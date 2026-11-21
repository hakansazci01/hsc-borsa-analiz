"""
Kalıcı başlatıcı — Windows görevleri BUNU çağırır.
Çalışma dizini ne olursa olsun kendi dizinini bulur ve 3 süreci başlatır.
Zaten ayakta olanları kontrol edip tekrar başlatmaz (çift süreç engeli).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from ui import autonomous_ops as ops  # noqa: E402


def main() -> None:
    # FELAKET KURTARMA: açılışta en son yedeği yükle (açık pozisyon hatırlanır)
    from ui import disaster_recovery

    disaster_recovery.recover()
    # watchdog_once() motor + scheduler + watchdog'u zaten kontrol edip başlatır.
    # Burada ayrıca watchdog başlatmak çift watchdog (ve çift motor) yaratıyordu.
    states = ops.watchdog_once()
    # Streamlit uygulaması da ayakta kalsın
    from launch_app import main as launch_app_main

    launch_app_main()
    ops._log(f"launch_all: motor={states['motor_alive']} scheduler={states['sched_alive']} "
             f"watchdog={states.get('watch_alive')}")


if __name__ == "__main__":
    main()
