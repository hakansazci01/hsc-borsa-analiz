"""
Kalıcı Binance TR kâr odaklı çalışma döngüsü.

- Bilgisayar açık olduğu sürece çalışır; STOP dosyası oluşturulana kadar durmaz.
- Her turda beklenmeyen hata oluşsa bile loglar ve devam eder (self-healing).
- Kâr odaklı: TP'ye/zirve-stop'a/breakeven'e erişince satar, kârla pozisyon büyütür.
- Durdurma: ui.tr_scalper.STOP_FILE oluşturmak (paneldeki düğme).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from ui import auth, tr_scalper

LOG = auth.USERS_DIR / "tr_scalper.log"
RUN_FLAG = auth.USERS_DIR / "TR_SCALPER_RUN"
LOCK = auth.USERS_DIR / "TR_SCALPER_LOCK"
INTERVAL = 8    # HIZLI MAKER modu: 8 sn tur (BTC/ETH, WS fiyat) — eski sistem 8. turda bir

# 1-dk scalper KAPALI: tüm döngü günlük EMA50 motorunu çağırır.
CYCLE = tr_scalper.cycle   # günlük EMA50 (1dk scalper kaldırıldı)


def _pid_alive(pid: int) -> bool:
    """PID yaşayan bir MOTOR mu? (wslhost.exe gibi PID yeniden kullanımını engelle)."""
    try:
        import psutil

        p = psutil.Process(pid)
        cmd = " ".join(p.cmdline() or [])
        exe = (p.exe() or "").lower()
        return "python" in exe and "ui.tr_runner" in cmd
    except Exception:
        return False


def _acquire_lock() -> bool:
    """Atomik kilit: aynı anda birden fazla motorun emir atmasını engelle."""
    for attempt in range(2):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            os.close(fd)
            return True
        except FileExistsError:
            try:
                old = int(LOCK.read_text(encoding="utf-8").strip() or 0)
            except Exception:
                old = 0
            if old and _pid_alive(old):
                return False
            try:
                LOCK.unlink(missing_ok=True)
            except OSError:
                return False
    return False


def _release_lock() -> None:
    try:
        if LOCK.exists() and int(LOCK.read_text(encoding="utf-8").strip() or 0) == os.getpid():
            LOCK.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def run_forever() -> None:
    RUN_FLAG.parent.mkdir(parents=True, exist_ok=True)
    if not _acquire_lock():
        _log("ZATEN ÇALIŞAN MOTOR VAR — bu örnek çıkıyor (çift emir riski)")
        return
    RUN_FLAG.write_text("running", encoding="utf-8")
    tr_scalper.STOP_FILE.unlink(missing_ok=True)
    _log("KALICI MOTOR BAŞLADI — kâr odaklı, 15 sn tur, self-healing")
    # WS market + user data stream'i KALICI motor başlatır.
    # launch_all.py kısa ömürlü; oradaki daemon thread'ler süreç çıkınca ölüyordu.
    try:
        from ui import ws_feed
        ws_feed.start()
    except Exception as exc:
        _log(f"WS başlatılamadı (REST yedekte): {type(exc).__name__}")
    try:
        while True:
            try:
                # Kilit baskasina gectiyse bu ornek cikar (cift emir riski).
                if int(LOCK.read_text(encoding="utf-8").strip() or 0) != os.getpid():
                    _log("Kilit baska PID'de — cift emir riski, çıkıyorum")
                    return
                if tr_scalper.STOP_FILE.exists():
                    RUN_FLAG.unlink(missing_ok=True)
                    _log("Durdurma sinyali alındı — güvenle çıkılıyor")
                    return
                # HIZLI MAKER — her 8 sn. Eski 30 coin taraması 8. turda bir.
                lines: list[str] = []
                try:
                    from ui import fast_maker
                    lines += fast_maker.step()
                except Exception as exc:
                    lines.append(f"FAST_MAKER hata: {type(exc).__name__}: {exc}")
                _fast_tick = globals().get("_fast_tick", 0) + 1
                globals()["_fast_tick"] = _fast_tick
                if _fast_tick % 8 == 0:
                    lines += CYCLE()
                for line in lines:
                    _log(line)
                try:
                    from ui import tr_journal

                    pos = tr_scalper._load().get("position")
                    kind = "emir" if any(
                        x.startswith("AL ") or x.startswith("SAT ") for x in lines
                    ) else "tarama"
                    tr_journal.append(lines, pos, kind)
                except Exception:
                    pass
            except Exception as exc:  # self-healing: tek hata tüm sistemi öldürmez
                _log(f"HATA ({type(exc).__name__}): {str(exc)[:150]} — devam ediliyor")
            time.sleep(INTERVAL)
    finally:
        _release_lock()


if __name__ == "__main__":
    # Sadece proje .venv python'u motor olabilir (çift emir riski).
    if ".venv" in sys.executable.lower():
        run_forever()
