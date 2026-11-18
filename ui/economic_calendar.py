"""
Ekonomik takvim: borsapy üzerinden günün makro olayları.

Yüksek/orta önemli olaylar ve Türkiye ile ilgili olanlar öne çıkarılır.
Ücretsiz kaynak, API anahtarı gerektirmez.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


@st.cache_data(ttl="1h", show_spinner=False)
def today_events() -> list[dict[str, Any]]:
    try:
        import borsapy as bp

        df = bp.EconomicCalendar().today()
        if df is None or df.empty:
            return []
        columns = [c for c in ["Time", "Country", "Importance", "Event", "Actual", "Forecast", "Previous"] if c in df.columns]
        rows = df[columns].to_dict("records")
        importance_order = {"high": 0, "mid": 1, "low": 2}
        rows.sort(key=lambda r: (
            0 if str(r.get("Country", "")).upper() in ("TÜRKİYE", "TURKEY", "TR") else 1,
            importance_order.get(str(r.get("Importance", "")).lower(), 3),
            str(r.get("Time", "")),
        ))
        return rows
    except Exception:
        return []
