"""Hisse detayı: interaktif grafikler, gösterge yorumları ve akıllı analist."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import components, insights
from ui.benchmark import bist100_benchmark
from ui.core import INTERVAL_OPTIONS, PERIOD_OPTIONS, analysis_args, analyze_symbol
from ui.finnhub import is_us_symbol, us_news, us_quote
from ui.help_texts import h


settings = st.session_state.settings
args = analysis_args(settings)
profile = settings["profile"]

symbol_list = list(dict.fromkeys(settings["symbols"] + [st.session_state.selected_symbol]))
if st.session_state.selected_symbol not in symbol_list:
    symbol_list.append(st.session_state.selected_symbol)

with st.container(horizontal=True, vertical_alignment="bottom"):
    symbol = st.selectbox("Hisse", symbol_list, key="detail_symbol", help=h("symbols"))
    period = st.pills(
        "Veri aralığı", PERIOD_OPTIONS, default=settings["period"],
        key="detail_period", help=h("period"),
    ) or settings["period"]
    interval = st.segmented_control(
        "Aralık", INTERVAL_OPTIONS, default=settings["interval"],
        key="detail_interval", help=h("interval"),
    ) or settings["interval"]

try:
    res = analyze_symbol(
        symbol, period, interval, args["indicators"], args["weights"],
        args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
    )
except Exception as exc:
    st.error(f"{symbol} için veri alınamadı: {exc}", icon=":material/error:")
    st.stop()

info, bt, df = res["info"], res["backtest"], res["df"]
conf = insights.confidence(info, bt)
rec = insights.recommendation(info, bt, profile, settings["risk"])

# ---- Başlık ----
with st.container(horizontal=True, wrap=True, vertical_alignment="bottom"):
    st.markdown(f"## {symbol}")
    components.signal_badge(info["signal"])
    st.metric("Son fiyat", f"{info['last_close']:,.2f}", help=h("last_close"))
    st.metric("Sinyal puanı", f"{info['score']:+.2f}", help=h("score"))
    st.metric("Güven", f"%{conf}", help=h("confidence"))

st.container(height=1, border=False)

chart_col, insight_col = st.columns([1.55, 1], gap="medium")

with chart_col:
    with st.container(border=True):
        st.subheader("Fiyat ve teknik göstergeler", divider="gray")
        components.price_chart(df, bt.get("trades", []), symbol)
        st.caption("Yeşil üçgen: backtest girişi · Kırmızı üçgen: çıkış · Gölgeli alan: Bollinger bantları")
    with st.container(border=True):
        st.subheader("Osilatörler", divider="gray")
        components.oscillator_charts(df)

with insight_col:
    with st.container(border=True):
        st.subheader("Akıllı analist", divider="gray")
        tone_fn = {
            "success": st.success, "warning": st.warning, "error": st.error, "info": st.info,
        }.get(rec["tone"], st.info)
        tone_fn(rec["headline"], icon=":material/auto_awesome:")
        st.write(rec["rationale"])

        if rec["pros"]:
            st.markdown("**Olumlu işaretler**")
            for item in rec["pros"]:
                st.markdown(f"- {item}")
        if rec["cons"]:
            st.markdown("**Risk işaretleri**")
            for item in rec["cons"]:
                st.markdown(f"- {item}")

        st.divider()
        components.confidence_gauge(conf)
        st.caption(f"Risk profili: **{profile}** · {insights.PROFILES[profile]['description']}")

        st.markdown("**Profil bazlı işlem planı**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pozisyon", f"%{rec['size_pct']}", help=h("position_size"))
        c2.metric("Tahsis", f"{rec['amount']:,.0f}", help="Seçilen risk profiline göre bu işleme ayrılan kurgusal tutar.")
        c3.metric("Stop", f"{rec['stop']:,.2f}", help=h("stop_loss"))
        c4.metric("Hedef", f"{rec['target']:,.2f}", help=h("take_profit"))

    with st.container(border=True):
        st.subheader("Gösterge detayları", divider="gray")
        detail_df = pd.DataFrame(
            [{"Gösterge": insights.INDICATOR_LABELS.get(k, k), "Yorum": v}
             for k, v in info["details"].items()]
        )
        st.dataframe(
            detail_df,
            hide_index=True,
            column_config={
                "Gösterge": st.column_config.TextColumn(width="small", help=h("score")),
                "Yorum": st.column_config.TextColumn(help="Göstergenin son değerinin nasıl yorumlandığı."),
            },
            alt=f"{symbol} göstergelerinin ayrıntılı yorumları",
        )

st.container(height=1, border=False)
st.subheader("Geriye dönük test özeti", divider="gray")
m1, m2, m3, m4, m5 = st.columns(5)
equity_spark = [float(v) for v in bt.get("equity_curve", [])]
m1.metric("Toplam getiri", f"%{bt.get('total_return_pct', 0)}",
          icon=":material/percent:", chart_data=equity_spark or None,
          chart_type="area", help="Backtest boyunca kurgusal sermayenin toplam değişimi.")
m2.metric("Yıllık getiri", f"%{bt.get('cagr_pct', 0)}", icon=":material/calendar_month:",
          help="Yıllıklandırılmış bileşik getiri (CAGR). Farklı süreleri karşılaştırmak için kullanılır.")
m3.metric("Kazanma oranı", f"%{bt.get('win_rate_pct', 0)}",
          icon=":material/verified:", help=h("win_rate"))
m4.metric("İşlem sayısı", bt.get("total_trades", 0),
          icon=":material/format_list_numbered:", help=h("trades"))
m5.metric("Maks. düşüş", f"%{bt.get('max_drawdown_pct', 0)}",
          icon=":material/trending_down:", help=h("max_drawdown"))

r1, r2, r3, r4 = st.columns(4)
r1.metric("Sharpe", f"{bt.get('sharpe_ratio', 0):.2f}", icon=":material/equalizer:", help=h("sharpe"))
r2.metric("Sortino", f"{bt.get('sortino_ratio', 0):.2f}", icon=":material/equalizer:", help=h("sortino"))
r3.metric("Calmar", f"{bt.get('calmar_ratio', 0):.2f}", icon=":material/equalizer:", help=h("calmar"))
exit_trades = [t for t in bt.get("trades", []) if str(t.get("type", "")).startswith("EXIT")]
gross_win = sum(t.get("pnl_pct", 0) for t in exit_trades if t.get("pnl_pct", 0) > 0)
gross_loss = abs(sum(t.get("pnl_pct", 0) for t in exit_trades if t.get("pnl_pct", 0) < 0))
profit_factor = gross_win / gross_loss if gross_loss else 0.0
r4.metric("Kâr faktörü", f"{profit_factor:.2f}", icon=":material/scale:", help=h("profit_factor"))

benchmark = bist100_benchmark()
if benchmark:
    alpha = float(bt.get("total_return_pct", 0)) - benchmark["total_return_pct"]
    b1, b2, b3 = st.columns(3)
    b1.metric(
        "BIST 100 getirisi", f"%{benchmark['total_return_pct']:+.2f}",
        icon=":material/show_chart:", help=h("benchmark"),
    )
    b2.metric(
        "Strateji farkı (alpha)", f"%{alpha:+.2f}",
        icon=":material/trending_up:" if alpha >= 0 else ":material/trending_down:",
        help="Strateji getirisi eksi BIST 100 getirisi. Pozitif değer endeksi yendiği anlamına gelir.",
    )
    b3.metric(
        "Endeks son değer", f"{benchmark['last']:,.2f}",
        delta=f"%{benchmark['cagr_pct']:+.2f}/yıl",
        icon=":material/leaderboard:", help=h("benchmark"),
    )

with st.expander("İşlem geçmişi", icon=":material/history:"):
    components.trades_table(bt)

with st.expander("Son fiyat verileri", icon=":material/table:"):
    tail = df.tail(30).reset_index()
    tail = tail.rename(columns={tail.columns[0]: "Tarih"})
    st.dataframe(tail, hide_index=True, alt=f"{symbol} son 30 günlük OHLCV verisi")

if is_us_symbol(symbol):
    with st.expander("Finnhub ek verisi (ABD hissesi)", icon=":material/api:"):
        quote = us_quote(symbol)
        if quote:
            q1, q2, q3 = st.columns(3)
            q1.metric("Finnhub fiyat", f"{quote['price']:,.2f}", help="Finnhub ücretsiz kotasyonu (ABD hisseleri).")
            q2.metric("Değişim", f"{quote['change_pct']:+.2f}%", help="Günlük yüzde değişim.")
            q3.metric("Önceki kapanış", f"{quote['prev_close']:,.2f}")
        else:
            st.caption("Finnhub bu sembol için veri dönmedi (ücretsiz plan BIST'i kapsamıyor).")
        news = us_news(symbol)
        if news:
            st.dataframe(
                [{"Başlık": n.get("headline", ""), "Kaynak": n.get("source", "")} for n in news],
                hide_index=True, alt="Finnhub ABD haberleri",
            )

st.caption(
    "Bu panel teknik analiz amaçlıdır; yatırım tavsiyesi değildir. "
    "Geçmiş performans gelecekteki getiriyi garanti etmez."
)
