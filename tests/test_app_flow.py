"""AppTest: giriş + 16 sayfanın tamamı (CI için)."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from ui import auth
from ui.core import default_settings


ROOT = Path(__file__).resolve().parent.parent
PAGES = [
    "akilli_panel", "ajans", "anlik", "terminal", "tarayici", "bot", "canli",
    "hesabim", "performans", "risk", "laboratuvar", "denetim", "piyasa",
    "hisse", "portfoy", "ayarlar",
]
USER = "ci_test"


def _setup() -> dict:
    try:
        auth.delete_account(USER)
    except Exception:
        pass
    auth.register(USER, "CiPass12345")
    return default_settings()


def _teardown() -> None:
    try:
        auth.delete_account(USER)
    except Exception:
        pass


def test_all_pages() -> None:
    settings = _setup()
    try:
        entry = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120)
        entry.run()
        assert not entry.exception, entry.exception

        for name in PAGES:
            app = AppTest.from_file(str(ROOT / "app_pages" / f"{name}.py"), default_timeout=180)
            app.session_state["user"] = USER
            app.session_state["settings"] = settings
            app.session_state["settings_owner"] = USER
            app.session_state["selected_symbol"] = settings.get("symbols", ["THYAO"])[0]
            app.run()
            assert not app.exception, f"{name}: {app.exception}"
    finally:
        _teardown()
