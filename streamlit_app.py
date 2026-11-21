"""
HSC Borsa Analiz — akıllı hisse sinyal paneli.

Çalıştırmak için:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="HSC Borsa Analiz",
    page_icon=":material/show_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui import auth  # noqa: E402
from ui import disclosure, guide_ui, motion, tr_ui, visual  # noqa: E402
from ui.core import load_settings  # noqa: E402
from ui.market_ticker import render_sidebar_ticker  # noqa: E402
from ui.password_tools import generate_password, strength  # noqa: E402
from ui.style import inject_modern_style  # noqa: E402

inject_modern_style()
motion.inject_motion_tokens()  # hareket token'ları + reduced-motion koruması
visual.inject_visual_css()  # kart, rozet ve animasyon stilleri (hv- öneki)
tr_ui.install()  # Streamlit'in İngilizce menü/toolbar etiketlerini Türkçe yapar


if "user" not in st.session_state:
    st.session_state.user = None
if "settings_owner" not in st.session_state:
    st.session_state.settings_owner = None
if "bot_batch" not in st.session_state:
    st.session_state.bot_batch = []
    st.session_state.pending_symbols = []
if "pending_symbols" not in st.session_state:
    st.session_state.pending_symbols = []


def _logout() -> None:
    st.session_state.user = None
    st.session_state.settings_owner = None
    st.session_state.pop("settings", None)
    st.session_state.pop("bot_messages", None)
    st.session_state.pop("bot_last", None)
    st.session_state.pop("live_decisions", None)


def _render_auth() -> None:
    brand_col, form_col = st.columns([1.05, 1.25], gap="large")
    with brand_col:
        visual.brand_panel()

    with form_col:
        st.title("HSC borsa analiz", icon=":material/show_chart:")
        st.caption(
            "Kişisel ayarlarınız, kurgusal portföyünüz ve karar geçmişiniz kullanıcı adınıza saklanır. "
            "Şifreler tuzlu PBKDF2 ile hash'lenir; düz metin tutulmaz."
        )
        guide_ui.inject_guide_css()
        guide_ui.tip(
            "Kullanıcı bilgilerini nereye, nasıl girmeli?",
            [
                "**İlk kez kullanıyorsunuz:** Kayıt ol sekmesinde kullanıcı adı (3-32 karakter) ve şifre (en az 10 karakter) belirleyin.",
                "**Şifre zorlanıyorsa:** Güçlü şifre öner düğmesi sizin için güvenli bir şifre üretir.",
                "**Daha önce kayıt olduysanız:** Giriş yap sekmesinden aynı kullanıcı adı ve şifreyi yazın.",
                "**API anahtarı gerekmez:** ntfy/Telegram/e-posta opsiyoneldir; Ayarlar sayfasından sonra ekleyebilirsiniz.",
            ],
            key="auth_userinfo",
            label="Bilgileri nereye gireceğim?",
        )
        login_tab, register_tab = st.tabs(["Giriş yap", "Kayıt ol"])

        with login_tab:
            with st.form("login_form", border=False):
                username = st.text_input("Kullanıcı adı", key="login_user")
                password = st.text_input("Şifre", type="password", key="login_pass")
                if st.form_submit_button("Giriş yap", type="primary", width="stretch"):
                    try:
                        st.session_state.user = auth.login(username, password)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc), icon=":material/error:")

        with register_tab:
            if st.button(
                "Güçlü şifre öner", icon=":material/key:", key="suggest_password",
                help="Kriptografik güvenli, rastgele bir şifre üretir.",
            ):
                st.session_state.reg_pass = generate_password(16)
                st.toast("Güçlü bir şifre önerildi. Şifre alanına yazıldı.", icon=":material/check:")

            with st.form("register_form", border=False):
                new_user = st.text_input("Kullanıcı adı (3-32 karakter)", key="reg_user")
                new_pass = st.text_input("Şifre (en az 10 karakter)", type="password", key="reg_pass")
                pw = strength(st.session_state.get("reg_pass", ""))
                st.progress(
                    pw["score"] / 4,
                    text=f"Şifre gücü: **{pw['label']}**",
                )
                st.caption(
                    "Kontrol: " + " · ".join(
                        f"{'✓' if ok else '✗'} {name}" for name, ok in pw["checks"].items()
                    )
                )
                if st.form_submit_button("Hesap oluştur", width="stretch"):
                    try:
                        auth.register(new_user, new_pass)
                        st.success("Hesap oluşturuldu. Giriş yapabilirsiniz.", icon=":material/check:")
                    except ValueError as exc:
                        st.error(str(exc), icon=":material/error:")

        st.caption(
            "Yerel tek kullanıcı oturumudur. İnternet üzerinden yayınlama için "
            "Streamlit `st.login()` + OIDC kullanılmalıdır."
        )
        visual.login_feature_panel()

    visual.auth_footer()


if not st.session_state.user:
    _render_auth()
    st.stop()

user = st.session_state.user
disclosure.render_once(user)
if st.session_state.settings_owner != user or "settings" not in st.session_state:
    st.session_state.settings = load_settings(auth.settings_path(user))
    st.session_state.settings_owner = user
    symbols = st.session_state.settings.get("symbols", [])
    st.session_state.selected_symbol = symbols[0] if symbols else "THYAO"
    st.session_state.live_decisions = []
    st.session_state.bot_messages = []
    st.session_state.bot_last = None
    st.session_state.bot_batch = []
    st.session_state.pending_symbols = []

if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = (
        st.session_state.settings.get("symbols", ["THYAO"])[0]
    )

from ui.market_session import status as session_status  # noqa: E402
from ui.pnl_tracker import record_mark  # noqa: E402
from ui.scheduler import auto_check_fragment  # noqa: E402


@st.fragment(run_every="60s")
def _global_scheduler_fragment() -> None:
    """Tüm sayfalarda çalışır: zamanlı tarama, seans hazırlığı, açılış güncellemesi."""
    auto_check_fragment(st.session_state.user, st.session_state.settings)


@st.fragment(run_every="5m")
def _global_pnl_fragment() -> None:
    """Seans içinde 15 dk'lık K/Z işaretlerini kaydeder."""
    if session_status()["in_session"]:
        record_mark(st.session_state.user, st.session_state.settings)


_global_scheduler_fragment()
_global_pnl_fragment()

st.logo("assets/logo.png", size="small", icon_image="assets/logo.png")
st.title("HSC borsa analiz", icon=":material/show_chart:")
st.caption(
    f"**{user}** olarak giriş yapıldı · Teknik analiz, geriye dönük test ve akıllı sinyal yorumlaması. "
    "Yatırım tavsiyesi değildir."
)

render_sidebar_ticker()
guide_ui.render_global_guide()

with st.sidebar:
    st.caption(f"Oturum: **{user}**")
    st.toggle(
        "Sinyalleri kapat (kill switch)",
        key="signals_off",
        help="Açıkken veri kapısı tüm AL/SAT sinyallerini BEKLE'ye çeker; mevcut veri korunur.",
    )
    if st.button(
        "Ayarları dosyadan yeniden yükle", icon=":material/refresh:", key="reload_settings_button",
        help="Kayıtlı ayarları diskten okur; oturumu kapatmadan uygular.",
    ):
        st.session_state.settings = load_settings(auth.settings_path(user))
        st.session_state.settings_owner = user
        st.toast("Ayarlar yeniden yüklendi.", icon=":material/check:")
    if st.button("Çıkış yap", icon=":material/logout:", key="logout_button", on_click=_logout):
        pass

page = st.navigation(
    [
        st.Page(
            "app_pages/bot_durumu.py",
                title="BOT DURUMU",
                icon=":material/traffic:",
                help="Canlı durum: büyük AÇIK/KAPALI ışığı, kilitler, watchdog, bakiye, frenler — her saniye.",
            ),
        st.Page(
            "app_pages/otonom_durum.py",
                title="CANLI İŞLEM AKIŞI",
                icon=":material/stream:",
                help="Ne aldım, ne sattım, kâr/zarar, başarı oranları, işlem defteri — 10 sn'de bir yenilenen gerçek veri.",
            ),
        st.Page(
            "app_pages/akilli_panel.py",
                title="Akıllı Panel",
                icon=":material/auto_awesome:",
                help="Sade 3 adımda piyasa durumu, tek net karar ve kurgusal portföy; rejime göre yöntem önerisi.",
            ),
            st.Page(
                "app_pages/ajans.py",
                title="İşlem ajansı",
                icon=":material/psychology:",
                help="Rejime uyarlanmış çoklu zaman dilimi uyumu ile tam işlem planı ve ön kontrol üretir.",
            ),
            st.Page(
                "app_pages/anlik.py",
                title="Anlık sinyal",
                icon=":material/flash_on:",
                help="Canlı 1 dakikalık mumlardan 5m/15m tetikleyici koşullarıyla anlık AL/SAT sinyali üretir.",
            ),
            st.Page(
                "app_pages/terminal.py",
                title="Sinyal terminali",
                icon=":material/monitoring:",
                help="İzlenen hisseleri 15 saniyede bir değerlendirir; karar değişiminde anında bildirim gönderir.",
            ),
            st.Page(
                "app_pages/hesabim.py",
                title="Hesabım",
                icon=":material/person:",
                help="Kurgusal portföyünüzü, karar geçmişinizi ve verilerinizi yönetir.",
            ),
            st.Page(
                "app_pages/performans.py",
                title="Sinyal performansı",
                icon=":material/query_stats:",
                help="Kapanan her kurgusal sinyali R çarpanıyla kaydeden şeffaf sonuç defteri ve performans KPI'ları.",
            ),
            st.Page(
                "app_pages/ayarlar.py",
                title="Ayarlar",
                icon=":material/settings:",
                help="İzleme listesi, eşikler, gösterge ağırlıkları ve risk parametrelerini düzenler.",
            ),
        st.Page(
            "app_pages/tarayici.py",
                title="BIST tarayıcı",
                icon=":material/radar:",
                help="BIST'te kayıtlı 804 hissenin tamamını teknik koşullarla tarar.",
            ),
            st.Page(
                "app_pages/bot.py",
                title="İşlem botu",
                icon=":material/smart_toy:",
                help="BIST hissesini yazın; canlı fiyat, KAP ve teknik sinyallerle anında AL/BEKLE/SAT kararı verir.",
            ),
            st.Page(
                "app_pages/canli.py",
                title="Canlı işlem",
                icon=":material/bolt:",
                help="Gerçek BIST fiyatları, KAP haberleri ve teknik sinyallerle anlık AL/BEKLE/SAT kararı üretir.",
            ),
            st.Page(
                "app_pages/risk.py",
                title="Akıllı risk merkezi",
                icon=":material/shield:",
                help="Piyasa rejimi, Kelly pozisyon boyutu, Monte Carlo zarar olasılığı ve portföy riskini analiz eder.",
            ),
            st.Page(
                "app_pages/laboratuvar.py",
                title="Strateji laboratuvarı",
                icon=":material/science:",
                help="Walk-forward doğrulama, parametre duyarlılığı ve işlem koruma katmanını gösterir.",
            ),
            st.Page(
                "app_pages/denetim.py",
                title="Denetim ve doğrulama",
                icon=":material/fact_check:",
                help="Hata kaynaklarını, istatistiksel güveni ve gerçek para öncesi zorunlu kontrolleri gösterir.",
            ),
            st.Page(
                "app_pages/piyasa.py",
                title="Piyasa analizi",
                icon=":material/dashboard:",
                help="İzleme listesini tarar, AL/SAT sinyallerini ve güven skorlarını gösterir.",
            ),
            st.Page(
                "app_pages/hisse.py",
                title="Hisse detayı",
                icon=":material/analytics:",
                help="Tek hissenin grafiklerini, gösterge gerekçelerini ve akıllı analist yorumunu gösterir.",
            ),
            st.Page(
                "app_pages/portfoy.py",
                title="Portföy ve test",
                icon=":material/account_balance_wallet:",
                help="Risk profiline göre dağılım önerisi ve backtest getiri karşılaştırması sunar.",
            ),
    ],
    position="sidebar",
    expanded=True,
)
page.run()
