"""HSC Borsa Analiz arayüz katmanı (Streamlit)."""

import sys
from pathlib import Path

# TEK INSTANCE: sadece proje .venv python'u kalıcı süreç olabilir.
# Sistem/global python '-m ui.<runner>' ile başlatıldığında sys.argv[0] modülün
# dosya yoludur; ikisini de kontrol edip import anında durdur.
_MODULES = {
    "ui.watchdog_runner", "ui.tr_runner", "ui.autonomous_scheduler",
    "watchdog_runner", "tr_runner", "autonomous_scheduler",
}
_FILES = {"watchdog_runner.py", "tr_runner.py", "autonomous_scheduler.py"}
if ".venv" not in sys.executable.lower():
    try:
        _entry = Path(sys.argv[0]).name
    except Exception:
        _entry = ""
    if any(a in _MODULES for a in sys.argv) or _entry in _FILES:
        raise SystemExit(0)
