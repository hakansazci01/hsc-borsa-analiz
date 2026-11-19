"""Hesabım: kullanıcı ayarları, kurgusal portföy, karar geçmişi ve veri yönetimi."""

from __future__ import annotations

import csv
import json

import pandas as pd
import streamlit as st

from ui import auth, paper
from ui.components import real_money_warning
from ui.core import default_settings, load_settings
from ui.help_texts import h
from ui.pnl_tracker import render_panel as render_pnl_panel
from ui.scheduler import render_scheduler


user = st.session_state.user
st.subheader("Hesabım", divider="gray")
real_money_warning(compact=True)

with st.container(horizontal=True, wrap=True, vertical_alignment="bottom"):
    st.metric("Kullanıcı", user, icon=":material/person:", border=True)
    positions = paper.evaluate(user, st.session_state.settings)
    open_count = len(positions)
    total_pnl = sum(p["pnl_amount"] for p in positions)
    st.metric("Açık kurgusal pozisyon", open_count, icon=":material/payments:", border=True)
    st.metric("Açık K/Z", f"{total_pnl:,.2f} ₺", icon=":material/show_chart:", border=True)

# ---- Kurgusal pozisyonlar ----
with st.container(border=True):
    st.subheader("Kurgusal pozisyonlarım", divider="gray")
    st.caption(
        "Bu pozisyonlar yalnızca simülasyondur; aracı kuruma emir gönderilmez. "
        "SAT önerisi stop, hedef veya teknik sinyal değişimine dayanır."
    )
    if not positions:
        st.info("Açık kurgusal pozisyon yok. İşlem botundan bir sinyali 'kurgusal al' ile açabilirsiniz.", icon=":material/info:")
    else:
        for p in positions:
            with st.container(border=True):
                c1, c2, c3 = st.columns([1.2, 1, 1])
                with c1:
                    st.markdown(f"### {p['symbol']} · {p['qty']:g} adet")
                    st.caption(f"Açılış: {p['opened_at']} · Giriş: {p['entry_price']:,.2f} ₺")
                with c2:
                    st.metric(
                        "Güncel", f"{p['current_price']:,.2f} ₺",
                        delta=f"{p['pnl_pct']:+.2f}%",
                        help=h("last_close"),
                    )
                    st.caption(f"K/Z: {p['pnl_amount']:,.2f} ₺")
                with c3:
                    if p["action"] == "SAT":
                        st.badge("SAT ÖNERİSİ", color="red", icon=":material/sell:")
                    else:
                        st.badge("TUT", color="green", icon=":material/pause_circle:")
                    st.caption(f"Stop: {p.get('stop') or '—'} · Hedef: {p.get('target') or '—'}")
                st.markdown("**Gerekçeler**")
                for reason in p["reasons"]:
                    st.markdown(f"- {reason}")
                st.caption(f"Fiyat kaynağı: {p['source']} · Seans: {p['session']}")

                if st.button(
                    f"{p['symbol']} pozisyonunu kurgusal sat",
                    key=f"close_{p['id']}",
                    icon=":material/sell:",
                    help="Kurgusal pozisyonu güncel fiyattan kapatır; gerçek emir gönderilmez.",
                ):
                    result = paper.close_position(user, p["id"], p["current_price"], "Manuel / öneri ile kapatıldı")
                    if result:
                        st.toast(
                            f"{p['symbol']} kurgusal satış: {result['pnl_pct']:+.2f}%",
                            icon=":material/check:",
                        )
                        st.rerun()

# ---- Karar geçmişi ----
with st.container(border=True):
    st.subheader("Karar geçmişim", divider="gray")
    history = auth.read_history(user, limit=100)
    if history:
        st.dataframe(pd.DataFrame(history), hide_index=True, alt="Kullanıcının karar ve kurgusal işlem geçmişi")
    else:
        st.caption("Henüz kayıtlı karar yok.")

# ---- 15 dakikalık net K/Z tablosu ----
with st.container(border=True, key="pnl_panel"):
    st.subheader("15 dakikalık net K/Z tablosu", divider="gray")
    st.caption("Seans içinde her 15 dakikada gerçekleşen + açık K/Z kaydedilir. Tamamı kurgusal simülasyondur.")
    render_pnl_panel(user)

# ---- Otomatik tarama zamanlayıcısı ----
with st.container(border=True):
    st.subheader("Otomatik tarama zamanlayıcısı", divider="gray")
    render_scheduler(user, st.session_state.settings)

# ---- Kayıtlı ayarlar ----
with st.container(border=True):
    st.subheader("Kayıtlı ayarlarım", divider="gray")
    settings = st.session_state.settings
    st.table({
        "İzleme listesi": ", ".join(settings.get("symbols", [])),
        "Profil": settings.get("profile", "—"),
        "Periyot": f"{settings.get('period')} / {settings.get('interval')}",
        "Sermaye": f"{float(settings.get('risk', {}).get('initial_capital', 0)):,.0f}",
        "Pozisyon": f"%{float(settings.get('risk', {}).get('position_size_pct', 0))*100:.0f}",
        "Koruma": "Açık" if settings.get("guards") else "Kapalı",
    }, border="horizontal", width="content",
       alt="Kayıtlı kullanıcı ayarları: izleme listesi, risk profili, veri periyodu, kurgusal sermaye, işlem başına pozisyon yüzdesi ve koruma durumu.")
    st.caption("Ayarları değiştirmek için **Ayarlar** sayfasını kullanın.")

# ---- Veri dönüştürücüler ----
with st.container(border=True):
    st.subheader("Veri içe / dışa aktarma", divider="gray")
    st.caption("CSV ↔ JSON dönüşümü, kurgusal portföyünüzü yedeklemenizi veya dışarıdan içe aktarmanızı sağlar.")

    current_positions = paper.load_positions(user)
    if current_positions:
        import io

        csv_buffer = io.StringIO()
        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=["symbol", "qty", "entry_price", "stop", "target", "confidence", "opened_at"],
        )
        writer.writeheader()
        for row in current_positions:
            writer.writerow({k: row.get(k, "") for k in writer.fieldnames})
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                "Portföyü CSV indir", data=csv_buffer.getvalue().encode("utf-8-sig"),
                file_name="kurgusal_portfoy.csv", mime="text/csv",
                icon=":material/download:", key="dl_portfolio_csv",
            )
        with c2:
            st.download_button(
                "Portföyü JSON indir",
                data=json.dumps(current_positions, ensure_ascii=False, indent=2).encode("utf-8"),
                file_name="kurgusal_portfoy.json", mime="application/json",
                icon=":material/download:", key="dl_portfolio_json",
            )
    st.caption("JSON görünümü (tablo):")
    st.dataframe(pd.DataFrame(current_positions), hide_index=True, alt="Kurgusal portföy JSON verisi")

    uploaded = st.file_uploader(
        "Kurgusal pozisyon CSV'si yükle",
        type=["csv"], key="portfolio_upload",
        help="symbol,qty,entry_price,stop,target sütunları gereklidir.",
    )
    if uploaded is not None:
        try:
            incoming = pd.read_csv(uploaded)
            required = {"symbol", "qty", "entry_price"}
            if not required.issubset(incoming.columns):
                st.error(f"Eksik sütunlar: {', '.join(required - set(incoming.columns))}", icon=":material/error:")
            else:
                st.dataframe(incoming, hide_index=True, alt="Yüklenecek kurgusal pozisyonlar")
                if st.button("Pozisyonları içe aktar", key="import_positions", icon=":material/upload:"):
                    added = 0
                    for _, row in incoming.iterrows():
                        paper.open_position(
                            user, str(row["symbol"]), float(row["qty"]),
                            float(row["entry_price"]),
                            float(row.get("stop", 0)) or None,
                            float(row.get("target", 0)) or None,
                            int(row.get("confidence", 0) or 0), "CSV içe aktarma",
                            allow_closed=True,
                        )
                        added += 1
                    st.toast(f"{added} pozisyon içe aktarıldı.", icon=":material/check:")
                    st.rerun()
        except Exception as exc:
            st.error(f"CSV okunamadı: {exc}", icon=":material/error:")

# ---- Veri yönetimi ----
st.container(height=1, border=False)
with st.container(border=True):
    st.subheader("Veri yönetimi", divider="gray")
    st.caption("Bu işlemler geri alınamaz. Silmeden önce mutlaka onaylayın.")

    c1, c2 = st.columns(2)
    with c1:
        confirm_reset = st.checkbox("Ayarlarımı, portföyümü, geçmişimi ve performans defterimi sıfırlamayı onaylıyorum", key="confirm_reset_data")
        if st.button(
            "Verilerimi sıfırla", icon=":material/restart_alt:", key="reset_my_data",
            disabled=not confirm_reset,
            help="Kullanıcıya özel tüm veriyi siler, ayarları varsayılana döndürür.",
        ):
            auth.reset_user_data(user)
            defaults = default_settings()
            st.session_state.settings = defaults
            st.session_state.settings_owner = user
            st.toast("Kullanıcı verileri sıfırlandı.", icon=":material/check:")
            st.rerun()
    with c2:
        confirm_delete = st.checkbox("Hesabımı kalıcı olarak silmeyi onaylıyorum", key="confirm_delete_account")
        if st.button(
            "Hesabı sil", icon=":material/delete_forever:", key="delete_my_account",
            disabled=not confirm_delete, type="primary",
            help="Hesabı ve tüm kullanıcı verilerini kalıcı siler.",
        ):
            auth.delete_account(user)
            st.session_state.user = None
            st.session_state.settings_owner = None
            st.session_state.pop("settings", None)
            st.toast("Hesap silindi.", icon=":material/check:")
            st.rerun()
