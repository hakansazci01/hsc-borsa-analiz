"""
Finnhub ek veri kaynağı (ABD hisseleri).

Test edilen ücretsiz anahtar BIST sembollerini kapsamıyor (THYAO boş dönüyor);
AAPL gibi ABD sembollerinde çalışıyor. Bu yüzden yalnızca '.IS' eki olmayan
sembollerde gösterilir. BIST fiyatı için borsapy/TradingView kullanılır.
"""

from __future__ import annotations

import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

import streamlit as st

from ui.secrets_access import get


def is_us_symbol(symbol: str) -> bool:
    return not symbol.strip().upper().endswith(".IS")


@st.cache_data(ttl="60s", show_spinner=False)
def us_quote(symbol: str) -> dict[str, Any] | None:
    key = get("finnhub", "api_key")
    if not key or not is_us_symbol(symbol):
        return None
    url = f"https://finnhub.io/api/v1/quote?symbol={urllib.parse.quote(symbol.upper())}&token={key}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            import json

            data = json.loads(resp.read().decode())
        # Boş yanıt: c=0 ve pc=0
        if not data or not data.get("c"):
            return None
        return {
            "price": data.get("c"),
            "change": data.get("d"),
            "change_pct": data.get("dp"),
            "high": data.get("h"),
            "low": data.get("l"),
            "open": data.get("o"),
            "prev_close": data.get("pc"),
        }
    except Exception:
        return None


@st.cache_data(ttl="15m", show_spinner=False)
def us_news(symbol: str, days: int = 7) -> list[dict[str, Any]]:
    key = get("finnhub", "api_key")
    if not key or not is_us_symbol(symbol):
        return []
    today = date.today()
    frm = today - timedelta(days=days)
    url = (
        f"https://finnhub.io/api/v1/company-news?symbol={urllib.parse.quote(symbol.upper())}"
        f"&from={frm}&to={today}&token={key}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            import json

            return json.loads(resp.read().decode())[:8]
    except Exception:
        return []
