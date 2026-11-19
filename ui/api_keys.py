"""
API kaynakları rehberi.

Denetim sayfasında şunları gösterir:
- her verinin nereden geldiği,
- kullanıcının anahtarı nereden alıp nereye kaydedeceği,
- anahtarın yapılandırılıp yapılandırılmadığı (değer gösterilmeden),
- isteğe bağlı olarak tarayıcıdan güvenli düzenleme.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib
from typing import Any

import streamlit as st

from ui import secrets_access
from ui.help_texts import h


SECRETS_PATH = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"

SERVICES: list[dict[str, Any]] = [
    {
        "name": "borsapy · KAP + TradingView",
        "purpose": "BIST fiyatı, gün içi veri, KAP bildirimleri, 9 zaman diliminde teknik sinyal",
        "key_required": "Hayır",
        "register_url": "https://github.com/saidsurucu/borsapy",
        "docs_url": "https://saidsurucu.github.io/borsapy/borsapy.html",
        "section": None,
        "keys": (),
        "note": (
            "Ücretsiz akış ~15 dk gecikmelidir. Gerçek zamanlı veri için TradingView oturum "
            "kimlik bilgileri gerekir (borsapy set_tradingview_auth); ücretsiz kullanımda bu olmadan devam edilir."
        ),
    },
    {
        "name": "Finnhub",
        "purpose": "ABD hisseleri için ek kotasyon ve şirket haberleri (BIST'i kapsamaz)",
        "key_required": "Evet (ücretsiz)",
        "register_url": "https://finnhub.io/register",
        "docs_url": "https://finnhub.io/docs/api",
        "section": "finnhub",
        "keys": ("api_key",),
        "note": "Anahtar Dashboard > API Key altında. Ücretsiz planda BIST sembolleri boş döner.",
    },
    {
        "name": "Google Gemini",
        "purpose": "Bot'taki isteğe bağlı kısa AI yorumu",
        "key_required": "Evet",
        "register_url": "https://aistudio.google.com/app/api-keys",
        "docs_url": "https://ai.google.dev/gemini-api/docs/quickstart",
        "section": "gemini",
        "keys": ("api_key", "model"),
        "note": "Model olarak çalışan 'gemini-3.1-flash-lite' kullanılır. Anahtar AI Studio > API keys sayfasından alınır.",
    },
    {
        "name": "Alpaca Paper",
        "purpose": "Kurgusal emir simülasyonu (yalnızca test ortamı; BIST desteklemez)",
        "key_required": "Evet (test hesabı)",
        "register_url": "https://app.alpaca.markets/paper/dashboard/overview",
        "docs_url": "https://alpaca.markets/docs/",
        "section": "alpaca_paper",
        "keys": ("key_id", "secret_key", "base_url"),
        "note": "Girişte hem Key ID hem Secret Key gerekir. Şu an secret eksik, bu yüzden hesap bağlantısı kapalı.",
    },
    {
        "name": "Twilio",
        "purpose": "SMS uyarıları (opsiyonel)",
        "key_required": "Evet",
        "register_url": "https://www.twilio.com/try-twilio",
        "docs_url": "https://www.twilio.com/docs/messaging/quickstarts",
        "section": "twilio",
        "keys": ("account_sid", "auth_token", "from_number"),
        "note": "Account SID, Auth Token ve gönderen numara gerekir; şu an tanımlı değil.",
    },
    {
        "name": "Inngest",
        "purpose": "Arka plan iş akışları (opsiyonel, henüz kullanılmıyor)",
        "key_required": "Evet",
        "register_url": "https://www.inngest.com/",
        "docs_url": "https://api-docs.inngest.com/authentication",
        "section": "inngest",
        "keys": ("signing_key", "event_key"),
        "note": "Anahtarlar saklandı; tanımlı bir iş akışı olmadığı için kullanılmıyor.",
    },
    {
        "name": "yfinance / Yahoo Finance",
        "purpose": "Günlük OHLCV ve backtest verisi",
        "key_required": "Hayır",
        "register_url": "https://finance.yahoo.com/",
        "docs_url": "https://ranaroussi.github.io/yfinance/",
        "section": None,
        "keys": (),
        "note": "Kısmi gün barı ve ~gecikmeli veri olasılığı vardır.",
    },
]


def _configured(service: dict[str, Any]) -> tuple[bool, str]:
    section = service.get("section")
    if not section:
        return True, "Anahtar gerekmiyor"
    keys = service["keys"]
    present = {k: bool(secrets_access.get(section, k)) for k in keys}
    if all(present.values()):
        return True, "Tüm anahtarlar tanımlı"
    if any(present.values()):
        missing = ", ".join(k for k, v in present.items() if not v)
        return False, f"Eksik: {missing}"
    return False, "Tanımlı değil"


def _snippet(service: dict[str, Any]) -> str:
    section = service.get("section")
    if not section:
        return "# Bu kaynak için anahtar gerekmez."
    lines = [f"[{section}]"]
    for key in service["keys"]:
        value = "<BURAYA_DEĞERİ_YAZIN>"
        lines.append(f'{key} = "{value}"')
    return "\n".join(lines)


def render_guide() -> None:
    """Servis servis kayıt adresi, amaç ve yapılandırma durumu gösterir."""
    for service in SERVICES:
        configured, status_text = _configured(service)
        with st.container(border=True):
            with st.container(horizontal=True, vertical_alignment="bottom"):
                st.markdown(f"#### {service['name']}")
                st.badge(
                    "HAZIR" if configured else "EKŞİK",
                    color="green" if configured else "orange",
                    help="Anahtar değeri gösterilmez; yalnızca tanımlı olup olmadığı kontrol edilir.",
                )
            st.caption(f"**Amaç:** {service['purpose']}")
            st.caption(f"**Veri kaynağı / anahtar:** {service['key_required']} · **Durum:** {status_text}")
            with st.container(horizontal=True):
                st.link_button(
                    "Kayıt ol / anahtar al", service["register_url"],
                    icon=":material/open_in_new:", key=f"reg_{service['name'].split()[0]}",
                )
                st.link_button(
                    "Doküman", service["docs_url"],
                    icon=":material/menu_book:", key=f"doc_{service['name'].split()[0]}",
                )
            if service.get("section"):
                st.markdown("**`.streamlit/secrets.toml` içine eklenecek bölüm:**")
                st.code(_snippet(service), language="toml")
            st.caption(service["note"])


def _read_secrets() -> dict[str, Any]:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {}


def _write_secrets(data: dict[str, Any]) -> None:
    lines: list[str] = [
        "# YEREL GİZLİ ANAHTARLAR - COMMIT ETMEYİN",
        "# Bu dosya .gitignore ile dışlanır.",
        "",
    ]
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {json.dumps(str(value), ensure_ascii=False)}")
        lines.append("")
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text("\n".join(lines), encoding="utf-8")


def render_editor() -> None:
    """Tarayıcıdan anahtar güncelleme (değerler maskelenir, boş bırakılan değişmez)."""
    with st.expander("Anahtarları tarayıcıdan düzenle", icon=":material/key:"):
        st.caption(
            "Boş bırakılan alanlar değiştirilmez. Kayıt dosyası `.streamlit/secrets.toml` "
            "üzerine yazılır ve `.gitignore` ile dışlanır. Yorum satırları korunmaz."
        )
        with st.form("api_key_editor", border=False):
            updates: dict[str, dict[str, str]] = {}
            for service in SERVICES:
                section = service.get("section")
                if not section:
                    continue
                st.markdown(f"**{service['name']}**")
                for key in service["keys"]:
                    value = st.text_input(
                        f"{section}.{key}",
                        type="password",
                        key=f"keyedit_{section}_{key}",
                        placeholder="Değiştirmek için yeni değeri yazın",
                        help=h("api_key_editor"),
                    )
                    if value:
                        updates.setdefault(section, {})[key] = value
            if st.form_submit_button("Anahtarları kaydet", type="primary"):
                if not updates:
                    st.info("Değiştirilecek anahtar girilmedi.", icon=":material/info:")
                else:
                    data = _read_secrets()
                    for section, values in updates.items():
                        data.setdefault(section, {}).update(values)
                    _write_secrets(data)
                    st.success("Anahtarlar kaydedildi. Önbellek temizleniyor...", icon=":material/check:")
                    st.cache_data.clear()
                    st.rerun()
        st.warning(
            "Güvenlik: Bu anahtarlar sohbete yazıldıysa sağlayıcı panellerinden yenileyin (rotate).",
            icon=":material/warning:",
        )


def render_gateio_editor() -> None:
    """Gate.io API anahtarı için maskeli yerel giriş formu."""
    with st.expander("Gate.io API anahtarını buraya girin", icon=":material/key:"):
        st.caption(
            "Yalnızca Gate.io **API Key / Secret** girin; giriş şifreniz değil. "
            "Testnet anahtarı: gate.io/testnet → API Keys. Withdrawal izni vermeyin."
        )
        with st.form("gateio_key_editor", border=False):
            key = st.text_input("API Key", type="password", key="gate_key_input")
            secret = st.text_input("API Secret", type="password", key="gate_secret_input")
            if st.form_submit_button("Yerel olarak kaydet", type="primary"):
                if not key or not secret:
                    st.warning("İki alan da gerekli.", icon=":material/warning:")
                else:
                    data = _read_secrets()
                    data.setdefault("gateio", {}).update({"key": key, "secret": secret})
                    _write_secrets(data)
                    st.success("Gate.io anahtarı yerel secrets.toml dosyasına kaydedildi.", icon=":material/check:")
                    st.cache_data.clear()
                    st.rerun()


def render_binance_editor() -> None:
    """Binance API anahtarını doğrudan bot panelinden girmek için küçük form.

    Binance **giriş şifresi buraya yazılmaz**; yalnızca API Management ekranında
    üretilen `api_key` ve `secret_key` yazılır. Değerler maskelenir ve yalnızca
    yerel `.streamlit/secrets.toml` dosyasına kaydedilir.
    """
    with st.expander("Binance API anahtarını buraya girin", icon=":material/key:"):
        st.caption(
            "⚠️ Binance **kullanıcı adı ve giriş şifrenizi BURAYA YAZMAYIN.** "
            "Yalnızca API Management → Create API ekranında üretilen **API Key** ve "
            "**Secret Key** değerlerini girin. Giriş şifreniz hiçbir yere kaydedilmez."
        )
        with st.form("binance_key_editor", border=False):
            api_key = st.text_input(
                "API Key", type="password", key="bin_api_key_input",
                placeholder="API Management ekranındaki API Key",
            )
            secret_key = st.text_input(
                "Secret Key", type="password", key="bin_secret_input",
                placeholder="Secret Key (bir kez gösterilir)",
            )
            if st.form_submit_button("Yerel olarak kaydet", type="primary"):
                if not api_key or not secret_key:
                    st.warning("İki alan da gerekli.", icon=":material/warning:")
                else:
                    data = _read_secrets()
                    data.setdefault("binance", {}).update({
                        "api_key": api_key, "secret_key": secret_key,
                    })
                    _write_secrets(data)
                    st.success(
                        "Anahtarlar yerel secrets.toml dosyasına kaydedildi "
                        "(depoya gitmez). Önbellek temizleniyor.",
                        icon=":material/check:",
                    )
                    st.cache_data.clear()
                    st.rerun()
        st.caption(
            "Fotoğrafta/görüntüde görünen veya sohbete yazılan bir secret kullanmayın; "
            "Binance panelinden iptal edip yenisi üretin."
        )
