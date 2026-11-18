"""
Tüm BIST evreni tarayıcı (804 hisse).

borsapy.scan() ile 0.3-0.5 sn içinde tüm hisseleri koşul bazında filtreler;
önceki 30'luk "hızlı tarama" yerine gerçek tam evren taraması sağlar.
"""

from __future__ import annotations

import warnings
from typing import Any

import streamlit as st

from ui.bist_universe import load_companies


PRESETS: dict[str, str] = {
    "Aşırı satım adayları (RSI<35)": "rsi < 35",
    "Yükselenler (günlük >%3)": "change > 3",
    "Düşenler (günlük <-%3)": "change < -3",
    "Yüksek hacimli (>10M)": "volume > 10000000",
    "Güçlü momentum": "rsi > 55 and change > 1",
    "Satış baskısı": "rsi < 45 and change < -1",
    "Hacimli yükseliş": "change > 1 and volume > 5000000",
}

HELP_TEXT = (
    "Koşul alanında borsapy sözdizimi kullanılır: rsi, change, volume, close, market_cap. "
    "Örnek: `rsi < 40 and volume > 5000000`"
)


@st.cache_data(ttl="60s", max_entries=40, show_spinner=False)
def scan_all(condition: str, limit: int = 80) -> tuple[dict[str, Any], ...]:
    import borsapy as bp

    universe = list(load_companies().keys())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = bp.scan(universe, condition, interval="1d", limit=limit)
    if df is None or df.empty:
        return ()
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        symbol = str(row.get("symbol") or row.get("ticker") or "").upper()
        if not symbol:
            continue
        rows.append({
            "Sembol": symbol,
            "Şirket": str(row.get("name", "")),
            "Fiyat": _num(row.get("close")),
            "Değişim %": _num(row.get("change")),
            "RSI": _num(row.get("rsi")),
            "Hacim": _num(row.get("volume")),
        })
    return tuple(rows)


@st.cache_data(ttl="5m", max_entries=100, show_spinner=False)
def symbol_signal(symbol: str) -> str | None:
    """Tek sembol için günlük teknik öneriyi döndürür (AL/SAT/NÖTR)."""
    import borsapy as bp

    try:
        summary = bp.Ticker(symbol).ta_signals(interval="1d").get("summary", {})
        return str(summary.get("recommendation", ""))
    except Exception:
        return None


def _num(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None
