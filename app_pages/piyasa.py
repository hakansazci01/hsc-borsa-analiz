"""Piyasa analizi: tüm izleme listesinin taranması ve akıllı sinyal paneli."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import components, insights
from ui.core import analysis_args, analyze_symbol, scan_market
from ui.economic_calendar import today_events
from ui.help_texts import h
from ui.signal_display import lamp_row


settings = st.session_state.settings
args = analysis_args(settings)
profile = settings["profile"]

with st.container(horizontal=True, horizontal_alignment="right"):
    st.caption(f"Analiz aralığı: **{args['period']} / {args['interval']}** · Profil: **{profile}**")
    if st.button("Verileri yenile", icon=":material/refresh:", key="refresh_scan", help=h("instant_analysis")):
        scan_market.clear()
        analyze_symbol.clear()
        st.rerun()

results = list(
    scan_market(
        tuple(settings["symbols"]),
        args["period"], args["interval"], args["indicators"], args["weights"],
        args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
    )
)
summary = insights.market_summary(results, profile)

# ---- Üst özet kartları (ikon + mini grafik) ----
al_spark = [
    1 if r.get("info", {}).get("signal") in ("STRONG_BUY", "BUY") else 0
    for r in results
]
sat_spark = [
    1 if r.get("info", {}).get("signal") in ("STRONG_SELL", "SELL") else 0
    for r in results
]
conf_spark = [
    insights.confidence(r["info"], r["backtest"])
    for r in results if "info" in r
]
with st.container(horizontal=True):
    st.metric("Taranan hisse", summary["total"], border=True,
              icon=":material/leaderboard:", help=h("symbols"))
    st.metric("AL sinyali", summary["buy_count"], border=True,
              icon=":material/trending_up:", chart_data=al_spark,
              chart_type="bar", help=h("signal"))
    st.metric("SAT sinyali", summary["sell_count"], border=True,
              icon=":material/trending_down:", chart_data=sat_spark,
              chart_type="bar", help=h("signal"))
    st.metric("Ortalama güven", f"%{summary['avg_confidence']}", border=True,
              icon=":material/speed:", chart_data=conf_spark,
              chart_type="line", help=h("confidence"))

st.container(height=1, border=False)

# ---- Akıllı öneri ----
with st.container(border=True):
    st.subheader("Akıllı öneri", divider="gray")
    pick = summary["pick"]
    if pick:
        pick_bt = next(
            r["backtest"] for r in results
            if r.get("info", {}).get("symbol") == pick["symbol"]
        )
        rec = insights.recommendation(pick["info"], pick_bt, profile, settings["risk"])
        with st.container(horizontal=True, vertical_alignment="bottom"):
            lamp_row({"decision": rec["action"], "confidence": rec["confidence"]})
            st.markdown(f"### {pick['symbol']}")
            st.markdown(f"**{insights.signal_label(pick['info']['signal'])}** · Güven skoru **%{pick['confidence']}**")
        st.write(rec["rationale"])
        with st.container(horizontal=True, horizontal_alignment="right"):
            if st.button("Hisse detayını aç", icon=":material/open_in_new:", key="pick_detail", help="Seçilen hissenin grafik ve gösterge detaylarına geçer."):
                st.session_state.selected_symbol = pick["symbol"]
                st.switch_page("app_pages/hisse.py")
    else:
        st.info(
            "Şu anda seçtiğiniz risk profiline uyan güçlü bir AL sinyali bulunmuyor. "
            "Puanlar değiştiğinde burada yeni bir öneri görünecek.",
            icon=":material/info:",
        )

# ---- Sinyal tablosu + puan grafiği ----
left, right = st.columns([1.7, 1], gap="medium")
with left:
    st.subheader("Sinyal paneli")
    rows: list[dict] = []
    for r in results:
        if "error" in r:
            rows.append({"Hisse": r["symbol"], "Sinyal": "VERİ HATASI", "Puan": 0,
                         "Fiyat": None, "RSI": None, "Güven": None, "Getiri %": None,
                         "Kazanma %": None, "Maks. düşüş %": None, "Detay": r["symbol"]})
            continue
        info, bt = r["info"], r["backtest"]
        rows.append({
            "Hisse": info["symbol"],
            "Sinyal": insights.signal_label(info["signal"]),
            "Puan": float(info["score"]),
            "Fiyat": float(info["last_close"]),
            "RSI": float(info["rsi"]),
            "Güven": insights.confidence(info, bt),
            "Getiri %": float(bt.get("total_return_pct", 0)),
            "Kazanma %": float(bt.get("win_rate_pct", 0)),
            "Maks. düşüş %": float(bt.get("max_drawdown_pct", 0)),
            "Detay": info["symbol"],
        })
    if not rows:
        st.info("İzleme listesi boş. Ayarlar sayfasından en az bir hisse ekleyin.", icon=":material/info:")
        st.stop()
    table = pd.DataFrame(rows)

    def _set_detail() -> None:
        click = st.session_state.get("row_action")
        if click:
            st.session_state.selected_symbol = click.label
            st.session_state.detail_requested = True

    def _signal_color(val: str) -> str:
        palette = {
            "Güçlü AL": "#065F46", "AL": "#059669", "NÖTR": "#475569",
            "SAT": "#DC2626", "Güçlü SAT": "#991B1B", "VERİ HATASI": "#7C2D12",
        }
        color = palette.get(val, "#475569")
        return f"background-color: {color}; color: white; font-weight: 600; text-align: center;"

    styled = table.style.map(_signal_color, subset=["Sinyal"])
    st.dataframe(
        styled,
        hide_index=True,
        column_config={
            "Sinyal": st.column_config.TextColumn("Sinyal", width="small", help=h("signal")),
            "Puan": st.column_config.NumberColumn("Puan", format="%.2f", help=h("score")),
            "Fiyat": st.column_config.NumberColumn("Fiyat", format="%.2f", help=h("last_close")),
            "RSI": st.column_config.NumberColumn("RSI", format="%.1f", help=h("rsi")),
            "Güven": st.column_config.ProgressColumn("Güven", min_value=0, max_value=100, format="%d", help=h("confidence")),
            "Getiri %": st.column_config.NumberColumn("Getiri %", format="%.1f", help="Backtest boyunca kurgusal sermayenin toplam yüzde değişimi."),
            "Kazanma %": st.column_config.NumberColumn("Kazanma %", format="%.1f", help=h("win_rate")),
            "Maks. düşüş %": st.column_config.NumberColumn("Maks. düşüş %", format="%.1f", help=h("max_drawdown")),
            "Detay": st.column_config.ButtonColumn("Detay", on_click=_set_detail, key="row_action", type="secondary", help="Bu hissenin detay sayfasına gider."),
        },
        alt="Hisse sinyalleri, puanlar ve backtest özet metrikleri",
    )
    if st.session_state.pop("detail_requested", False):
        st.switch_page("app_pages/hisse.py")

with right:
    st.subheader("Puan dağılımı")
    components.score_chart(results)
    st.caption("Puan -5 (güçlü sat) ile +5 (güçlü al) arasında değişir.")

with st.expander("Ekonomik takvim (bugün)", icon=":material/calendar_month:"):
    events = today_events()
    if events:
        st.caption("Türkiye ve yüksek/orta önemli olaylar üstte. Veri: borsapy EconomicCalendar.")
        st.dataframe(events, hide_index=True, alt="Bugünün ekonomik olay takvimi")
    else:
        st.caption("Bugün için ekonomik olay bulunamadı.")

with st.expander("Bu sinyaller nasıl üretiliyor?", icon=":material/help:"):
    st.markdown(
        "Her hisse için RSI, MACD, trend (SMA50/SMA200), Bollinger bantları, Stokastik, "
        "OBV ve VWAP göstergeleri ayrı ayrı puanlanır. Ağırlıklı toplam -5..+5 aralığına "
        "çevrilir ve AL / SAT / NÖTR olarak sınıflandırılır. **Güven skoru** ise sinyal "
        "gücünü, göstergelerin birbirini onaylamasını ve geçmiş test performansını "
        "birleştirir. Detaylar **Hisse detayı** sayfasındadır."
    )
