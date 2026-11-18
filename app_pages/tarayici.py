"""BIST tarayıcı: 804 kayıtlı hissenin tamamını koşul bazında tarar."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.bist_universe import load_companies
from ui.components import real_money_warning
from ui.help_texts import h
from ui.screener import HELP_TEXT, PRESETS, scan_all, symbol_signal


if "screener_selected" not in st.session_state:
    st.session_state.screener_selected = []

st.subheader("BIST tarayıcı (tüm evren)", divider="gray")
st.caption(
    f"Borsa İstanbul'da kayıtlı **{len(load_companies())} hisse** taranır. "
    "Sonuçlar 60 saniye önbelleğe alınır; seans içinde otomatik yenilenir."
)
real_money_warning(compact=True)

preset = st.segmented_control(
    "Hazır filtreler", list(PRESETS), key="screener_preset",
    help="Kayıtlı tüm BIST hisseleri üzerinde çalışan teknik filtreler.",
)
condition = st.text_input(
    "Özel koşul", value=PRESETS.get(preset or "Aşırı satım adayları (RSI<35)", "rsi < 35"),
    key="screener_condition", help=HELP_TEXT,
)

rows = scan_all(condition.strip(), limit=100)
df = pd.DataFrame(rows)

if df.empty:
    st.info("Bu koşulla eşleşen hisse bulunamadı. Filtreyi gevşetmeyi deneyin.", icon=":material/info:")
else:
    c1, c2, c3 = st.columns(3)
    c1.metric("Eşleşen hisse", len(df), icon=":material/leaderboard:")
    c2.metric("Ortalama değişim", f"{df['Değişim %'].mean():+.2f}%", icon=":material/show_chart:")
    c3.metric("Ortalama RSI", f"{df['RSI'].dropna().mean():.1f}", icon=":material/equalizer:")

    def _color_change(value: float) -> str:
        if pd.isna(value):
            return ""
        color = "#065F46" if value > 0 else "#991B1B" if value < 0 else "#475569"
        return f"background-color: {color}; color: white; font-weight: 600;"

    st.dataframe(
        df.style.map(_color_change, subset=["Değişim %"]),
        hide_index=True,
        column_config={
            "Fiyat": st.column_config.NumberColumn("Fiyat", format="%.2f"),
            "Değişim %": st.column_config.NumberColumn("Değişim %", format="%+.2f"),
            "RSI": st.column_config.NumberColumn("RSI", format="%.1f"),
            "Hacim": st.column_config.NumberColumn("Hacim", format="%,.0f"),
        },
        alt="Tüm BIST hisseleri için filtre sonuçları",
    )

    if st.button("İlk 10 hisse için teknik sinyal ekle", icon=":material/analytics:", key="enrich_signals"):
        with st.spinner("Teknik sinyaller alınıyor..."):
            top = df.head(10).copy()
            top["Teknik Sinyal"] = [symbol_signal(sym) or "—" for sym in top["Sembol"]]
        st.dataframe(top, hide_index=True, alt="İlk 10 hisse için teknik sinyaller")

    # Önceden seçilmiş hisseler filtre değişse de listede kalır (kalıcı seçim)
    options = list(dict.fromkeys(
        df["Sembol"].tolist() + st.session_state.screener_selected
    ))

    with st.container(horizontal=True):
        if st.button("Tümünü seç", icon=":material/select_all:", key="select_all_results",
                     help="Görüntülenen sonuçların tamamını seçer."):
            st.session_state.screener_selected = list(dict.fromkeys(
                st.session_state.screener_selected + df["Sembol"].tolist()
            ))[:12]
            st.rerun()
        if st.button("Seçimi temizle", icon=":material/clear_all:", key="clear_selection",
                     help="Tüm seçimleri kaldırır."):
            st.session_state.screener_selected = []
            st.rerun()

    selected = st.multiselect(
        "Analiz için hisse seç (çoklu)", options,
        default=[s for s in st.session_state.screener_selected if s in options],
        help="Seçimler filtre değişiminde korunur; bot seçilenleri ayrı ayrı analiz eder.",
    )
    st.session_state.screener_selected = list(selected)[:12]
    if st.session_state.screener_selected:
        with st.container(horizontal=True):
            for sym in st.session_state.screener_selected:
                st.badge(sym, color="blue")
        st.caption(f"{len(st.session_state.screener_selected)} hisse seçildi")

    c1, c2 = st.columns(2)
    with c1:
        if st.button(
            "Seçilenleri bot'ta analiz et", icon=":material/smart_toy:",
            key="screener_to_bot", disabled=not selected,
            help="Seçilen hisseler için AL/BEKLE/SAT kararlarını üretir.",
        ):
            st.session_state.bot_batch = list(selected)[:12]
            st.session_state.bot_messages = []
            st.session_state.bot_last = None
            st.switch_page("app_pages/bot.py")
    with c2:
        if st.button(
            "İzleme listesine ekle", icon=":material/add:", key="screener_watchlist",
            disabled=not selected, help="Seçilen hisseleri Ayarlar'daki izleme listesine ekler.",
        ):
            current = list(st.session_state.settings.get("symbols", []))
            added = 0
            for sym in selected:
                yahoo = sym if sym.endswith(".IS") else f"{sym}.IS"
                if yahoo not in current:
                    current.append(yahoo)
                    added += 1
            st.session_state.settings = {**st.session_state.settings, "symbols": current}
            from ui.core import save_settings
            from ui import auth

            save_settings(st.session_state.settings, auth.settings_path(st.session_state.user))
            st.toast(f"{added} hisse izleme listesine eklendi.", icon=":material/check:")
