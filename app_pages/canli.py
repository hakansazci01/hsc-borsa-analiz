"""Canlı işlem masası: gerçek BIST verisi, KAP haberleri ve anlık AL/BEKLE/SAT kararı."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from ui import autonomous, binance_bot, binance_tr_bot, broker, components, live_bot, live_guard, quant_lab, tr_monitor, tr_scalper
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
            st.subheader("İnternet verileri · KAP haberleri", divider="gray")
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

# ---- GERÇEK PARA: varsayılan olarak tamamen kilitli ----
with st.expander("GERÇEK PARA emir (varsayılan KAPALI)", icon=":material/lock:"):
    st.error(
        "Bu özellik **gerçek para** ile emir gönderebilir. Uygulama gerçek para için "
        "**onaylanmamıştır**; yasal/broker önkoşulları tamamlanmadan açmayın. "
        "Tüm kilitler sağlanmadan hiçbir ağ çağrısı yapılmaz.",
        icon=":material/warning:",
    )
    cfg_live = live_guard.config(settings)
    st.caption(
        "Kilit durumu: "
        + ("✅ açık" if cfg_live.get("enabled") else "❌ config.yaml live_trading.enabled = false")
        + " · "
        + ("✅ HSC_LIVE_ARMED=YES" if os.environ.get("HSC_LIVE_ARMED") == "YES"
           else "❌ HSC_LIVE_ARMED ortam değişkeni yok")
        + " · "
        + ("✅ canlı broker anahtarı var" if broker.live_configured()
           else "❌ canlı broker anahtarı yok")
    )
    phrase = st.text_input("Onay ifadesi", key="live_phrase", type="password")
    armed = st.checkbox("Oturumu gerçek emir için onaylıyorum", key="live_armed_session")
    qty_live = st.number_input(
        "Adet", min_value=0.0, value=0.0, step=1.0, key="live_qty",
        help=f"Tek emir limiti {float(cfg_live.get('max_order_tl', 5000)):,.0f} ₺",
    )
    last_live = (st.session_state.get("live_decisions") or [{}])[-1]
    price_live = float(last_live.get("Fiyat") or 0)
    decision_live = str(last_live.get("Karar") or "BEKLE")
    ok_live, reasons_live, _ = live_guard.check(
        st.session_state.user, symbol, qty_live, price_live,
        phrase=phrase, session_armed=armed, settings=settings,
    )
    if reasons_live:
        st.caption("Eksik kilitler: " + " · ".join(reasons_live))
    if st.button(
        "GERÇEK EMİR GÖNDER", icon=":material/send:", key="live_send",
        disabled=not ok_live, type="primary",
    ):
        result = live_bot.execute(
            st.session_state.user, symbol,
            decision_live, qty_live, price_live,
            phrase=phrase, session_armed=armed, settings=settings,
        )
        if result.get("ok"):
            st.success(f"Emir iletildi · broker ID {result.get('id')}", icon=":material/check:")
        else:
            st.warning(result.get("reason", "Emir gönderilmedi."), icon=":material/warning:")
        st.rerun()

    orders = live_bot.recent_orders(st.session_state.user, 10)
    st.dataframe(
        pd.DataFrame(orders) if orders else pd.DataFrame(
            [{"time": "—", "symbol": "—", "decision": "—", "ok": "—", "status": "—"}]
        ),
        hide_index=True,
        alt="Gerçek emir denemelerinin yerel kaydı (anahtar veya hassas veri içermez)",
    )

# ---- BINANCE (varsayılan TESTNET / sanal para) ----
with st.expander("Binance botu (varsayılan TESTNET — sanal para)", icon=":material/smart_toy:"):
    from ui.api_keys import render_binance_editor
    from ui.exchange_probe import render as render_probe

    render_probe()
    render_binance_editor()
    bcfg = binance_bot.cfg(settings)
    st.caption(
        "Binance API anahtarı **kullanıcı adı/şifre değildir**. Testnet için ayrı anahtar "
        "üretin (testnet.binance.vision), para çekme yetkisi vermeyin, IP kısıtlayın. "
        "Anahtarları sohbete yapıştırmayın; `.streamlit/secrets.toml` → `[binance]` bölümüne yazın."
    )
    st.caption(
        "Durum: "
        + ("✅ açık" if bcfg.get("enabled") else "❌ kapalı (binance.enabled)")
        + " · " + ("✅ testnet" if bcfg.get("testnet", True) else "⚠️ CANLI mod")
        + " · " + ("✅ anahtar var" if binance_bot.configured() else "❌ anahtar yok")
    )
    b_symbol = st.selectbox(
        "Sembol", [str(s).upper() for s in bcfg.get("allowed_symbols", ["BTCUSDT"])],
        key="bin_symbol",
    )
    if st.button("15m sinyal al", icon=":material/flash_on:", key="bin_signal"):
        sig = binance_bot.quick_signal(b_symbol)
        st.session_state["bin_last_signal"] = sig
    sig = st.session_state.get("bin_last_signal")
    if sig:
        st.caption(
            f"Sinyal: **{sig.get('decision')}** · fiyat {sig.get('price', 0):,.4f} USDT · "
            f"RSI {sig.get('rsi', '—')} · {sig.get('reason', '')}"
        )
    b_phrase = st.text_input("Onay ifadesi", key="bin_phrase", type="password")
    b_local_armed = st.checkbox(
        "Ortam kilidini yerel olarak aç (HSC_BINANCE_ARMED yerine)",
        value=binance_bot.is_local_armed(), key="bin_local_armed",
        help="Kısayoldan başlatırken ortam değişkeni ayarlanamıyorsa bunu kullanın.",
    )
    if b_local_armed != binance_bot.is_local_armed():
        binance_bot.set_local_armed(b_local_armed)
        st.rerun()
    b_armed = st.checkbox("Oturumu Binance emri için onaylıyorum", key="bin_armed_session")
    b_qty = st.number_input("Miktar", min_value=0.0, value=0.0, step=0.001, key="bin_qty")
    b_price = float((sig or {}).get("price") or 0)
    b_ok, b_reasons, _ = binance_bot.guard(
        b_symbol, b_qty, b_price, b_phrase, b_armed, settings
    )
    if b_reasons:
        st.caption("Eksik kilitler: " + " · ".join(b_reasons))
    decision_side = "buy" if (sig or {}).get("decision") == "AL" else "sell"
    if st.button(
        "BINANCE EMIR GONDER", icon=":material/send:", key="bin_send",
        disabled=not b_ok or not sig or sig.get("decision") == "BEKLE", type="primary",
    ):
        result = binance_bot.execute(
            st.session_state.user, b_symbol, decision_side, b_qty, b_price,
            b_phrase, b_armed, settings,
        )
        if result.get("ok"):
            st.success("Emir iletildi (testnet/sanal bakiye).", icon=":material/check:")
        else:
            st.warning(result.get("reason", "Emir gönderilmedi."), icon=":material/warning:")
        st.rerun()

with st.expander("Gate.io botu (erişilebilir — TESTNET / sanal para)", icon=":material/smart_toy:"):
    from ui.gateio_bot import cfg as gate_cfg
    from ui.gateio_bot import configured as gate_configured
    from ui.gateio_bot import execute as gate_execute
    from ui.gateio_bot import guard as gate_guard
    from ui.gateio_bot import is_local_armed as gate_armed
    from ui.gateio_bot import quick_signal as gate_signal
    from ui.gateio_bot import set_local_armed as gate_set_armed
    from ui.api_keys import render_gateio_editor

    render_gateio_editor()
    gcfg = gate_cfg(settings)
    st.caption(
        "Durum: " + ("✅ açık" if gcfg.get("enabled") else "❌ kapalı (gateio.enabled)")
        + " · " + ("✅ testnet" if gcfg.get("testnet", True) else "⚠️ CANLI")
        + " · " + ("✅ anahtar var" if gate_configured() else "❌ anahtar yok")
    )
    g_symbol = st.selectbox(
        "Sembol", [str(s).upper() for s in gcfg.get("allowed_symbols", ["BTC_USDT"])],
        key="gate_symbol",
    )
    if st.button("15m sinyal al", icon=":material/flash_on:", key="gate_signal"):
        st.session_state["gate_last_signal"] = gate_signal(g_symbol)
    gsig = st.session_state.get("gate_last_signal")
    if gsig:
        st.caption(
            f"Sinyal: **{gsig.get('decision')}** · fiyat {gsig.get('price', 0):,.4f} USDT · "
            f"RSI {gsig.get('rsi', '—')} · {gsig.get('reason', '')}"
        )
    g_phrase = st.text_input("Onay ifadesi", key="gate_phrase", type="password")
    g_local = st.checkbox(
        "Ortam kilidini yerel olarak aç", value=gate_armed(), key="gate_local_armed"
    )
    if g_local != gate_armed():
        gate_set_armed(g_local)
        st.rerun()
    g_session = st.checkbox("Oturumu Gate.io emri için onaylıyorum", key="gate_session")
    g_qty = st.number_input("Miktar", min_value=0.0, value=0.0, step=0.001, key="gate_qty")
    g_price = float((gsig or {}).get("price") or 0)
    g_ok, g_reasons, _ = gate_guard(g_symbol, g_qty, g_price, g_phrase, g_session, settings)
    if g_reasons:
        st.caption("Eksik kilitler: " + " · ".join(g_reasons))
    g_side = "buy" if (gsig or {}).get("decision") == "AL" else "sell"
    if st.button(
        "GATEIO EMIR GONDER", icon=":material/send:", key="gate_send",
        disabled=not g_ok or not gsig or gsig.get("decision") == "BEKLE", type="primary",
    ):
        result = gate_execute(
            st.session_state.user, g_symbol, g_side, g_qty, g_price,
            g_phrase, g_session, settings,
        )
        if result.get("ok"):
            st.success("Emir iletildi (testnet/sanal bakiye).", icon=":material/check:")
        else:
            st.warning(result.get("reason", "Emir gönderilmedi."), icon=":material/warning:")
        st.rerun()

# ---- BINANCE TR (gercek borsa, imza dogrulandi; emirler kilitle bloklu) ----
with st.expander("Binance TR botu (gerçek borsa — emirler kilitli)", icon=":material/smart_toy:"):
    from ui.api_keys import render_binance_tr_editor

    render_binance_tr_editor()
    trcfg = binance_tr_bot.cfg(settings)
    st.caption(
        "Binance TR, global Binance'den **ayrı borsadır** (`www.binance.tr`). "
        "Anahtarınız imzalı hesap sorgusunda **doğrulandı** (code 0). "
        "Fiyatlar ve mumlar **gerçek**; bakiye sizin hesabınızın gerçek bakiyesidir. "
        "Emir göndermek için aşağıdaki tüm kilitleri açmanız gerekir."
    )
    st.caption(
        "Durum: "
        + ("✅ açık" if trcfg.get("enabled") else "❌ kapalı (binance_tr.enabled)")
        + " · " + ("✅ anahtar var" if binance_tr_bot.configured() else "❌ anahtar yok")
        + " · " + ("✅ hesap doğrulandı" if binance_tr_bot.account_status().get("ok") else "❌ hesap sorgusu başarısız")
    )
    if st.button("Hesap durumunu sorgula (salt okunur)", key="btr_account"):
        status = binance_tr_bot.account_status()
        if status.get("ok"):
            st.success("Hesap bağlantısı OK. Gerçek bakiye bilgisi panelde gösterilmez.", icon=":material/check:")
            st.caption(f"Hesap alanları: {', '.join(status.get('fields', []))}")
        else:
            st.warning(status.get("reason", "Sorgu başarısız."), icon=":material/warning:")
    tr_symbol = st.selectbox(
        "Sembol", [str(s).upper() for s in trcfg.get("allowed_symbols", ["BTC_USDT"])],
        key="btr_symbol",
    )
    if st.button("15m sinyal al", icon=":material/flash_on:", key="btr_signal"):
        st.session_state["btr_last_signal"] = binance_tr_bot.quick_signal(tr_symbol)
    trsig = st.session_state.get("btr_last_signal")
    if trsig:
        st.caption(
            f"Sinyal: **{trsig.get('decision')}** · fiyat {trsig.get('price', 0):,.4f} USDT · "
            f"RSI {trsig.get('rsi', '—')} · {trsig.get('reason', '')}"
        )
    tr_phrase = st.text_input("Onay ifadesi", key="btr_phrase", type="password")
    tr_local = st.checkbox(
        "Ortam kilidini yerel olarak aç", value=binance_tr_bot.is_local_armed(), key="btr_local_armed"
    )
    if tr_local != binance_tr_bot.is_local_armed():
        binance_tr_bot.set_local_armed(tr_local)
        st.rerun()
    tr_session = st.checkbox("Oturumu Binance TR emri için onaylıyorum", key="btr_session")
    st.caption(
        "Canlı emir için ayrıca `HSC_BINANCE_TR_LIVE=YES` ortam değişkeni gerekir. "
        "Bu kilit kasıtlıdır; shortcuts ile başlatırken yerel kilit kutusunu kullanın."
    )
    tr_qty = st.number_input("Miktar", min_value=0.0, value=0.0, step=0.0001, key="btr_qty")
    tr_price = float((trsig or {}).get("price") or 0)
    tr_ok, tr_reasons, _ = binance_tr_bot.guard(
        tr_symbol, tr_qty, tr_price, tr_phrase, tr_session, settings
    )
    if tr_reasons:
        st.caption("Eksik kilitler: " + " · ".join(tr_reasons))
    tr_side = "buy" if (trsig or {}).get("decision") == "AL" else "sell"
    if st.button(
        "BINANCE TR EMIR GONDER", icon=":material/send:", key="btr_send",
        disabled=not tr_ok or not trsig or trsig.get("decision") == "BEKLE", type="primary",
    ):
        result = binance_tr_bot.execute(
            st.session_state.user, tr_symbol, tr_side, tr_qty, tr_price,
            tr_phrase, tr_session, settings,
        )
        if result.get("ok"):
            st.success("Emir iletildi (GERÇEK borsa, gerçek bakiye).", icon=":material/check:")
        else:
            st.warning(result.get("reason", "Emir gönderilmedi."), icon=":material/warning:")
        st.rerun()

# ---- BINANCE TR mikro-alsat motoru (CANLI ANALİZ) ----
with st.expander("CANLI ANALİZ — anlık alım/satım, kâr, süre, zarar", icon=":material/analytics:", expanded=True):
    st.caption(
        "**Kâr odaklı, sürekli çalışır:** hedef %0,80 · %0,40 üzerinde trailing stop · "
        "komisyonu kurtaran kilit stop · kârla büyüen pozisyon (₺20'ye kadar) · "
        "15 dk'dan uzun durgun pozisyon serbest bırakılır · azami ₺15 zarar · "
        "bakiyeye göre ₺50–100 pozisyon. "
        "Panel **5 saniyede bir yenilenir**; tüm sayılar gerçek "
        "Binance TR API'sinden gelir, tahmin/simülasyon değildir."
    )
    from pathlib import Path as _Path

    _running = tr_scalper.STOP_FILE.exists() is False
    st.caption("Motor durumu: **" + ("ÇALIŞIYOR ♻️" if _running else "DURDURULDU ⏹") + "**")
    st.warning(
        "⚠️ **Doğrulama sonucu:** 7 gerçek çift üzerinde 228 parametre kombinasyonunun "
        "**hiçbiri** komisyon sonrası pozitif çıkmadı (en iyisi -%0,098/işlem). "
        "Canlı pilot da **-₺0,069** net zarar verdi. Bu yüzden motor durduruldu; "
        "kârlı bir strateji doğrulanmadan parasını yatırmak risklidir. "
        "Detay: `docs/STRATEJI_ARASTIRMA_SONUCU.md`.",
        icon=":material/warning:",
    )

    @st.fragment(run_every="5s")
    def _live_panel():
        m = tr_monitor.live_metrics()
        s = tr_monitor.summary()
        pos = m["position"]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric(
            "Anlık K/Z (açık)",
            f"{pos['pnl']:+.2f} ₺" if pos else "—",
            delta=f"{pos['pct']:+.2f}%" if pos else None,
        )
        k2.metric("Gerçekleşen net K/Z", f"{s['net_pnl']:+.2f} ₺")
        k3.metric("Geçen süre", pos["elapsed"] if pos else "—")
        k4.metric("İşlem / Kazanma", f"{s['trades']} / %{s['win_rate']:.0f}")

        if pos:
            st.markdown(f"#### {pos['symbol']} · açık pozisyon")
            a, b, c, d = st.columns(4)
            a.metric("Alınan miktar", f"{pos['qty']}")
            b.metric("Alış fiyatı", f"{pos['entry']:,.4f} ₺")
            c.metric("Anlık fiyat", f"{pos['price']:,.4f} ₺" if pos["price"] else "—")
            d.metric("Maliyet / Değer", f"{pos['cost']:.2f} → {pos['value']:.2f} ₺")
            st.caption(
                f"Emir ID **{pos['order_id']}** · başlangıç {pos['entry_time']} · "
                f"tahmini komisyon {pos['fee_est']:.3f} ₺"
            )
            st.progress(pos["progress"], text=(
                f"KİLİTLİ STOP {pos['effective_sl']:,.4f}  ◀──  giriş {pos['entry']:,.4f}  "
                f"──▶  HEDEF {pos['tp']:,.4f}  · zirve {pos['peak']:,.4f}"
            ))
        else:
            st.info("Açık pozisyon yok — motor AL sinyali bekliyor.", icon=":material/info:")

        st.markdown("##### Bakiyeye uygun tüm çiftlerin anlık durumu")

        @st.cache_data(ttl=60)
        def _live_pairs():
            return tr_scalper.tradeable_pairs()

        rows = []
        for sym in _live_pairs():
            sig = tr_scalper.signal(sym)
            rows.append({
                "Çift": sym, "Fiyat": sig.get("price"),
                "RSI7": sig.get("rsi"), "Karar": sig.get("decision"),
                "Neden": sig.get("reason"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        snaps = tr_monitor.recent_snapshots(180)
        pos_snaps = [x for x in snaps if x.get("symbol")]
        if len(pos_snaps) > 2:
            chart = pd.DataFrame([{
                "Zaman": datetime.fromtimestamp(x["ts"]).strftime("%H:%M:%S"),
                "Kâr %": x.get("pct", 0),
            } for x in pos_snaps]).set_index("Zaman")
            st.line_chart(chart, height=140)

        if m["history"]:
            st.markdown("##### Kapanmış işlemler (komisyon sonrası)")
            cols = ["symbol", "qty", "entry", "exit", "gross_pnl", "fee",
                    "net_pnl", "duration_sec", "reason", "exit_time"]
            frame = pd.DataFrame(m["history"])
            frame = frame[[c for c in cols if c in frame.columns]]
            frame = frame.rename(columns={
                "symbol": "Çift", "qty": "Adet", "entry": "Alış", "exit": "Satış",
                "gross_pnl": "Brüt K/Z", "fee": "Komisyon", "net_pnl": "Net K/Z",
                "duration_sec": "Süre (sn)", "reason": "Neden", "exit_time": "Zaman",
            })
            st.dataframe(frame.tail(8), use_container_width=True, hide_index=True)

        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Kazanan", s["wins"])
        g2.metric("Kaybeden", s["losses"])
        g3.metric("Toplam komisyon", f"{s['fees']:.3f} ₺")
        g4.metric("Ort. süre", f"{s['avg_seconds']:.0f} sn")
        st.caption(
            f"En iyi işlem **{s['best']:+.2f} ₺** · en kötü işlem **{s['worst']:+.2f} ₺** · "
            f"azami zarar sınırı ₺15, işlem sayısı sınırı yok (sürekli çalışır)."
        )

    _live_panel()

    ctrl1, ctrl2 = st.columns(2)
    if ctrl1.button("MOTORU BAŞLAT (kalıcı)", icon=":material/play_arrow:", key="scalper_start",
                    disabled=tr_scalper.STOP_FILE.exists() is False and
                    (tr_scalper.STOP_FILE.parent / "TR_SCALPER_RUN").exists()):
        import subprocess
        import sys
        from pathlib import Path as _P

        root = _P(__file__).resolve().parent.parent
        venv_py = root / ".venv" / "Scripts" / "python.exe"
        exe = str(venv_py) if venv_py.exists() else sys.executable
        subprocess.Popen(
            [exe, "-m", "ui.tr_runner"], cwd=str(root),
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        st.success("Kalıcı motor başlatıldı. Bilgisayar açık olduğu sürece çalışır.",
                   icon=":material/check:")
        st.rerun()
    if ctrl2.button("MOTORU DURDUR", icon=":material/stop:", key="scalper_stop",
                    type="primary", disabled=tr_scalper.STOP_FILE.exists()):
        tr_scalper.STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        tr_scalper.STOP_FILE.write_text("stopped", encoding="utf-8")
        st.warning("Durdurma sinyali verildi. Motor bir sonraki 15 saniyelik turda duracak.",
                   icon=":material/warning:")
        st.rerun()

# ---- OTONOM YÖNETİCİ ----
with st.expander("OTONOM YÖNETİCİ — sürekli analiz, kendini test eder", icon=":material/psychology:"):
    st.caption(
        "Saatte bir gerçek veriyi tarar, öngörüsünü gerçekleşen fiyatla karşılaştırır. "
        "**Yalnızca** doğrulanmış kârlı edge + yukarı rejim + yeterli isabet varsa motoru "
        "kendiliğinden açar; aksi halde kapalı tutar. Sizin müdahaleniz gerekmez."
    )
    _as = autonomous._load()
    _last = _as.get("last_decision", {})
    _acc = autonomous.accuracy(_as)
    _gov_alive = autonomous.LOCK.exists() and autonomous.tr_runner._pid_alive(
        int(autonomous.LOCK.read_text(encoding="utf-8").strip() or 0)
    ) if autonomous.LOCK.exists() else False
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Yönetici", "ÇALIŞIYOR ♻️" if _gov_alive else "DURDU ⏹")
    m2.metric("Son karar", _last.get("decision", "—"))
    m3.metric("Öngörü isabeti", f"%{_acc['rate']}" if _acc["rate"] is not None else "—",
              help=f"{_acc['n']} test")
    try:
        _hb = json.loads(autonomous.HEARTBEAT.read_text(encoding="utf-8"))
        _age = int(time.time() - float(_hb.get("ts", 0)))
    except Exception:
        _hb, _age = {}, 999999
    m4.metric("Son nabız", f"{_age} sn önce",
              help="Sistem her 60 saniyede nabız atar; 300 sn üstü = sorun")
    if _age > 300:
        st.error("⚠️ Yönetici nabzı 5 dakikadan eski — sistem çalışmıyor olabilir. "
                 "Paneldeki **YÖNETİCİYİ BAŞLAT** düğmesine basın.", icon=":material/error:")
    else:
        st.caption(f"✅ Canlı nabız: **{_hb.get('at', '—')}** · PID **{_hb.get('pid', '—')}** · "
                   f"son analiz **{_hb.get('last_analysis', '—')}**")
    if _last:
        st.caption(
            f"Son analiz **{_last.get('at', '—')}** · rejim **{_last.get('regime', '—')}** · "
            f"doğrulanmış edge **{_last.get('robust', 0)}**"
        )
        if _last.get("reasons"):
            st.caption("Kapalı kalma nedenleri: " + " · ".join(_last["reasons"]))
    tests = _as.get("prediction_tests", [])
    if tests:
        st.markdown("##### Öngörü self-test (gerçekleşen fiyata göre)")
        st.dataframe(pd.DataFrame(tests).tail(8), use_container_width=True, hide_index=True)
    hgit = _as.get("decisions", [])
    if hgit:
        st.caption(f"Toplam {len(hgit)} otonom karar kaydedildi.")
    gc1, gc2 = st.columns(2)
    if gc1.button("YÖNETİCİYİ BAŞLAT", key="autonomous_start", icon=":material/play_arrow:"):
        import subprocess

        root = Path(__file__).resolve().parent.parent
        exe = str(root / ".venv" / "Scripts" / "python.exe")
        if not Path(exe).exists():
            exe = sys.executable
        subprocess.Popen(
            [exe, "-m", "ui.autonomous_runner"], cwd=str(root),
            creationflags=0x00000008 | 0x00000200,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        st.success("Otonom yönetici başlatıldı.", icon=":material/check:")
        st.rerun()
    if gc2.button("YÖNETİCİYİ DURDUR", key="autonomous_stop", icon=":material/stop:"):
        from pathlib import Path as _P2

        lk = _P2(autonomous.LOCK)
        if lk.exists():
            try:
                pid = int(lk.read_text(encoding="utf-8").strip() or 0)
                if pid:
                    import psutil

                    psutil.Process(pid).terminate()
            except Exception:
                pass
            lk.unlink(missing_ok=True)
        st.warning("Otonom yönetici durduruldu.", icon=":material/warning:")
        st.rerun()
    if st.button("ŞİMDİ ANALİZ ET", key="autonomous_now", icon=":material/refresh:"):
        with st.spinner("Gerçek veriler analiz ediliyor..."):
            d = autonomous.run_once()
        st.caption(f"Karar: **{d['decision']}** — " + ("; ".join(d["reasons"]) or "edge doğrulandı"))
        st.rerun()

# ---- KANTİTATİF ARAŞTIRMA ----
with st.expander("Kantitatif doğrulama — gerçek veride edge var mı?", icon=":material/science:"):
    st.caption(
        "7 coin × 3 zaman diliminde gerçek Binance verisi, %0,2 komisyon, "
        "iç/dış örneklem ayrımı. Eğitimde iyi çıkıp testte çöken stratejiler "
        "**doğrulanmış sayılmaz**. Sonuç iddia değil ölçümdür."
    )

    q = st.session_state.get("quant_result")
    if st.button("Araştırmayı çalıştır", key="quant_run", icon=":material/play_arrow:"):
        with st.spinner("Gerçek veriler taranıyor..."):
            st.session_state["quant_result"] = quant_lab.research()
        q = st.session_state["quant_result"]
    if q is None:
        st.info("Henüz çalıştırılmadı. Yukarıdaki düğmeyle gerçek verileri tarayın.",
                icon=":material/info:")
    elif not q.get("ok"):
        st.warning(q.get("reason", "Veri yok"), icon=":material/warning:")
    else:
        r = q["regime"]
        st.metric("Piyasa rejimi (BTC 4s)", r.get("name", "—"),
                  delta=f"{r.get('dist_pct', 0):+.1f}% EMA100'den" if r.get("price") else None)
        a, b, c = st.columns(3)
        a.metric("Gerçek seri", q["series"])
        b.metric("Test edilen kombinasyon", q["combinations"])
        c.metric("Doğrulanmış kârlı", q["robust_count"])
        best = q["best_train"]
        st.caption(
            f"Eğitimde en iyi: **{best['key']}** → eğitim **%{best['train']:+.2f}**, "
            f"dış örneklem **%{best['test']:+.2f}**"
        )
        if q["robust_count"] == 0:
            st.error("**Karar: " + q["verdict"] + ".** Motor kapalı kalır.", icon=":material/block:")
        else:
            st.warning("Karar: " + q["verdict"], icon=":material/warning:")

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
