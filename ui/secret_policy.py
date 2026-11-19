"""
Anahtar döndürme politikası takibi.

Yalnızca *ne zaman döndürüldüğünü* saklar; anahtar değerlerini asla okumaz,
göstermez veya günlüğe yazmaz. 90 günü geçen anahtarlar için uyarı verir.
Resmi politika: docs/SECRET_ROTATION.md
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from ui import auth


POLICY_FILE = "secret_rotation.json"
MAX_AGE_DAYS = 90

SERVICES: tuple[str, ...] = (
    "finnhub.api_key",
    "gemini.api_key",
    "alpaca_paper.key_id / secret_key",
    "twilio.auth_token",
    "smtp.password",
    "inngest.signing_key / event_key",
    "alerts.telegram_bot_token",
)


def _path() -> Path:
    return auth.USERS_DIR / POLICY_FILE


def load() -> dict[str, Any]:
    data = auth.read_json(_path(), {})
    return data if isinstance(data, dict) else {}


def days_since(service: str) -> int | None:
    value = (load().get(service) or {}).get("last_rotated")
    if not value:
        return None
    try:
        return (date.today() - date.fromisoformat(str(value))).days
    except ValueError:
        return None


def record(service: str, when: date) -> None:
    data = load()
    data[service] = {"last_rotated": when.isoformat()}
    auth.write_json(_path(), data)


def render_panel() -> None:
    with st.expander("Anahtar döndürme takibi", icon=":material/key:"):
        st.caption(
            f"Politika: kritik servis anahtarları en fazla **{MAX_AGE_DAYS} günde bir** "
            "döndürülür. Burada yalnızca tarih tutulur; anahtar değerleri gösterilmez. "
            "Detay: `docs/SECRET_ROTATION.md`."
        )
        data = load()
        for service in SERVICES:
            age = days_since(service)
            if age is None:
                color, label = "red", "KAYIT YOK"
            elif age > MAX_AGE_DAYS:
                color, label = "red", f"{age} gün — SÜRESİ GEÇTİ"
            elif age > MAX_AGE_DAYS - 14:
                color, label = "orange", f"{age} gün — YAKLAŞIYOR"
            else:
                color, label = "green", f"{age} gün — OK"
            c1, c2 = st.columns([2, 1])
            c1.markdown(f"**{service}**")
            c2.badge(label, color=color)
        st.markdown("**Döndürme kaydet**")
        service = st.selectbox("Servis", SERVICES, key="secret_rot_service")
        when = st.date_input("Döndürme tarihi", value=date.today(), key="secret_rot_date")
        if st.button("Tarihi kaydet", key="secret_rot_save"):
            record(service, when)
            st.toast(f"{service} için döndürme tarihi kaydedildi.", icon=":material/check:")
            st.rerun()
