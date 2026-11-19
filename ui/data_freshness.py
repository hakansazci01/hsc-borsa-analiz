"""
Veri kaynağı ve tazelik göstergesi.

Bir kararın güvenilirliği, verinin yaşından bağımsız değildir. Bu modül
kotasyonun kaynağını ve yaşını kullanıcıya açıkça gösterir; varsayılan
bilgi akışının ~15 dakika gecikmeli olabileceğini hatırlatır.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import streamlit as st

from ui.help_texts import h


@st.cache_data(ttl="5m", show_spinner=False)
def _snapshot(symbol: str) -> dict[str, Any]:
    from ui.live_data import get_live_snapshot

    try:
        return get_live_snapshot(symbol)
    except Exception:
        return {}


def snapshot(symbol: str) -> dict[str, Any]:
    """Kotasyon anlık görüntüsünü (5 dk önbellekli) döndürür."""
    return _snapshot(symbol)


def _age_text(value: Any) -> str | None:
    moment: datetime | None = None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    elif isinstance(value, str) and value.strip():
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - moment).total_seconds()
    if seconds < 0:
        return None
    if seconds < 90:
        return "az önce"
    if seconds < 3600:
        return f"{int(seconds // 60)} dk önce"
    if seconds < 86400:
        return f"{int(seconds // 3600)} sa önce"
    return f"{int(seconds // 86400)} gün önce"


def freshness_badges(symbol: str) -> None:
    """Kaynak, veri yaşı ve gecikme uyarısını rozet olarak gösterir."""
    snap = _snapshot(symbol)
    source = str(snap.get("quote_source") or "—")
    quote_time = (snap.get("info") or {}).get("quote_time")
    age = _age_text(quote_time)
    stale = bool(age and ("gün" in age or "sa önce" in age))

    with st.container(horizontal=True):
        st.badge(f"Kaynak: {source}", icon=":material/cloud:", color="blue", help=h("quote_source"))
        st.badge(
            f"Veri yaşı: {age}" if age else "Veri yaşı: belirtilmemiş",
            icon=":material/schedule:",
            color=("red" if stale else "green") if age else "orange",
            help="Kotasyonun ne kadar önce alındığı. Eski veri karar güvenini düşürür.",
        )
        st.badge(
            "Ücretsiz veri ~15 dk gecikmeli olabilir",
            icon=":material/info:", color="orange", help=h("disclaimer"),
        )
