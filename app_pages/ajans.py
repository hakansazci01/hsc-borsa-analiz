"""Akıllı işlem ajansı: confluence + tam trade planı + işlem öncesi kontroller + kalibrasyon."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import auth, paper
from ui.agent import build_plan, pretrade_checks
from ui.bist_universe import load_companies, ordered_symbols
from ui.components import real_money_warning
from ui.help_texts import h
from ui.scientific import calibration_report


st.subheader("Akıllı işlem ajansı", divider="gray")
st.caption(
    "9 zaman dilimi, KAP duyarımı ve BIST 100'e göre göreli güç birleştirilir; "
    "rejime göre ağırlıklar değişir. Çıktı bir **işlem planıdır** — emir gönderilmez."
)
real_money_warning(compact=True)

universe = load_companies()
symbol = st.selectbox(
    "Hisse", ordered_symbols(universe),
    format_func=lambda s: f"{s} · {universe.get(s, s)}",
    key="agent_symbol", help=h("bist_search"),
)

if st.button("Plan oluştur", icon=":material/auto_awesome:", key="agent_build", type="primary"):
    with st.spinner("Ajan analiz ediyor..."):
        plan = build_plan(symbol, st.session_state.settings, st.session_state.user)
        st.session_state.agent_plan = plan
        if plan:
            st.session_state.agent_checks = pretrade_checks(
                plan, st.session_state.user, st.session_state.settings
            )
        else:
            st.session_state.agent_checks = []

plan = st.session_state.get("agent_plan")
checks = st.session_state.get("agent_checks", [])

if not plan:
    st.info("Bir hisse seçip **Plan oluştur** düğmesine basın.", icon=":material/info:")
else:
    with st.container(border=True, key="agent_verdict"):
        color = {"AL": "green", "BEKLE": "orange", "SAT": "red"}[plan["decision"]]
        with st.container(horizontal=True, vertical_alignment="bottom"):
            st.markdown(f"### {plan['symbol']} · {plan['decision']}")
            st.badge(f"Güven %{plan['confidence']}", color=color)
            st.badge(f"Rejim: {plan['regime']}", color="blue")
        st.caption(
            f"Confluence skoru {plan['score']:+.2f} · zaman dilimi {plan['confluence']['tf_score']:+.2f} · "
            f"haber {plan['confluence']['news_score']:+.2f} · göreli güç {plan['confluence']['relative_score']:+.2f} "
            f"({plan['confluence']['relative_pct']:+.2f}%)"
        )
        st.caption(plan["calibration_note"])
        st.progress(plan["confidence"] / 100, text="Kalibre edilmiş güven")

    c1, c2 = st.columns([1.2, 1], gap="medium")
    with c1:
        with st.container(border=True):
            st.subheader("İşlem planı", divider="gray")
            plan_df = pd.DataFrame([
                {"Alan": "Giriş bölgesi", "Değer": f"{plan['price']*0.997:,.2f} – {plan['price']*1.003:,.2f} ₺"},
                {"Alan": "Stop (1.5 ATR)", "Değer": f"{plan['stop']:,.2f} ₺ ({plan['stop_distance_pct']:.2f}%)" if plan["stop"] else "—"},
                {"Alan": "Hedef 1 (1.5R)", "Değer": f"{plan['t1']:,.2f} ₺" if plan["t1"] else "—"},
                {"Alan": "Hedef 2 (2.5R)", "Değer": f"{plan['t2']:,.2f} ₺" if plan["t2"] else "—"},
                {"Alan": "Hedef 3 (4R)", "Değer": f"{plan['t3']:,.2f} ₺" if plan["t3"] else "—"},
                {"Alan": "Pozisyon", "Değer": f"{plan['qty']} adet · {plan['risk_amount']:,.2f} ₺"},
                {"Alan": "Risk", "Değer": f"%{plan['risk_pct']} sermaye"},
                {"Alan": "Yatay ufuk", "Değer": f"{plan['horizon']} gün"},
                {"Alan": "Geçersizleme", "Değer": plan["invalidation"]},
            ])
            st.dataframe(plan_df, hide_index=True, alt="Ajan tarafından üretilen işlem planı")
    with c2:
        with st.container(border=True):
            st.subheader("Zaman dilimi katkıları", divider="gray")
            if plan["confluence"]["contributions"]:
                st.dataframe(
                    pd.DataFrame(plan["confluence"]["contributions"]),
                    hide_index=True,
                    column_config={
                        "Katkı": st.column_config.NumberColumn(format="%+.2f"),
                        "AL": st.column_config.NumberColumn("AL oyu"),
                        "SAT": st.column_config.NumberColumn("SAT oyu"),
                    },
                    alt="Zaman dilimlerinin karara katkısı",
                )
            else:
                st.caption("Yönlü zaman dilimi katkısı yok.")

    with st.container(border=True):
        st.subheader("İşlem öncesi kontroller", divider="gray")
        for check in checks:
            icon = ":material/check_circle:" if check["Geçti"] else ":material/cancel:"
            st.markdown(f"- {icon} **{check['Kontrol']}:** {check['Detay']}")
        all_ok = bool(checks) and all(c["Geçti"] for c in checks)

        if st.button(
            "Kurgusal emri onayla ve aç", icon=":material/check:", key="agent_open",
            disabled=not all_ok,
            help="Tüm kontroller geçtiğinde kurgusal pozisyon açılır; gerçek emir gönderilmez.",
        ):
            paper.open_position(
                st.session_state.user, plan["symbol"], plan["qty"], plan["price"],
                plan["stop"], plan["t2"], plan["confidence"],
                f"Ajan planı: {plan['decision']} (skor {plan['score']:+.2f})",
            )
            st.toast(f"{plan['symbol']} kurgusal pozisyon açıldı.", icon=":material/check:")
            st.rerun()

    st.caption(
        "Plan; teknik uyum, haber, göreli güç, rejim, volatilite ve risk limitlerinin "
        "birleşimidir. Gelecek getiri garantisi değildir."
    )

# ---- Güven kalibrasyonu ----
with st.container(border=True):
    st.subheader("Güven kalibrasyonu (Brier skoru)", divider="gray")
    st.caption(
        "Ajanın tahmin ettiği güven ile gerçekleşen kurgusal işlemlerin kazanma oranı karşılaştırılır. "
        "Brier skoru düşük, skill skoru yüksek olmalı."
    )
    outcomes = [
        r for r in auth.read_history(st.session_state.user, limit=500)
        if r.get("type") == "PAPER_SAT"
    ]
    cal = calibration_report(outcomes)
    if cal.get("available"):
        c1, c2, c3 = st.columns(3)
        c1.metric("Brier skoru", cal["brier"], help="Olasılık tahmininin ortalama kare hatası; düşük iyidir.")
        c2.metric("Brier skill", cal["brier_skill"], help="Taban orana göre iyileşme; pozitif iyidir.")
        c3.metric("Örnek", cal["samples"], icon=":material/format_list_numbered:")
        st.dataframe(
            pd.DataFrame(cal["buckets"]), hide_index=True,
            alt="Güven kovalarına göre tahmin ve gerçek kazanma oranları",
        )
        st.caption(cal["verdict"])
    else:
        st.caption(cal.get("reason", "Henüz yeterli gerçekleşmiş işlem yok."))

# ---- Açık pozisyonlar ----
with st.container(border=True):
    st.subheader("Açık kurgusal pozisyonlar", divider="gray")
    positions = paper.evaluate(st.session_state.user, st.session_state.settings)
    if not positions:
        st.caption("Açık pozisyon yok.")
    else:
        for p in positions:
            with st.container(border=True):
                st.markdown(f"### {p['symbol']} · {p['action']}")
                st.caption(
                    f"Giriş {p['entry_price']:,.2f} · güncel {p['current_price']:,.2f} · "
                    f"K/Z {p['pnl_pct']:+.2f}% ({p['pnl_amount']:+,.2f} ₺)"
                )
                for reason in p["reasons"]:
                    st.markdown(f"- {reason}")
