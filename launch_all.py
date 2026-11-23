"""
TEK başlatma noktası: Windows Görev Zamanlayıcı (ONLOGON + 30 sn gecikme).

Startup bat / Registry Run key KULLANILMAZ. Her açılış şunu yazar:
users/autostart.log -> tarih - saat - sonuç BAŞARILI/BAŞARISIZ + hata.
Başlamadan önce eski .venv/global runner kopyalarını temizler (çift süreç olmasın).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
# Masaüstü simgesi HSC_START_LOG=manual_start.log geçirir; aksi halde autostart.log
AUTOSTART_LOG = ROOT / "users" / os.environ.get("HSC_START_LOG", "autostart.log")


def _autolog(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        AUTOSTART_LOG.parent.mkdir(parents=True, exist_ok=True)
        with AUTOSTART_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def _kill_old_runners() -> int:
    """Eski watchdog/motor/scheduler kopyalarını kapat — sadece 1'er tane kalsın."""
    import os

    import psutil

    me = os.getpid()
    targets = ("ui.watchdog_runner", "ui.tr_runner", "ui.autonomous_scheduler")
    killed = 0
    for p in psutil.process_iter(["pid", "cmdline", "exe"]):
        if p.info["pid"] == me:
            continue
        cmd = " ".join(p.info.get("cmdline") or [])
        exe = (p.info.get("exe") or "").lower()
        if "python" not in exe:
            continue
        if any(t in cmd for t in targets):
            try:
                p.kill()
                killed += 1
            except Exception:
                pass
    return killed


def main() -> None:
    _label = ("Masaüstünden başlatıldı"
              if os.environ.get("HSC_START_SOURCE") == "masaustu"
              else "Bilgisayar açıldı")
    _autolog(f"{_label}, bot başlatılıyor...")
    try:
        n = _kill_old_runners()
        _autolog(f"Eski süreç temizliği: {n} kopya kapatıldı")

        from ui import autonomous_ops as ops
        from ui import disaster_recovery

        disaster_recovery.recover()
        # watchdog_once() motor + scheduler + watchdog'u kontrol edip başlatır.
        # Watchdog kendi kopyalarını kurduktan sonra tek kopya güvenliğini sağla:
        # global/.venv karışık başlatmalarda çift watchdog/scheduler kalmasın.
        try:
            from ui import watchdog_runner
            watchdog_runner._kill_other_runners()
        except Exception:
            pass
        states = ops.watchdog_once()

        # WS market + user data stream'i kalıcı motor (ui.tr_runner) başlatır.
        # Bu süreç Streamlit'i başlatıp çıkar; daemon thread'ler burada yaşamaz.

        from launch_app import main as launch_app_main

        launch_app_main()
        # Anlık kontrol yeni başlayan süreçleri göremeyebilir — 3 sn sonra gerçek doğrulama
        time.sleep(3)
        w = ops.process_state("ui.watchdog_runner")
        m = ops.process_state("ui.tr_runner")
        s = ops.process_state("ui.autonomous_scheduler")
        _autolog(
            f"Sonuç: BAŞARILI — watchdog={w[0]} (PID {w[1]}) "
            f"motor={m[0]} (PID {m[1]}) scheduler={s[0]} (PID {s[1]})"
        )
    except Exception as exc:
        _autolog(f"Sonuç: BAŞARISIZ — {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
