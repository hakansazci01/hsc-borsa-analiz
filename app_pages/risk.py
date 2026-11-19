"""Akıllı Risk & Rejim Merkezi — rejim tespiti, Kelly boyutlandırma, Monte Carlo ve portföy riski."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.bist_universe import load_companies, ordered_symbols
from ui.core import analysis_args, analyze_symbol
from ui.help_texts import h
from ui.live_data import BIST_SYMBOLS
from ui.risk_engine import (
    REGIME_COLORS, REGIME_ICONS, adjust_decision_for_regime, detect_regime,
    kelly_sizing, monte_carlo, portfolio_risk,
)


settings = st.session_state.settings
universe = load_companies()
symbols = ordered_symbols(universe)
st.subheader("Akıllı risk ve rejim merkezi", divider="gray")
st.caption(
    "Kurumsal sistemlerde kullanılan dört yöntem tek panelde: piyasa rejimi tespiti, "
    "kesirli Kelly ile pozisyon boyutu, Monte Carlo ile zarar olasılığı ve portföy risk katkısı. "
    "Tüm hesaplamalar şeffaftır ve yatırım tavsiyesi değildir."
)

section = st.segmented_control(
    "Bölüm",
    ["Rejim analizi", "Kelly pozisyon", "Monte Carlo", "Portföy riski"],
    key="risk_section",
    help="Rejim: piyasa durumu · Kelly: pozisyon büyüklüğü · Monte Carlo: zarar olasılığı · Portföy: korelasyon ve risk katkısı.",
)

symbol = st.selectbox(
    "BIST sembolü", symbols,
    format_func=lambda s: f"{s} · {universe.get(s, BIST_SYMBOLS.get(s, s))}",
    key="risk_symbol", help=h("bist_search"),
)


def _yahoo_symbol(raw: str) -> str:
    s = raw.strip().upper()
    if "." in s:
        return s
    # universe ~800 BIST hissesini içerir; curated sözlükle sınırlamak
    # çoğu sembol için geçersiz Yahoo sembolü üretiyordu.
    return s + ".IS" if s in universe and s != "BIST100" else s


args = analysis_args(settings)

if section == "Rejim analizi":
    try:
        regime = detect_regime(symbol)
    except Exception as exc:
        st.error(f"Rejim tespiti başarısız: {exc}", icon=":material/error:")
        st.stop()

    with st.container(border=True):
        with st.container(horizontal=True, wrap=True, vertical_alignment="bottom"):
            st.badge(
                regime["regime"], color=REGIME_COLORS[regime["regime"]],
                icon=REGIME_ICONS[regime["regime"]],
            )
            st.markdown(f"### {symbol} · {universe.get(symbol, BIST_SYMBOLS.get(symbol, symbol))}")
            st.metric("Rejim güveni", f"%{regime['confidence']}", help=h("regime_confidence"))
        st.write(regime["advice"])
        st.caption(
            "Yöntem: son 1 yılın günlük getirilerinden 21 günlük yıllık oynaklık serisi oluşturulur; "
            "1-Boyutlu k-means ile düşük/yüksek oynaklık kümeleri ayrılır. Trend; SMA50/SMA200 sıralaması, "
            "50 günlük eğim ve 20 günlük momentum ile puanlanır. Yüksek oynaklık baskın rejimi belirler."
        )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Trend skoru", f"{regime['trend_score']:+.2f}", icon=":material/trending_up:", help=h("trend_score"))
    m2.metric("20 günlük momentum", f"%{regime['momentum_20d_pct']:+.2f}", icon=":material/bolt:", help="Son 20 günlük getiri. Pozitif değer kısa vadeli yükseliş eğilimini gösterir.")
    m3.metric("50 günlük eğim", f"%{regime['slope_50d_pct']:+.2f}", icon=":material/show_chart:", help="50 günlük hareketli ortalamanın son 20 gündeki değişimi. Ana eğilimin yönünü gösterir.")
    m4.metric("Yıllık oynaklık", f"%{regime['volatility_annual_pct']}", icon=":material/equalizer:", help=h("volatility"))
    st.caption(
        f"Oynaklık kümeleri — düşük: %{regime['vol_low_center']} · "
        f"yüksek: %{regime['vol_high_center']} · mevcut: %{regime['volatility_annual_pct']}"
    )

    c1, c2 = st.columns([1.4, 1], gap="medium")
    with c1:
        with st.container(border=True):
            st.subheader("Oynaklık geçmişi (120 gün)", divider="gray")
            hist = pd.DataFrame({
                "Oynaklık %": regime["history"] * 100,
                "Düşük küme": regime["vol_low_center"],
                "Yüksek küme": regime["vol_high_center"],
            })
            st.line_chart(hist, alt="Son 120 günün yıllık oynaklık serisi ve rejim eşikleri")
    with c2:
        with st.container(border=True):
            st.subheader("Canlı karara etkisi", divider="gray")
            ysym = _yahoo_symbol(symbol)
            try:
                res = analyze_symbol(
                    ysym, args["period"], args["interval"], args["indicators"], args["weights"],
                    args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
                )
                from ui.trade_engine import build_decision
                fake_snap = {
                    "symbol": symbol, "name": universe.get(symbol, symbol),
                    "info": {"price": float(res["info"]["last_close"]), "change_pct": 0.0},
                    "signals": {}, "news": None, "intraday": None, "fetched_at": None, "errors": [],
                }
                base = build_decision(fake_snap, "Dengeli", settings["risk"])
                adj = adjust_decision_for_regime(base, regime)
                st.markdown(f"Ham karar: **{base['decision']}** (güven %{base['confidence']}, pozisyon %{base['position_pct']})")
                st.markdown(f"Rejime uyarlanmış: **{adj['decision']}** (güven %{adj['confidence']}, pozisyon %{adj['position_pct']})")
                st.caption("Bu uyarlama Canlı işlem sayfasındaki karara da uygulanır.")
            except Exception as exc:
                st.caption(f"Karar karşılaştırması hesaplanamadı: {exc}")

elif section == "Kelly pozisyon":
    ysym = _yahoo_symbol(symbol)
    try:
        res = analyze_symbol(
            ysym, args["period"], args["interval"], args["indicators"], args["weights"],
            args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
        )
    except Exception as exc:
        st.error(f"Backtest verisi alınamadı: {exc}", icon=":material/error:")
        st.stop()
    k = kelly_sizing(res["backtest"], settings["risk"])

    with st.container(border=True):
        st.subheader(f"{symbol} · Kesirli Kelly analizi", divider="gray")
        if not k["available"]:
            st.info(k["reason"], icon=":material/info:")
        else:
            st.caption(
                "Kelly formülü: f = W − (1−W)/R. W kazanma olasılığı, R ortalama kazanç / ortalama kayıp. "
                "Aşırı bahis riskine karşı **yarım Kelly** kullanılır ve işlem başına **%2 sert tavan** uygulanır."
            )
            m1, m2, m3, m4 = st.columns(4)
            trade_pnl = [
                float(t["pnl_pct"])
                for t in res["backtest"].get("trades", [])
                if str(t.get("type", "")).startswith("EXIT") and "pnl_pct" in t
            ]
            m1.metric("Kazanma oranı", f"%{k['win_rate_pct']}",
                      icon=":material/verified:", help=h("win_rate"))
            m2.metric("Ödeme oranı (R)", f"{k['payoff_ratio']:.2f}",
                      icon=":material/compare_arrows:", help="Ortalama kazancın ortalama kayba oranı. 2,0 kazançların kayıpların iki katı olduğunu gösterir.")
            m3.metric("Beklenti / işlem", f"%{k['expectancy_pct']:+.2f}",
                      icon=":material/calculate:", chart_data=trade_pnl or None,
                      chart_type="bar", help="Her işlemde beklenen ortalama getiri. Negatifse strateji uzun vadede zarar eder.")
            m4.metric("İşlem sayısı", k["trades"],
                      icon=":material/format_list_numbered:", help="Kelly hesabında kullanılan kapanmış backtest işleminin sayısı.")

            c1, c2 = st.columns([1, 1.2], gap="medium")
            with c1:
                st.dataframe(
                    pd.DataFrame([
                        {"Ölçü": "Ham Kelly", "Değer": f"%{k['kelly_pct']}"},
                        {"Ölçü": "Yarım Kelly", "Değer": f"%{k['half_kelly_pct']}"},
                        {"Ölçü": "Sert tavan", "Değer": f"%{k['hard_cap_pct']:.0f}"},
                        {"Ölçü": "Önerilen risk", "Değer": f"%{k['suggested_risk_pct']}"},
                        {"Ölçü": "Önerilen pozisyon", "Değer": f"%{k['suggested_position_pct']}"},
                        {"Ölçü": "Mevcut sabit pozisyon", "Değer": f"%{k['current_position_pct']}"},
                        {"Ölçü": "Önerilen tutar", "Değer": f"{k['suggested_amount']:,.0f}"},
                    ]),
                    hide_index=True, alt="Kelly kriteri pozisyon boyutlandırma sonuçları",
                )
            with c2:
                comp = pd.DataFrame({
                    "Seçenek": ["Mevcut sabit", "Kelly önerisi", "Risk tavanı"],
                    "Sermaye %": [k["current_position_pct"], k["suggested_position_pct"], 100 / max(int(settings["risk"]["max_positions"]), 1)],
                })
                st.bar_chart(comp, x="Seçenek", y="Sermaye %", alt="Mevcut ve Kelly önerilen pozisyon büyüklükleri")
            if k["kelly_pct"] <= 0:
                st.warning(
                    "Stratejinin bu hisse üzerindeki beklentisi negatif: Kelly payı sıfır. "
                    "Kurumsal yaklaşımda bu durumda işlem açılmaz; sinyal 'AL' bile olsa risk yönetimi devreye girer.",
                    icon=":material/gpp_maybe:",
                )
            st.caption(
                f"Ortalama kazanç %{k['avg_win_pct']}, ortalama kayıp %{k['avg_loss_pct']}. "
                f"Pozisyon, stop mesafesi ({settings['risk']['stop_loss_pct']*100:.0f}%) ve azami açık pozisyon "
                f"({settings['risk']['max_positions']}) sınırıyla da sınırlandırıldı."
            )

elif section == "Monte Carlo":
    ysym = _yahoo_symbol(symbol)
    try:
        res = analyze_symbol(
            ysym, args["period"], args["interval"], args["indicators"], args["weights"],
            args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
        )
    except Exception as exc:
        st.error(f"Backtest verisi alınamadı: {exc}", icon=":material/error:")
        st.stop()
    sims = st.slider("Simülasyon sayısı", 500, 5000, 2000, 500, key="mc_sims", help=h("simulations"))
    mc = monte_carlo(res["backtest"], settings["risk"], simulations=sims)

    with st.container(border=True):
        st.subheader(f"{symbol} · Monte Carlo risk projeksiyonu", divider="gray")
        if mc is None:
            st.info("Simülasyon için en az 3 kapanmış işlem gerekir.", icon=":material/info:")
        else:
            st.caption(
                f"{mc['trade_count']} geçmiş işlemin getirisi rastgele yeniden örneklenip "
                f"{mc['simulations']:,} olası gelecek senaryosu oluşturuldu (bootstrap, tohum=42). "
                f"Her senaryoda sermayenin %{mc['position_size_pct']}'i riske atıldı."
            )
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Zarar olasılığı", f"%{mc['prob_loss_pct']}", icon=":material/warning:", help=h("monte_carlo"))
            m2.metric("VaR %95", f"%{mc['var95_pct']}", icon=":material/shield:", help=h("var95"))
            m3.metric("CVaR %95", f"%{mc['cvar95_pct']}", icon=":material/gpp_maybe:", help=h("cvar95"))
            m4.metric("Medyan getiri", f"%{mc['median_return_pct']:+.2f}", icon=":material/percent:", help="Tüm senaryoların ortanca getirisi. Yarısı daha iyi, yarısı daha kötü sonuçlandı demektir.")

            m5, m6, m7 = st.columns(3)
            m5.metric("En iyi senaryo", f"%{mc['best_pct']:+.1f}", icon=":material/arrow_upward:", help="Simülasyonlar içindeki en yüksek getiri; tek bir iyimser senaryodur.")
            m6.metric("En kötü senaryo", f"%{mc['worst_pct']:+.1f}", icon=":material/arrow_downward:", help="Simülasyonlar içindeki en kötü getiri; kuyruk riskini gösterir.")
            m7.metric("Medyan maks. düşüş", f"%{mc['median_max_dd_pct']}", icon=":material/trending_down:", help=h("max_drawdown"))

            dist = pd.cut(pd.Series(mc["distribution"]), bins=36)
            hist = pd.DataFrame({
                "Getiri %": [interval.mid * 100 - 100 for interval in dist.cat.categories],
                "Senaryo": dist.value_counts().sort_index().values,
            })
            st.bar_chart(hist, x="Getiri %", y="Senaryo", alt="Monte Carlo simülasyonlarının getiri dağılımı")
            st.caption(
                "VaR %95: en kötü %5'lik dilimdeki kayıp. CVaR %95: o dilimin ortalaması "
                "(beklenen kayıp). Geçmiş işlem dağılımı geleceği garanti etmez."
            )

else:
    try:
        frames = []
        for sym in settings["symbols"]:
            r = analyze_symbol(
                sym, args["period"], args["interval"], args["indicators"], args["weights"],
                args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
            )
            close = r["df"]["Close"].astype(float)
            frames.append(close.pct_change().rename(sym))
        returns = pd.concat(frames, axis=1, sort=False)
        pr = portfolio_risk(returns)
    except Exception as exc:
        st.error(f"Portföy riski hesaplanamadı: {exc}", icon=":material/error:")
        st.stop()

    with st.container(border=True):
        st.subheader("İzleme listesi portföy riski", divider="gray")
        if pr is None:
            st.info("Korelasyon için en az 2 hisse ve 30 günlük ortak veri gerekir.", icon=":material/info:")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Portföy yıllık oynaklık", f"%{pr['portfolio_vol_pct']}", help=h("volatility"))
            m2.metric("Çeşitlendirme skoru", f"%{pr['diversification_score']}", help=h("diversification"))
            m3.metric("Ortalama korelasyon", f"{pr['avg_correlation']:.2f}", help=h("correlation"))

            c1, c2 = st.columns([1, 1], gap="medium")
            with c1:
                st.subheader("Korelasyon matrisi", divider="gray")
                corr_long = pr["correlation"].reset_index().melt(
                    id_vars="index", var_name="Hisse2", value_name="Korelasyon"
                ).rename(columns={"index": "Hisse1"})
                import altair as alt
                heat = (
                    alt.Chart(corr_long)
                    .mark_rect()
                    .encode(
                        x=alt.X("Hisse1:N", title=None),
                        y=alt.Y("Hisse2:N", title=None),
                        color=alt.Color(
                            "Korelasyon:Q",
                            scale=alt.Scale(domain=[-1, 1], scheme="redyellowgreen"),
                        ),
                        tooltip=["Hisse1:N", "Hisse2:N", alt.Tooltip("Korelasyon:Q", format=".2f")],
                    )
                    .properties(height=260)
                )
                st.altair_chart(heat, alt="İzleme listesindeki hisselerin korelasyon matrisi")
            with c2:
                st.subheader("Risk katkısı", divider="gray")
                contrib = pd.DataFrame(
                    [{"Hisse": k, "Risk katkısı %": v} for k, v in pr["risk_contributions"].items()]
                ).sort_values("Risk katkısı %", ascending=False)
                st.dataframe(
                    contrib, hide_index=True, alt="Hisselerin portföy riskine katkısı",
                    column_config={"Risk katkısı %": st.column_config.NumberColumn(help=h("risk_contribution"))},
                )
                st.caption("Eşit ağırlık varsayılır. Yüksek korelasyon, çeşitlendirme faydasını azaltır.")

st.container(height=1, border=False)
with st.container(border=True):
    st.subheader("Risk kuralları ve devre kesici", divider="gray")
    risk = settings["risk"]
    st.table({
        ":material/rule: İşlem başına azami risk": f"%{risk['stop_loss_pct']*100:.0f} stop-loss",
        ":material/pie_chart: Pozisyon büyüklüğü": f"%{risk['position_size_pct']*100:.0f} sermaye",
        ":material/groups: Azami açık pozisyon": str(risk["max_positions"]),
        ":material/savings: Başlangıç sermayesi": f"{risk['initial_capital']:,.0f}",
        ":material/health_and_safety: Uygulanan tavan": "%2 sermaye / işlem (Kelly + sert cap)",
    }, border="horizontal", width="content",
       alt="Risk kuralları: işlem başına stop-loss yüzdesi, pozisyon büyüklüğü, azami açık pozisyon sayısı, başlangıç sermayesi ve Kelly sonrası sert tavan.")
    st.caption(
        "Rejim motoru yüksek oynaklık veya düşüş rejiminde pozisyon önerisini otomatik azaltır; "
        "güven eşiği altındaki AL sinyallerini BEKLE'ye çevirir. Ayarlar sayfasından limitleri değiştirebilirsiniz."
    )
