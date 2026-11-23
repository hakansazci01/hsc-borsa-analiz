"""Watchdog sürecini kalıcı başlatır — MOTOR + SCHEDULER'ı gerçekten izler/başlatır."""

import os
import sys
from pathlib import Path

from ui.autonomous_ops import watchdog

LOCK = Path(__file__).resolve().parent.parent / "users" / "WATCHDOG_SINGLE.lock"


def _claim() -> bool:
    """Tek watchdog garantisi — varsa PID'i doğrula, ölüyse devral."""
    try:
        import psutil

        if LOCK.exists():
            pid = int(LOCK.read_text(encoding="utf-8").strip() or 0)
            if pid and psutil.pid_exists(pid) and pid != os.getpid():
                try:
                    cmd = " ".join(psutil.Process(pid).cmdline() or [])
                except Exception:
                    cmd = ""
                # Sadece gerçek watchdog PID'i kilidi tutar; wslhost.exe vb. devralınır.
                if "ui.watchdog_runner" in cmd:
                    return False
    except Exception:
        pass
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _kill_other_runners() -> None:
    """Kalıcı süreçleri TEK kopyaya indir — global/.venv ayrımı yok.

    Watchdog her başladığında motor/scheduler/watchdog kopyalarını temizler,
    sonra kendi kopyalarını kurar. Böylece sayı sürekli artmaz.
    """
    import os
    import psutil

    me = os.getpid()
    targets = ("ui.watchdog_runner", "ui.tr_runner", "ui.autonomous_scheduler")
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
            except Exception:
                pass


if __name__ == "__main__":
    # SADECE proje .venv python'u watchdog olabilir. Global python kopyaları
    # (start_module'un fallback'i) hemen çıkar — aksi halde zincirleme çoğalır.
    if ".venv" not in sys.executable.lower():
        sys.exit(0)
    if _claim():
        watchdog(claim_fn=_claim)

