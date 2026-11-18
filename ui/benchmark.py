"""
Benchmark: BIST 100 endeksinin aynı dönemdeki al-sat getirisi.

Stratejinin endeksi yenip yenemediğini görmek için kullanılır. Ücretsiz
kaynak (borsapy Index) üzerinden, anahtar gerektirmeden hesaplanır.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


@st.cache_data(ttl="1h", show_spinner=False)
def bist100_benchmark() -> dict[str, Any] | None:
    try:
        import borsapy as bp

        hist = bp.Index("XU100").history(period="2y", interval="1d")
        if hist is None or hist.empty or len(hist) < 2:
            return None
        close = hist["Close"].astype(float)
        first = float(close.iloc[0])
        last = float(close.iloc[-1])
        total = (last / first - 1) * 100
        days = (hist.index[-1] - hist.index[0]).days
        years = max(days / 365.25, 1 / 365.25)
        cagr = ((last / first) ** (1 / years) - 1) * 100
        running_max = close.cummax()
        mdd = float(((close - running_max) / running_max).min()) * 100
        return {
            "symbol": "BIST 100",
            "start": str(hist.index[0])[:10],
            "end": str(hist.index[-1])[:10],
            "total_return_pct": round(total, 2),
            "cagr_pct": round(cagr, 2),
            "max_drawdown_pct": round(mdd, 2),
            "last": round(last, 2),
        }
    except Exception:
        return None
