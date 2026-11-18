"""
Gizli anahtarlara güvenli erişim.

Öncelik: Streamlit st.secrets (.streamlit/secrets.toml - gitignore).
Yedek: ortam değişkenleri / .env (mevcut Config altyapısı ile uyumlu).
Anahtarlar asla kaynak koda gömülmez ve arayüzde gösterilmez.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st


ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"


def _toml_fallback() -> dict[str, Any]:
    try:
        import tomllib
    except ImportError:
        return {}
    if not SECRETS_PATH.exists():
        return {}
    try:
        return tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get(section: str, key: str, default: str = "") -> str:
    """st.secrets -> ortam değişkeni -> TOML sırasıyla anahtar okur."""
    env_name = f"{section.upper()}_{key.upper()}"
    try:
        value = st.secrets.get(section, {}).get(key, "")
        if value:
            return str(value)
    except Exception:
        pass
    import os

    value = os.getenv(env_name, "")
    if value:
        return str(value)
    return str(_toml_fallback().get(section, {}).get(key, default) or default)


def status(section: str, keys: tuple[str, ...]) -> dict[str, Any]:
    """Anahtarların varlığını (değerini göstermeden) raporlar."""
    present = {k: bool(get(section, k)) for k in keys}
    return {"section": section, "keys": present, "configured": all(present.values())}
