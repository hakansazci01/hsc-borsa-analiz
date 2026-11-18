"""Anlık işlem sinyali: canlı 1d mumlardan 5m/15m tetikleyici analiz."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from ui import paper
from ui.bist_universe import load_companies, ordered_symbols
from ui.components import real_money_warning
from ui.help_texts import h
from ui.intraday import intraday_signal


st.subheader("Anlık işlem sinyali", divider="gray")
st.caption(
    "Canlı 1 dakikalık mumlar 5m/15m'e örneklenir; EMA9/20, VWAP, RSI7, hacim patlaması "
    "ve üst zaman dilimi onayı tek tek kontrol edilir. Koşullar birleşmeden sinyal üretilmez."
)
real_money_warning(compact=True)

universe = load_companies()
symbol = st.selectbox(
    "Hisse", ordered_symbols(universe),
    format_func=lambda s: f"{s} · {universe.get(s, s)}",
    key="intraday_symbol", help=h("bist_search"),
)


@st.fragment(run_every="15s")
def _render() -> None:
    result = intraday_signal(symbol, st.session_state.settings)
    if not result:
        st.warning("Canlı mum verisi alınamadı (seans dışında veya bağlantı yok).", icon=":material/warning:")
        return

    color = {"AL": "green", "BEKLE": "orange", "SAT": "red"}[result["decision"]]
    with st.container(border=True, key="intraday_verdict"):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            st.markdown(f"### {result['symbol']} · {result['decision']}")
            st.badge(f"Güven %{result['confidence']}", color=color)
            st.badge(result["session"], color="blue")
        st.caption(f"Son güncelleme {result['time']} · fiyat {result['price']:,.2f} ₺ · {result['reason']}")
        if result["stop"] and result["target"]:
            st.caption(f"Stop {result['stop']:,.2f} · Hedef {result['target']:,.2f} · ATR {result['atr']:.2f}")

    c1, c2 = st.columns([1, 1.2], gap="medium")
    with c1:
        with st.container(border=True):
            st.subheader("Tetikleyici kontroller", divider="gray")
            for check in result["checks"]:
                icon = ":material/check_circle:" if check["Geçti"] else ":material/cancel:"
                st.markdown(f"- {icon} **{check['Kontrol']}:** {check['Detay']}")
            if st.button(
                "Kurgusal pozisyon aç", icon=":material/add_circle:", key="intraday_open",
                disabled=result["decision"] == "BEKLE" or result["session"] != "Seans açık",
                help="Yalnızca seans içinde ve yönlü sinyalde; gerçek emir gönderilmez.",
            ):
                risk = st.session_state.settings["risk"]
                price = result["price"]
                qty = float(risk["initial_capital"]) * float(risk["position_size_pct"]) / price
                paper.open_position(
                    st.session_state.user, result["symbol"], round(qty, 2), price,
                    result["stop"], result["target"], result["confidence"],
                    f"Anlık tetikleyici: {result['decision']}",
                )
                st.toast(f"{result['symbol']} kurgusal pozisyon açıldı.", icon=":material/check:")
    with c2:
        with st.container(border=True):
            st.subheader("5 dakikalık canlı grafik", divider="gray")
            d = result["m5"].tail(80).reset_index()
            base = alt.Chart(d).encode(x=alt.X("Tarih:T", title=None))
            vol = base.mark_bar(opacity=0.25, color="#94A3B8").encode(y=alt.Y("Volume:Q", title="Hacim"))
            price_line = base.mark_line(color="#E2E8F0", strokeWidth=1.5).encode(y=alt.Y("Close:Q", title="Fiyat"))
            ema9 = base.mark_line(color="#34D399", strokeWidth=1.2).encode(y=alt.Y("EMA9:Q"))
            ema20 = base.mark_line(color="#FBBF24", strokeWidth=1.2).encode(y=alt.Y("EMA20:Q"))
            vwap = base.mark_line(color="#60A5FA", strokeWidth=1.2, strokeDash=[4, 3]).encode(y=alt.Y("VWAP:Q"))
            st.altair_chart(
                (vol + price_line + ema9 + ema20 + vwap).properties(height=300),
                alt=f"{result['symbol']} 5 dakikalık fiyat, EMA9/20 ve VWAP",
            )

            st.caption("Yeşil EMA9 · sarı EMA20 · kesikli mavi VWAP · gri hacim")


_render()
