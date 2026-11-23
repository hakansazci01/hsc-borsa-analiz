"""Canlı sinyal terminali: izlenen hisseler sürekli değerlendirilir, karar değişiminde anında bildirim."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import auth, paper
from ui.bist_universe import load_companies
from ui.components import real_money_warning
from ui.help_texts import h
from ui.market_session import now, status as session_status
from ui.signal_feed import detect_and_record, evaluate_watchlist, read_events


user = st.session_state.user
settings = st.session_state.settings
universe = load_companies()

if "terminal_watch" not in st.session_state:
    initial = [s.replace(".IS", "") for s in settings.get("symbols", [])[:8]]
    st.session_state.terminal_watch = initial or ["THYAO", "GARAN"]
if "alert_wait" not in st.session_state:
    st.session_state.alert_wait = False
if "alert_offhours" not in st.session_state:
    st.session_state.alert_offhours = False

st.subheader("Canlı sinyal terminali", divider="gray")
real_money_warning(compact=True)


@st.fragment(run_every="15s")
def _terminal() -> None:
    session = session_status()
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.caption(f"İstanbul saati: **{now().strftime('%H:%M:%S')}** · 15 sn'de bir yenilenir")
        st.badge(
            session["label"],
            color={"open": "green", "pre_market": "orange", "lunch": "gray",
                   "after_hours": "gray", "closed": "gray"}.get(session["key"], "gray"),
            help=session["detail"],
        )

    watched = st.multiselect(
        "İzlenen hisseler (en fazla 8)", list(universe.keys()),
        default=[s for s in st.session_state.terminal_watch if s in universe],
        help="Seçilen hisseler sürekli taranır; karar değiştiğinde bildirim gider.",
    )
    watched = watched[:8]
    st.session_state.terminal_watch = watched
    if not watched:
        st.info("İzlenecek en az bir hisse seçin.", icon=":material/info:")
        return

    results = evaluate_watchlist(watched, settings)
    if not results:
        st.warning("Sinyal alınamadı. Birazdan tekrar denenecek.", icon=":material/warning:")
        return

    new_events = detect_and_record(
        user, results, settings,
        notify_wait=st.session_state.alert_wait,
        notify_offhours=st.session_state.alert_offhours,
    )
    if new_events:
        st.toast(
            f"Sinyal değişimi: {', '.join(e['symbol'] + ' ' + e['to'] for e in new_events[:3])}",
            icon=":material/notifications:",
        )

    st.markdown("#### Sinyel matrisi")
    columns = st.columns(min(4, len(results)))
    for index, row in enumerate(results):
        with columns[index % len(columns)]:
            color = {"AL": "green", "BEKLE": "orange", "SAT": "red"}.get(row["Karar"], "gray")
            with st.container(border=True):
                st.badge(row["Sembol"], color="blue")
                st.badge(row["Karar"], color=color)
                st.metric(
                    "Fiyat", f"{row['Fiyat']:,.2f} ₺",
                    delta=f"{row['Değişim %']:+.2f}%",
                )
                st.progress(row["Güven"] / 100, text=f"Güven %{row['Güven']}")
                st.caption(row["Gerekçe"][:90])

    st.divider()
    focus = st.selectbox(
        "Odak hisse", [r["Sembol"] for r in results], key="terminal_focus",
        help="Bu hissenin işlem seviyeleri ve gerekçesi aşağıda gösterilir.",
    )
    focused = next(r for r in results if r["Sembol"] == focus)
    c1, c2, c3 = st.columns([1, 1, 1.4])
    with c1:
        st.markdown(f"### {focus} · {focused['Karar']}")
        st.caption(f"Güven %{focused['Güven']} · skor {focused['Skor']:+.2f}")
    with c2:
        st.metric("Giriş", f"{focused['Fiyat']:,.2f}", icon=":material/login:")
        st.caption(f"Stop {focused['Stop']:,.2f} · Hedef {focused['Hedef']:,.2f}")
    with c3:
        st.caption(focused["Gerekçe"])
        if st.button("Detaylı analize git", icon=":material/analytics:", key="terminal_detail"):
            st.session_state.bot_pending_symbol = focus
            st.session_state.bot_batch = []
            st.switch_page("app_pages/bot.py")

        if st.button(
            "Kurgusal pozisyon aç", icon=":material/add_circle:", key="terminal_open",
            disabled=not session["in_session"] or focused["Karar"] == "BEKLE",
            help="Yalnızca seans içinde ve AL/SAT sinyalinde; gerçek emir gönderilmez.",
        ):
            risk = settings["risk"]
            price = float(focused["Fiyat"])
            qty = float(risk["initial_capital"]) * float(risk["position_size_pct"]) / price
            paper.open_position(
                user, focus, round(qty, 2), price, focused["Stop"], focused["Hedef"],
                focused["Güven"], f"Terminal sinyali: {focused['Karar']}",
            )
            st.toast(f"{focus} kurgusal pozisyon açıldı.", icon=":material/check:")

    with st.expander("Bildirim ayarları", icon=":material/notifications:"):
        st.toggle(
            "BEKLE geçişlerinde de bildir", value=st.session_state.alert_wait,
            key="alert_wait_toggle",
            help="Açık olması gürültü yaratabilir; varsayılan olarak yalnızca AL/SAT bildirilir.",
        )
        st.toggle(
            "Seans dışında da bildir", value=st.session_state.alert_offhours,
            key="alert_offhours_toggle",
            help="Kapalıyken yalnızca seans içindeki değişimler bildirilir.",
        )
        st.session_state.alert_wait = st.session_state.alert_wait_toggle
        st.session_state.alert_offhours = st.session_state.alert_offhours_toggle
        st.caption("Bildirim yalnızca karar GERÇEKTEN değiştiğinde gönderilir; aynı sinyal tekrarlanmaz.")

    st.markdown("#### Sinyal akışı")
    events = read_events(user, limit=30)
    if events:
        feed = pd.DataFrame(events)
        feed = feed.rename(columns={
            "time": "Saat", "symbol": "Hisse", "from": "Önceki", "to": "Yeni",
            "price": "Fiyat", "change": "Değişim %", "confidence": "Güven", "reason": "Gerekçe",
            "session": "Seans",
        })
        st.dataframe(
            feed[["Saat", "Hisse", "Önceki", "Yeni", "Fiyat", "Değişim %", "Güven", "Gerekçe"]],
            hide_index=True,
            column_config={
                "Fiyat": st.column_config.NumberColumn(format="%.2f"),
                "Değişim %": st.column_config.NumberColumn(format="%+.2f"),
            },
            alt="Sinyal değişimlerinin zaman damgalı akışı",
        )
    else:
        st.caption("Henüz sinyal değişimi yok. İlk değişimde burada görünür ve bildirim gönderilir.")


_terminal()
