"""
15 dakikalık net kâr/zarar takibi.

Her 15 dakikalık dilimde portföyün gerçekleşen + açık K/Z'ini kaydeder;
seans sonunda günün net tablosunu ve grafiğini üretir. Tüm veriler kurgusaldır.
"""

from __future__ import annotations

from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from ui import auth, paper
from ui.market_session import now


def _path(username: str):
    return auth.user_dir(username) / "pnl_15m.json"


def _load(username: str) -> list[dict[str, Any]]:
    data = auth.read_json(_path(username), [])
    return data if isinstance(data, list) else []


def _slot(moment) -> str:
    minute = (moment.minute // 15) * 15
    return f"{moment.hour:02d}:{minute:02d}"


def record_mark(
    username: str,
    settings: dict[str, Any] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    """Seans içindeki 15 dk dilimini kaydeder; aynı dilim güncellenir."""
    moment = now()
    if not force and moment.weekday() >= 5:
        return None
    slot = _slot(moment)
    day = moment.strftime("%Y-%m-%d")

    settings = settings or (st.session_state.get("settings", {}) if st.session_state else {})
    positions = paper.evaluate(username, settings)
    open_pnl = sum(float(p.get("pnl_amount", 0)) for p in positions)

    realized = 0.0
    for row in auth.read_history(username, limit=500):
        if row.get("type") == "PAPER_SAT" and str(row.get("time", "")).startswith(moment.strftime("%d.%m.%Y")):
            realized += float(row.get("pnl_amount", 0) or 0)

    net = realized + open_pnl
    capital = float(settings.get("risk", {}).get("initial_capital", 100000)) + net
    buys = sum(1 for d in (decisions or []) if d.get("decision") in ("AL", "STRONG_BUY", "BUY"))
    sells = sum(1 for d in (decisions or []) if d.get("decision") in ("SAT", "STRONG_SELL", "SELL"))

    record = {
        "date": day,
        "slot": slot,
        "time": auth._now(),
        "realized": round(realized, 2),
        "open": round(open_pnl, 2),
        "net": round(net, 2),
        "equity": round(capital, 2),
        "positions": len(positions),
        "buys": buys,
        "sells": sells,
        "final": slot == "18:00",
    }
    rows = [r for r in _load(username) if not (r.get("date") == day and r.get("slot") == slot)]
    rows.append(record)

    # Kaçırılan 15 dk dilimlerini geriye dönük doldur (uygulama kapalı kalmış olabilir)
    if 10 <= moment.hour < 18 or (moment.hour == 18 and moment.minute == 0):
        existing = {r.get("slot") for r in rows if r.get("date") == day}
        for hour in range(10, 18):
            for minute in (0, 15, 30, 45):
                candidate = f"{hour:02d}:{minute:02d}"
                if candidate <= slot and candidate not in existing:
                    filled = dict(record)
                    filled["slot"] = candidate
                    filled["backfill"] = True
                    rows.append(filled)

    rows = sorted(rows, key=lambda r: (r.get("date", ""), r.get("slot", "")))[-400:]
    auth.write_json(_path(username), rows)
    return record


def today_table(username: str) -> pd.DataFrame:
    day = now().strftime("%Y-%m-%d")
    rows = [r for r in _load(username) if r.get("date") == day]
    if not rows:
        return pd.DataFrame(columns=["Saat", "Gerçekleşen", "Açık K/Z", "Net K/Z", "Sermaye", "Pozisyon", "AL/SAT"])
    df = pd.DataFrame(rows)
    df["AL/SAT"] = df.apply(
        lambda r: f"{int(r.get('buys',0))} AL / {int(r.get('sells',0))} SAT", axis=1
    )
    return df.rename(columns={
        "slot": "Saat", "realized": "Gerçekleşen", "open": "Açık K/Z",
        "net": "Net K/Z", "equity": "Sermaye", "positions": "Pozisyon",
    })[["Saat", "Gerçekleşen", "Açık K/Z", "Net K/Z", "Sermaye", "Pozisyon", "AL/SAT"]]


def render_panel(username: str) -> None:
    df = today_table(username)
    if df.empty:
        st.caption("Bugün için 15 dakikalık kayıt yok. Seans içinde otomatik oluşur.")
        return
    last = df.iloc[-1]
    previous = df.iloc[-2] if len(df) > 1 else None
    slot_net = float(last["Net K/Z"]) - (
        float(previous["Net K/Z"]) if previous is not None else 0.0
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Son 15 dk net", f"{slot_net:+,.2f} ₺", icon=":material/show_chart:")
    c2.metric("Günlük net", f"{float(last['Net K/Z']):,.2f} ₺", icon=":material/account_balance:")
    c3.metric("Sermaye", f"{float(last['Sermaye']):,.2f} ₺", icon=":material/savings:")
    st.dataframe(
        df, hide_index=True,
        column_config={
            "Gerçekleşen": st.column_config.NumberColumn(format="%,.2f"),
            "Açık K/Z": st.column_config.NumberColumn(format="%,.2f"),
            "Net K/Z": st.column_config.NumberColumn(format="%,.2f"),
            "Sermaye": st.column_config.NumberColumn(format="%,.2f"),
        },
        alt="15 dakikalık dilimlerde net kâr/zarar tablosu",
    )
    chart = (
        alt.Chart(df)
        .mark_area(line={"color": "#34D399"}, color="#34D399", opacity=0.2)
        .encode(
            x=alt.X("Saat:N", title=None, sort=list(df["Saat"])),
            y=alt.Y("Net K/Z:Q", title="Net K/Z (₺)"),
            tooltip=["Saat:N", alt.Tooltip("Net K/Z:Q", format=",.2f")],
        )
        .properties(height=180)
    )
    st.altair_chart(chart, alt="15 dakikalık net K/Z eğrisi")
