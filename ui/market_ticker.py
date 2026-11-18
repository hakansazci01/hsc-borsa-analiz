"""
Sidebar canlı piyasa şeridi: dolar, euro, gram altın, BIST100, ons altın.

Kaynaklar (anahtar gerektirmez):
- borsapy FX.current  → USD/TRY, EUR/TRY
- borsapy Index.history → BIST100 (XU100)
- Frankfurter API → XAU/USD (gram altın = XAU/USD × USD/TRY / 31.1035)
"""

from __future__ import annotations

import urllib.request
from typing import Any

import streamlit as st


@st.cache_data(ttl="60s", max_entries=10, show_spinner=False)
def market_snapshot() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def add(name: str, value: Any, change: Any, source: str, unit: str = "") -> None:
        try:
            items.append({
                "name": name,
                "value": float(value),
                "change": float(change) if change is not None else 0.0,
                "source": source,
                "unit": unit,
            })
        except (TypeError, ValueError):
            pass

    try:
        import borsapy as bp

        for name, asset in (("USD/TRY", "USD"), ("EUR/TRY", "EUR")):
            q = bp.FX(asset).current
            if isinstance(q, dict) and q.get("last"):
                last = float(q["last"])
                open_ = float(q.get("open") or last)
                add(name, last, (last / open_ - 1) * 100 if open_ else 0, "borsapy")
    except Exception:
        pass

    usd = next((i["value"] for i in items if i["name"] == "USD/TRY"), None)
    try:
        with urllib.request.urlopen(
            "https://api.frankfurter.dev/v2/rate/xau/usd", timeout=10
        ) as resp:
            import json

            xau = float(json.loads(resp.read().decode())["rate"])
        add("XAU/USD", xau, None, "Frankfurter")
        if usd:
            add("Gram altın", xau * usd / 31.1035, None, "Frankfurter × borsapy", " ₺")
    except Exception:
        pass

    try:
        import borsapy as bp

        hist = bp.Index("XU100").history(period="5d", interval="1d")
        if hist is not None and not hist.empty:
            last = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
            add("BIST 100", last, (last / prev - 1) * 100 if prev else 0, "borsapy")
    except Exception:
        pass

    return items


@st.fragment(run_every="60s")
def _ticker_fragment() -> None:
    items = market_snapshot()
    if not items:
        st.caption("Canlı piyasa verisi alınamadı.")
        return
    for item in items:
        value = f"{item['value']:,.2f}{item['unit']}"
        st.metric(
            item["name"], value,
            delta=f"{item['change']:+.2f}%" if item["change"] else None,
            help=f"Kaynak: {item['source']} · 60 saniyede bir yenilenir",
        )
    if st.button("Piyasa verisini yenile", icon=":material/refresh:", key="ticker_refresh"):
        market_snapshot.clear()
        st.rerun()


def render_sidebar_ticker() -> None:
    """Sidebar'da canlı piyasa şeridini ve seans durumunu gösterir."""
    from ui.market_session import status as session_status

    with st.sidebar:
        st.markdown("#### Canlı piyasa")
        session = session_status()
        st.badge(
            session["label"],
            color={"open": "green", "pre_market": "orange", "after_hours": "gray", "closed": "gray"}[session["key"]],
            help=session["detail"],
        )
        st.caption(session["detail"])
        st.caption("Döviz · altın · endeks · BIST")
        _ticker_fragment()
