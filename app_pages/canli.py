"""Canlı işlem masası: gerçek BIST verisi, KAP haberleri ve anlık AL/BEKLE/SAT kararı."""

from __future__ import annotations

from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from ui import components
from ui.bist_universe import load_companies, ordered_symbols, search_symbols
from ui.components import real_money_warning
from ui.help_texts import h
from ui.live_data import STRATEGIES, get_live_snapshot, scan_bist
from ui.market_session import status as session_status
from ui.order_ticket import build_ticket, render_ticket
from ui.paper import open_position
from ui.risk_engine import REGIME_COLORS, adjust_decision_for_regime, detect_regime
from ui.signal_display import render_signal_panel
from ui.stream import is_stream_alive
from ui.trade_engine import build_decision


settings = st.session_state.settings
if "live_decisions" not in st.session_state:
    st.session_state.live_decisions = []

universe = load_companies()
st.subheader("Canlı işlem masası", divider="gray")
st.caption(
    f"BIST'te kayıtlı **{len(universe)} şirket** otomatik yüklenir. Seçtiğiniz hisse için gerçek fiyat "
    "(WebSocket akışı), KAP bildirimleri ve 9 zaman dilimindeki teknik sinyaller anında analiz edilir. "
    "Ücretsiz akış ~15 dakika gecikmelidir. Panel **aracı kuruma emir göndermez**, karar desteği sağlar."
)

query = st.text_input(
    "Hisse ara (sembol veya şirket adı)",
    placeholder="Örn. THYAO, banka, asel",
    key="live_search",
    help=h("bist_search"),
)
options = search_symbols(universe, query)
if not options:
    options = ordered_symbols(universe)[:60]

controls = st.container(horizontal=True, vertical_alignment="bottom")
with controls:
    symbol = st.selectbox(
        "BIST sembolü",
        options=options,
        format_func=lambda s: f"{s} · {universe.get(s, s)}",
        key="live_symbol",
        help=h("bist_search"),
    )
    strategy = st.segmented_control(
        "Strateji", list(STRATEGIES), key="live_strategy", default="Dengeli", help=h("strategy")
    )
    news_weight = st.slider(
        "Haber etkisi %", 0, 50, 25, 5, key="live_news_weight",
        help=h("news_weight"),
    )
    auto_refresh = st.toggle("Otomatik yenile", value=True, key="live_auto", help=h("auto_refresh"))
    if st.button("Anlık analiz", icon=":material/bolt:", key="live_instant", help=h("instant_analysis")):
        get_live_snapshot.clear()
        detect_regime.clear()
        st.rerun()

st.caption(
    f"Canlı akış: {'bağlı' if is_stream_alive() else 'yedek mod'} · "
    "Kaynaklar: TradingView WebSocket + KAP + borsapy"
)
real_money_warning(compact=True)


def _render_panel(symbol: str, strategy: str, news_weight: int, risk: dict) -> None:
    try:
        snap = get_live_snapshot(symbol)
    except Exception as exc:
        st.error(f"{symbol} için canlı veri alınamadı: {exc}", icon=":material/error:")
        return

    decision = build_decision(snap, strategy, risk, news_weight / 100.0)
    try:
        regime = detect_regime(symbol)
        decision = adjust_decision_for_regime(decision, regime)
    except Exception:
        regime = None
    info = snap.get("info", {})
    fetched = snap.get("fetched_at")
    fetched_text = fetched.strftime("%d.%m.%Y %H:%M:%S") if isinstance(fetched, datetime) else "—"

    with st.container(horizontal=True, horizontal_alignment="right"):
        session = str(info.get("session") or "—")
        session_tr = {"regular": "Seans açık", "out_of_session": "Seans kapalı", "premarket": "Seans öncesi"}.get(session, session)
        st.caption(
            f"Son veri: **{fetched_text}** · Fiyat: **{snap.get('quote_source', '—')}** · "
            f"Seans: **{session_tr}** · Kotasyon saati: **{info.get('quote_time') or '—'}**"
        )
        if st.button("Şimdi yenile", icon=":material/refresh:", key="live_refresh", help=h("instant_analysis")):
            get_live_snapshot.clear()
            st.rerun()

    if snap.get("errors"):
        with st.expander("Veri uyarıları", icon=":material/warning:"):
            for err in snap["errors"]:
                st.caption(f"- {err}")

    # ---- Karar kartı ----
    with st.container(border=True, key="decision_card"):
        d = decision["decision"]
        st.subheader(f"{symbol} · {decision['name']}", divider="gray")
        if regime:
            st.badge(
                f"Rejim: {regime['regime']}",
                color=REGIME_COLORS.get(regime["regime"], "gray"),
                help=h("regime"),
            )
        render_signal_panel(decision, snap, decision.get("volatility_pct"))
        st.caption(
            f"Strateji: {strategy} · Teknik skor: {decision['technical']['score']:+.2f} · "
            f"Haber skoru: {decision['news']['score']:+.2f} · Karar skoru: {decision['score']:+.2f}"
            + (f" · Rejim güveni: %{regime['confidence']}" if regime else "")
        )
        if regime:
            st.caption(f"Rejim uyarlaması: {regime['advice']}")

        if decision["reasons"]:
            st.markdown("**Karar gerekçeleri**")
            for reason in decision["reasons"][:8]:
                icon = ":material/arrow_upward:" if reason["tone"] == "positive" else (
                    ":material/arrow_downward:" if reason["tone"] == "negative" else ":material/remove:"
                )
                st.markdown(f"- {icon} **{reason['source']}:** {reason['text']}")
        else:
            st.caption("Teknik sinyal veya haber bulunamadı; karar nötr kabul edildi.")

        if d in ("AL", "SAT"):
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Giriş fiyatı", f"{decision['price']:,.2f}",
                      icon=":material/login:", help=h("last_close"))
            c2.metric("Stop", f"{decision['stop']:,.2f}",
                      icon=":material/shield:", help=h("stop_loss"))
            c3.metric("Hedef", f"{decision['target']:,.2f}",
                      icon=":material/flag:", help=h("take_profit"))
            c4.metric("Önerilen pozisyon", f"%{decision['position_pct']}",
                      icon=":material/pie_chart:", help=h("position_size"))

    # ---- Özet metrikler ----
    with st.container(key="live_market"):
        intraday_data = snap.get("intraday")
        price_spark = (
            intraday_data["Close"].tail(40).astype(float).tolist()
            if intraday_data is not None and not getattr(intraday_data, "empty", True)
            else []
        )
        k1, k2, k3, k4 = st.columns(4)
        k1.metric(
            "Son fiyat", f"{info.get('price') or 0:,.2f} ₺",
            delta=f"{decision['change_pct']:+.2f}%",
            icon=":material/show_chart:", chart_data=price_spark or None,
            chart_type="line", help=h("last_close"),
        )
        vol = info.get("volume")
        k2.metric("Hacim", f"{vol:,.0f}" if vol else "—",
                  icon=":material/bar_chart:", help=h("volume"))
        k3.metric("Gün aralığı", f"{info.get('low') or 0:,.2f} - {info.get('high') or 0:,.2f}",
                  icon=":material/swap_vert:", help=h("last_close"))
        k4.metric("5 dk oynaklık", f"%{decision['volatility_pct']}" if decision["volatility_pct"] else "—",
                  icon=":material/bolt:", help=h("volatility"))

    # ---- Grafik / sinyaller / haberler ----
    left, right = st.columns([1.4, 1], gap="medium")
    with left:
        with st.container(border=True):
            st.subheader("Gün içi fiyat (5 dk)", divider="gray")
            intraday = snap.get("intraday")
            if intraday is not None and not getattr(intraday, "empty", True):
                dframe = intraday.reset_index()
                dframe = dframe.rename(columns={dframe.columns[0]: "Tarih"})
                dframe["Tarih"] = pd.to_datetime(dframe["Tarih"])
                chart = (
                    alt.Chart(dframe.tail(130))
                    .mark_line(color="#60A5FA", strokeWidth=1.8)
                    .encode(
                        x=alt.X("Tarih:T", title=None),
                        y=alt.Y("Close:Q", title="Fiyat (₺)", scale=alt.Scale(zero=False)),
                        tooltip=[
                            alt.Tooltip("Tarih:T", title="Saat", format="%d.%m %H:%M"),
                            alt.Tooltip("Close:Q", title="Kapanış", format=",.2f"),
                        ],
                    )
                    .properties(height=250)
                    .interactive()
                )
                st.altair_chart(chart, alt=f"{symbol} gün içi 5 dakikalık fiyat grafiği")
            else:
                st.caption("Gün içi veri bulunamadı.")
        with st.container(border=True):
            st.subheader("Zaman dilimi sinyalleri", divider="gray")
            tf = pd.DataFrame(decision["technical"]["timeframes"])
            if not tf.empty:
                def _tf_color(val: str) -> str:
                    palette = {
                        "Güçlü AL": "#065F46", "AL": "#059669", "Nötr": "#475569",
                        "SAT": "#DC2626", "Güçlü SAT": "#991B1B",
                    }
                    return f"background-color: {palette.get(val, '#475569')}; color: white; font-weight: 600;"
                st.dataframe(
                    tf.style.map(_tf_color, subset=["recommendation"]),
                    hide_index=True,
                    column_config={
                        "timeframe": st.column_config.TextColumn("Zaman", help=h("timeframe")),
                        "recommendation": st.column_config.TextColumn("Sinyal", help=h("recommendation")),
                        "buy": st.column_config.NumberColumn("AL", help="Bu zaman dilimindeki AL yönlü gösterge sayısı."),
                        "sell": st.column_config.NumberColumn("SAT", help="Bu zaman dilimindeki SAT yönlü gösterge sayısı."),
                        "neutral": st.column_config.NumberColumn("Nötr", help="Yön vermeyen gösterge sayısı."),
                        "weight": st.column_config.NumberColumn("Ağırlık", help=h("weight")),
                    },
                    alt="Zaman dilimlerine göre teknik alım satım sinyalleri",
                )
    with right:
        with st.container(border=True):
            st.subheader("Internet verileri · KAP haberleri", divider="gray")
            news_items = decision["news"]["items"]
            if news_items:
                news_df = pd.DataFrame(news_items)[["date", "title", "tone"]]
                news_df = news_df.rename(columns={"date": "Tarih", "title": "Başlık", "tone": "Etki"})
                news_df["Etki"] = news_df["Etki"].map(
                    {"positive": "OLUMLU", "negative": "OLUMSUZ", "neutral": "NÖTR"}
                )
                st.dataframe(
                    news_df,
                    hide_index=True,
                    column_config={
                        "Başlık": st.column_config.TextColumn(width="large", help=h("news")),
                        "Etki": st.column_config.TextColumn(help=h("news_impact")),
                        "Tarih": st.column_config.TextColumn(help="KAP bildiriminin yayın tarihi."),
                    },
                    height=310,
                    alt="KAP ve şirket haberleri ile duyarım etkileri",
                )
                links = [i for i in news_items if i["url"]][:5]
                if links:
                    st.caption("Haber bağlantıları")
                    for item in links:
                        st.markdown(f"- [{item['title'][:60]}]({item['url']})")
            else:
                st.caption("Bu sembol için güncel haber bulunamadı.")

    # ---- Manuel emir taslağı ----
    with st.expander("Manuel emir taslağı (broker'a elle giriş için)", icon=":material/receipt:"):
        ticket = build_ticket(decision, snap, risk, settings["profile"])
        render_ticket(ticket)
        session = session_status()
        if not session["in_session"]:
            st.caption(f":material/warning: {session['detail']} Kurgusal işlem yalnızca seans içinde açılabilir.")
        if ticket["qty"] > 0 and st.button(
            "Kurgusal pozisyon aç",
            key=f"paper_open_live_{symbol}",
            icon=":material/add_circle:",
            disabled=not session["in_session"],
            help="Sinyali kurgusal portföyünüze ekler; gerçek emir gönderilmez. Yalnızca seans içinde.",
        ):
            open_position(
                st.session_state.user, symbol, ticket["qty"], ticket["price"],
                ticket["stop"], ticket["target"], decision.get("confidence", 0),
                f"Canlı sinyal: {decision['decision']}",
            )
            st.toast(
                f"{symbol} kurgusal pozisyon açıldı. SAT önerilerini Hesabım sayfasında görebilirsiniz.",
                icon=":material/check:",
            )

    # ---- Karar geçmişi ----
    hist = st.session_state.live_decisions
    last = hist[-1] if hist else None
    now = datetime.now()
    if (
        not last
        or last["Sembol"] != symbol
        or last["Karar"] != d
        or (now - last["time"]).total_seconds() > 300
    ):
        hist.append({
            "Zaman": now.strftime("%H:%M:%S"),
            "Sembol": symbol,
            "Karar": d,
            "Güven": decision["confidence"],
            "Fiyat": decision["price"],
            "time": now,
        })
        st.session_state.live_decisions = hist[-30:]

    with st.expander("Bu oturumdaki kararlar", icon=":material/history:"):
        log = pd.DataFrame(
            [{k: v for k, v in h.items() if k != "time"} for h in reversed(st.session_state.live_decisions)]
        )
        if not log.empty:
            st.dataframe(log, hide_index=True, alt="Oturum boyunca üretilen AL SAT kararları")


if auto_refresh:
    @st.fragment(run_every="60s")
    def _auto_panel(sym: str, strat: str, weight: int, risk: dict) -> None:
        _render_panel(sym, strat, weight, risk)

    _auto_panel(symbol, strategy or "Dengeli", news_weight, settings["risk"])
else:
    _render_panel(symbol, strategy or "Dengeli", news_weight, settings["risk"])

# ---- BIST hızlı tarama ----
with st.expander("BIST hızlı tarama (günlük teknik sinyal)", icon=":material/radar:"):
    st.caption(
        "Popüler BIST hisselerinin günlük teknik AL/SAT sinyallerini listeler. "
        "Tarama 2 dakika süreyle önbelleğe alınır."
    )
    if st.button("Taramayı çalıştır", icon=":material/play_arrow:", key="bist_scan_run"):
        rows = scan_bist(tuple(ordered_symbols(universe)[:30]))
        scan_df = pd.DataFrame(rows, columns=["Sembol", "Şirket", "Sinyal"])
        scan_df = scan_df.sort_values(
            "Sinyal",
            key=lambda s: s.map({"STRONG_BUY": 0, "BUY": 1, "NEUTRAL": 2, "SELL": 3, "STRONG_SELL": 4}).fillna(5),
        )
        st.dataframe(
            scan_df,
            hide_index=True,
            alt="BIST hisselerinin günlük teknik sinyal taraması",
        )
        st.caption("Anlık fiyat ve ayrıntılı karar için yukarıdan bir sembol seçin.")
    else:
        st.caption("Listeyi görmek için **Taramayı çalıştır** düğmesine basın.")

st.caption(
    "Uyarı: Bu araç yatırım tavsiyesi değildir. Ücretsiz veri gecikmeli olabilir; "
    "gerçek işlem öncesi güncel fiyat ve KAP bildirimlerini kontrol edin."
)
