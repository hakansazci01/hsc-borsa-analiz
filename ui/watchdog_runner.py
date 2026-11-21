"""Watchdog sürecini kalıcı başlatır — MOTOR + SCHEDULER'ı gerçekten izler/başlatır."""

import os
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
                return False
    except Exception:
        pass
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True


if __name__ == "__main__":
    if _claim():
        watchdog()

