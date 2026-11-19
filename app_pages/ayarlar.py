"""Ayarlar: izleme listesi, veri aralığı, sinyal eşikleri, ağırlıklar ve risk profili.

Her ayarın üzerine gelindiğinde ne işe yaradığını anlatan bir açıklama gösterilir.
"""

from __future__ import annotations

import json

import streamlit as st

from ui import auth, guide_ui
from ui.core import (
    INTERVAL_OPTIONS, PERIOD_OPTIONS, SUGGESTED_SYMBOLS,
    analyze_symbol, default_settings, reset_settings, save_settings, scan_market,
)
from ui.help_texts import h
from ui.insights import PROFILES
from ui.notify import (
    detect_chat_id, new_topic, save_credentials, save_secrets_section,
    send_email, send_ntfy, send_telegram,
)


settings = st.session_state.settings
defaults = default_settings()

# Widget key'i tek kaynaktan beslenir: session_state (default= kullanılmaz)
if "set_symbols" not in st.session_state:
    st.session_state.set_symbols = list(settings["symbols"])

# Widget oluşturulmadan önce bekleyen sembol eklemesini uygula
if st.session_state.get("pending_symbol"):
    pending = st.session_state.pending_symbol
    if pending not in st.session_state.set_symbols:
        st.session_state.set_symbols = st.session_state.set_symbols + [pending]
    st.session_state.pending_symbol = None

st.subheader("Ayarlar", divider="gray")
st.caption(
    "Değişiklikler **Kaydet**'e bastığınızda analiz sayfalarına yansır ve tarayıcıda saklanır. "
    "Her ayarın üzerine fareyi getirerek neyi değiştirdiğinizi görebilirsiniz."
)
guide_ui.tip(
    "Ayarlarda nereye ne yazmalı?",
    [
        "**İzleme listesi:** Hisse ekle alanına `THYAO` veya `GARAN` yazıp Ekleyin; tam liste BIST tarayıcı sayfasındadır.",
        "**Risk profili:** Temkinli/Dengeli/Atak seçimi sinyal eşiklerini ve pozisyon boyutunu değiştirir.",
        "**Bildirim kanalları:** ntfy/Telegram/e-posta tamamen opsiyoneldir; anahtar olmadan da çalışır.",
        "**Kaydet:** Değişiklikler Kaydet'e basıldığında geçerli olur; Varsayılana dön geri alır.",
        "**Veri sıfırlama:** Hesabım sayfasındaki Verilerimi sıfırla ayarları, portföyü ve performans defterini temizler.",
    ],
    key="ayarlar_rehber",
    label="Nereye ne yazmalı?",
)

with st.expander("Varsayılan ayarlar nelerdir?", icon=":material/info:"):
    st.caption(
        "Uygulama ilk açıldığında veya **Varsayılana dön**'e basıldığında bu değerler kullanılır. "
        "Kişisel ayarlarınız kaydedilmediği sürece varsayılanlar geçerlidir."
    )
    default_rows = [
        {"Ayar": "İzleme listesi", "Varsayılan": ", ".join(defaults["symbols"]), "Açıklama": h("symbols")},
        {"Ayar": "Veri aralığı", "Varsayılan": f"{defaults['period']} / {defaults['interval']}", "Açıklama": h("period")},
        {"Ayar": "Risk profili", "Varsayılan": defaults["profile"], "Açıklama": h("profile")},
        {"Ayar": "Güçlü AL / AL eşiği", "Varsayılan": f"{defaults['signal']['strong_buy']} / {defaults['signal']['buy']}", "Açıklama": h("strong_buy")},
        {"Ayar": "SAT / Güçlü SAT eşiği", "Varsayılan": f"{defaults['signal']['sell']} / {defaults['signal']['strong_sell']}", "Açıklama": h("sell")},
        {"Ayar": "RSI eşikleri", "Varsayılan": f"{defaults['indicators']['rsi_oversold']} / {defaults['indicators']['rsi_overbought']}", "Açıklama": h("rsi_oversold")},
        {"Ayar": "Pozisyon büyüklüğü", "Varsayılan": f"%{defaults['risk']['position_size_pct']*100:.0f}", "Açıklama": h("position_size")},
        {"Ayar": "Stop / Hedef", "Varsayılan": f"%{defaults['risk']['stop_loss_pct']*100:.0f} / %{defaults['risk']['take_profit_pct']*100:.0f}", "Açıklama": h("stop_loss")},
        {"Ayar": "Başlangıç sermayesi", "Varsayılan": f"{defaults['risk']['initial_capital']:,.0f}", "Açıklama": h("capital")},
        {"Ayar": "Azami pozisyon", "Varsayılan": str(defaults["risk"]["max_positions"]), "Açıklama": h("max_positions")},
    ]
    st.table(default_rows, alt="Uygulamanın varsayılan ayarları ve açıklamaları")

# ---- İzleme listesi ----
st.subheader("İzleme listesi", divider="gray")
st.multiselect(
    "Takip edilecek hisseler",
    options=list(dict.fromkeys(sorted(set(SUGGESTED_SYMBOLS + settings["symbols"] + defaults["symbols"])))),
    key="set_symbols",
    help=h("symbols"),
)
def _queue_symbol() -> None:
    """Widget instantiation'dan önce çalışır; eklemeyi session_state'e alır."""
    sym = str(st.session_state.get("set_custom_symbol", "")).strip().upper()
    if sym:
        st.session_state.pending_symbol = sym
        st.toast(f"{sym} listeye eklendi.", icon=":material/check:")


with st.container(horizontal=True, vertical_alignment="bottom"):
    st.text_input(
        "Özel sembol ekle",
        placeholder="Örn. BIMAS.IS veya MSFT",
        key="set_custom_symbol",
        help=h("symbols"),
    )
    st.button(
        "Ekle", icon=":material/add:", key="add_symbol",
        help="Yazdığınız sembolü izleme listesine ekler.",
        on_click=_queue_symbol,
    )

# ---- Veri ve profil ----
st.subheader("Veri ayarları ve risk profili", divider="gray")
c1, c2 = st.columns(2)
with c1:
    period = st.pills("Veri periyodu", PERIOD_OPTIONS, default=settings["period"], key="set_period", help=h("period"))
    interval = st.segmented_control("Zaman aralığı", INTERVAL_OPTIONS, default=settings["interval"], key="set_interval", help=h("interval"))
with c2:
    profile = st.segmented_control(
        "Risk profili", list(PROFILES), default=settings["profile"], key="set_profile", help=h("profile")
    )
    st.caption(PROFILES[profile]["description"])

# ---- Sinyal eşikleri ----
st.subheader("Sinyal eşikleri", divider="gray")
sig = settings["signal"]
sc = st.columns(5)
strong_buy = sc[0].number_input("Güçlü AL ≥", value=float(sig.get("strong_buy", 4.0)), min_value=0.0, max_value=5.0, step=0.1, help=h("strong_buy"))
buy = sc[1].number_input("AL ≥", value=float(sig.get("buy", 2.0)), min_value=0.0, max_value=5.0, step=0.1, help=h("buy"))
sell = sc[2].number_input("SAT ≤", value=float(sig.get("sell", -2.0)), min_value=-5.0, max_value=0.0, step=0.1, help=h("sell"))
strong_sell = sc[3].number_input("Güçlü SAT ≤", value=float(sig.get("strong_sell", -4.0)), min_value=-5.0, max_value=0.0, step=0.1, help=h("strong_sell"))
neutral = sc[4].number_input("Nötr", value=float(sig.get("neutral", 0.0)), min_value=-5.0, max_value=5.0, step=0.1, disabled=True, help=h("score"))

rc = st.columns(2)
rsi_os = rc[0].number_input("RSI aşırı düşük", value=float(settings["indicators"].get("rsi_oversold", 30)), min_value=5.0, max_value=45.0, help=h("rsi_oversold"))
rsi_ob = rc[1].number_input("RSI aşırı yüksek", value=float(settings["indicators"].get("rsi_overbought", 70)), min_value=55.0, max_value=95.0, help=h("rsi_overbought"))

# ---- Gösterge ağırlıkları ----
st.subheader("Gösterge ağırlıkları", divider="gray")
weights = settings["signal_weights"]
new_weights: dict[str, float] = {}
for i, (key, default) in enumerate(weights.items()):
    col = st.columns(4)[i % 4]
    new_weights[key] = col.slider(
        key.replace("_", " ").title().replace("Obv", "OBV").replace("Vwap", "VWAP").replace("Rsi", "RSI").replace("Macd", "MACD"),
        min_value=0.0, max_value=3.0, value=float(default), step=0.1,
        key=f"set_w_{key}", help=h("weight"),
    )

# ---- Risk ayarları ----
st.subheader("Risk yönetimi", divider="gray")
risk = settings["risk"]
r1, r2 = st.columns(2)
capital = r1.number_input(
    "Başlangıç sermayesi", value=float(risk.get("initial_capital", 100000)),
    min_value=1000.0, step=1000.0, help=h("capital"),
)
max_positions = r2.number_input(
    "Maksimum açık pozisyon", value=int(risk.get("max_positions", 5)), min_value=1, max_value=20,
    help=h("max_positions"),
)
r3, r4, r5 = st.columns(3)
position_pct = r3.slider(
    "İşlem başına sermaye %", 1, 50, int(float(risk.get("position_size_pct", 0.10)) * 100),
    help=h("position_size"),
) / 100.0
stop_pct = r4.slider(
    "Stop-loss %", 1, 20, int(float(risk.get("stop_loss_pct", 0.05)) * 100),
    help=h("stop_loss"),
) / 100.0
target_pct = r5.slider(
    "Take-profit %", 1, 40, int(float(risk.get("take_profit_pct", 0.10)) * 100),
    help=h("take_profit"),
) / 100.0

# ---- İşlem koruma kuralları ----
st.subheader("İşlem koruma kuralları", divider="gray")
st.caption(h("guards"))
guard_cfg = settings.get("guards", defaults.get("guards", {}))
g1, g2, g3, g4 = st.columns(4)
g_cooldown = int(g1.number_input(
    "Cooldown (bar)", min_value=0, max_value=20,
    value=int(guard_cfg.get("cooldown_bars", 2)), help=h("guards"),
))
g_sl_limit = int(g2.number_input(
    "Stop uyarısı (adet)", min_value=1, max_value=20,
    value=int(guard_cfg.get("stoploss_limit", 3)), help=h("guards"),
))
g_daily_cap = float(g3.number_input(
    "Günlük zarar limiti %", min_value=0.5, max_value=20.0,
    value=float(guard_cfg.get("daily_loss_cap_pct", 3.0)), step=0.5, help=h("guards"),
))
g_halt = float(g4.number_input(
    "Drawdown durma %", min_value=1.0, max_value=50.0,
    value=float(guard_cfg.get("drawdown_halt_pct", 8.0)), step=0.5, help=h("guards"),
))

# ---- Telegram bildirimleri ----
st.subheader("Bildirim kanalları", divider="gray")
st.caption(h("telegram"))
with st.expander("Telegram botu nasıl oluşturulur? (3 adım)", icon=":material/help:"):
    st.markdown(
        "1. Telegram'da **@BotFather**'a git, `/newbot` yaz. Botun adını ve kullanıcı adını "
        "belirle; sana uzun bir **token** verir. Onu aşağıdaki *Bot token* alanına yapıştır.\n"
        "2. Token'ı aldıktan sonra yeni botuna Telegram'dan bir mesaj gönder (örn. `/start`).\n"
        "3. Aşağıdaki **Chat ID'yi otomatik algıla** düğmesine bas; ID kendiliğinden dolar. "
        "Alternatif olarak @userinfobot'a `/start` yazıp ID'ni kopyalayabilirsin."
    )
    with st.container(horizontal=True):
        st.link_button("@BotFather", "https://t.me/BotFather", icon=":material/open_in_new:", key="link_botfather")
        st.link_button("@userinfobot", "https://t.me/userinfobot", icon=":material/open_in_new:", key="link_userinfobot")
    st.caption(
        "Bot görüşmeleri Telegram sunucularında saklanır. Token/chat ID yalnızca bu "
        "makinedeki secrets.toml dosyasına kaydedilir."
    )
# Otomatik algılanan chat ID, widget oluşturulmadan önce uygulanır
if st.session_state.get("pending_chat_id"):
    st.session_state.set_telegram_chat = st.session_state.pending_chat_id
    st.session_state.pending_chat_id = None

tg_cfg = settings.get("alerts", {})


def _persist_alert_flag(flag_name: str, widget_key: str) -> None:
    """Toggle değişince ayarı anında kullanıcı dosyasına yazar."""
    current = st.session_state.settings
    alerts = dict(current.get("alerts", {}))
    alerts[flag_name] = bool(st.session_state.get(widget_key, False))
    current["alerts"] = alerts
    save_settings(current, auth.settings_path(st.session_state.user))


tg_on = st.toggle(
    "Telegram bildirimlerini etkinleştir",
    value=bool(tg_cfg.get("telegram_enabled", False)),
    key="set_telegram_enabled",
    help=h("telegram"),
    on_change=_persist_alert_flag,
    args=("telegram_enabled", "set_telegram_enabled"),
)
tg1, tg2 = st.columns(2)
with tg1:
    tg_token = st.text_input(
        "Bot token", type="password", key="set_telegram_token",
        placeholder="BotFather'dan alınan token", help=h("telegram"),
    )
with tg2:
    tg_chat = st.text_input(
        "Chat ID", key="set_telegram_chat",
        placeholder="Örn. 123456789", help=h("telegram"),
    )
if st.button(
    "Chat ID'yi otomatik algıla", icon=":material/find_in_page:", key="detect_chat_id_button",
    help="Botunuza Telegram'dan mesaj gönderdikten sonra ID'yi otomatik bulur.",
):
    found, message = detect_chat_id(st.session_state.get("set_telegram_token", ""))
    if found:
        st.session_state.pending_chat_id = found
        st.success(f"Chat ID bulundu: {found}", icon=":material/check:")
    else:
        st.warning(message, icon=":material/warning:")

if st.button(
    "Telegram bilgilerini kaydet", icon=":material/save:", key="save_telegram",
    help="Token ve chat id'yi secrets.toml dosyasına yazar.",
):
    save_credentials(tg_token, tg_chat)
    st.success("Telegram bilgileri kaydedildi (değerler gösterilmez).", icon=":material/check:")

if st.button("Telegram test bildirimi", icon=":material/send:", key="test_telegram", help=h("telegram")):
    ok, msg = send_telegram("HSC Borsa Analiz test bildirimi ✅", settings)
    (st.success if ok else st.error)(msg, icon=":material/check:" if ok else ":material/error:")

# ---- ntfy (Telegram alternatifi) ----
with st.expander("Alternatif 1: ntfy.sh push bildirimi (hesapsız)", icon=":material/notifications:"):
    st.caption(h("ntfy"))
    ntfy_on = st.toggle(
        "ntfy bildirimlerini etkinleştir",
        value=bool(tg_cfg.get("ntfy_enabled", False)),
        key="set_ntfy_enabled", help=h("ntfy"),
        on_change=_persist_alert_flag,
        args=("ntfy_enabled", "set_ntfy_enabled"),
    )
    # widget key'i tek kaynaktan beslenir; rastgele konu burada uygulanır
    if "set_ntfy_topic" not in st.session_state:
        st.session_state.set_ntfy_topic = str(tg_cfg.get("ntfy_topic", ""))
    if st.session_state.get("pending_ntfy_topic"):
        st.session_state.set_ntfy_topic = st.session_state.pending_ntfy_topic
        st.session_state.pending_ntfy_topic = None
    ntfy_topic = st.text_input("ntfy konusu", key="set_ntfy_topic", help=h("ntfy"))
    if st.button("Rastgele konu oluştur", icon=":material/shuffle:", key="new_ntfy_topic", help=h("ntfy")):
        st.session_state.pending_ntfy_topic = new_topic()
        st.toast("Yeni konu oluşturuldu.", icon=":material/check:")
    if ntfy_topic:
        st.link_button(
            f"ntfy aboneliğini aç: {ntfy_topic}",
            f"https://ntfy.sh/{ntfy_topic}",
            icon=":material/open_in_new:", key="open_ntfy",
        )
    if st.button("ntfy bilgilerini kaydet", icon=":material/save:", key="save_ntfy"):
        save_secrets_section("alerts", {"ntfy_topic": ntfy_topic})
        st.success("ntfy konusu kaydedildi.", icon=":material/check:")
    if st.button("ntfy test bildirimi", icon=":material/send:", key="test_ntfy"):
        ok, msg = send_ntfy("HSC Borsa Analiz ntfy test ✅", ntfy_topic)
        (st.success if ok else st.error)(msg, icon=":material/check:" if ok else ":material/error:")

# ---- E-posta ----
with st.expander("Alternatif 2: e-posta bildirimi (Gmail)", icon=":material/mail:"):
    st.caption(h("email"))
    mail_on = st.toggle(
        "E-posta bildirimlerini etkinleştir",
        value=bool(tg_cfg.get("email_enabled", False)),
        key="set_email_enabled", help=h("email"),
        on_change=_persist_alert_flag,
        args=("email_enabled", "set_email_enabled"),
    )
    mail_user = st.text_input("Gmail adresi", key="set_mail_user", help=h("email"))
    mail_app = st.text_input("Uygulama şifresi (16 haneli)", type="password", key="set_mail_app", help=h("email"))
    mail_to = st.text_input("Alıcı (boşsa gönderen)", key="set_mail_to", help=h("email"))
    if st.button("E-posta bilgilerini kaydet", icon=":material/save:", key="save_mail"):
        save_secrets_section("smtp", {
            "host": "smtp.gmail.com", "port": "587",
            "user": mail_user, "password": mail_app, "to": mail_to or mail_user,
        })
        st.success("E-posta ayarları kaydedildi.", icon=":material/check:")
    if st.button("E-posta test bildirimi", icon=":material/send:", key="test_mail"):
        ok, msg = send_email("HSC Borsa Analiz e-posta testi ✅", settings)
        (st.success if ok else st.error)(msg, icon=":material/check:" if ok else ":material/error:")

st.container(height=1, border=False)
with st.container(horizontal=True):
    if st.button("Ayarları kaydet", type="primary", icon=":material/save:", key="save_settings", help=h("save_settings")):
        if not st.session_state.set_symbols:
            st.error("En az bir hisse sembolü seçmelisiniz.", icon=":material/error:")
        else:
            updated = {
                "symbols": list(st.session_state.set_symbols),
                "period": period,
                "interval": interval,
                "profile": profile,
                "indicators": {
                    **settings["indicators"],
                    "rsi_oversold": rsi_os,
                    "rsi_overbought": rsi_ob,
                },
                "signal": {
                    **sig,
                    "strong_buy": strong_buy, "buy": buy, "neutral": neutral,
                    "sell": sell, "strong_sell": strong_sell,
                    "rsi_oversold": rsi_os, "rsi_overbought": rsi_ob,
                },
                "signal_weights": new_weights,
                "risk": {
                    **risk,
                    "initial_capital": capital,
                    "max_positions": max_positions,
                    "position_size_pct": position_pct,
                    "stop_loss_pct": stop_pct,
                    "take_profit_pct": target_pct,
                },
                "guards": {
                    **guard_cfg,
                    "cooldown_bars": g_cooldown,
                    "stoploss_limit": g_sl_limit,
                    "daily_loss_cap_pct": g_daily_cap,
                    "drawdown_halt_pct": g_halt,
                },
                "alerts": {
                    **tg_cfg,
                    "telegram_enabled": tg_on,
                    "ntfy_enabled": ntfy_on,
                    "ntfy_topic": ntfy_topic,
                    "email_enabled": mail_on,
                },
            }
            st.session_state.settings = updated
            save_settings(updated, auth.settings_path(st.session_state.user))
            analyze_symbol.clear()
            scan_market.clear()
            st.toast("Ayarlar kaydedildi ve analizler yenilendi.", icon=":material/check:")

    if st.button("Varsayılana dön", icon=":material/restart_alt:", key="reset_settings", help=h("reset_settings")):
        reset_settings(auth.settings_path(st.session_state.user))
        st.session_state.settings = defaults
        st.session_state.selected_symbol = defaults["symbols"][0]
        analyze_symbol.clear()
        scan_market.clear()
        st.rerun()

with st.expander("Mevcut ayarların JSON görünümü (gizli alanlar maskeli)", icon=":material/code:"):
    safe_settings = json.loads(json.dumps(st.session_state.settings, ensure_ascii=False))
    alerts_view = dict(safe_settings.get("alerts", {}) or {})
    for key in ("telegram_bot_token", "telegram_chat_id", "ntfy_topic"):
        if alerts_view.get(key):
            alerts_view[key] = "***"
    for key in ("smtp_user", "smtp_password", "smtp_to", "smtp_host"):
        if alerts_view.get(key):
            alerts_view[key] = "***"
    safe_settings["alerts"] = alerts_view
    st.code(json.dumps(safe_settings, ensure_ascii=False, indent=2), language="json")
