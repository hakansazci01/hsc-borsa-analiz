"""
Gerçek para hazırlık kontrolü.

Yazılımın yapabileceği ile kullanıcının/yetkili kurumların yapması gereken
işleri net bir kontrol listesinde gösterir. Durumları abartmaz: yapılmayan
hiçbir maddesi "tamam" işaretlemez.

Bu modül anahtar değeri okumaz/göstermez; yalnızca varlık/yokluk kontrolü yapar.
"""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st

from ui import broker, live_guard, secret_policy, source_attestation
from ui.core import default_settings


def assess() -> list[dict[str, Any]]:
    settings = default_settings()
    cfg = live_guard.config(settings)
    att = source_attestation.load()

    def who(kind: str) -> str:
        return kind

    items: list[dict[str, Any]] = [
        {
            "Madde": "Canlı broker API anahtarı (alpaca_live)",
            "Sorumlu": "SİZ",
            "Durum": "VAR" if broker.live_configured() else "YOK",
            "Yapılacak": "Yetkili aracı kurumdan canlı API anahtarı alın; secrets.toml → [alpaca_live] bölümüne yazın. Asla depoya/OneDrive'a koymayın.",
        },
        {
            "Madde": "live_trading.enabled = true",
            "Sorumlu": "SİZ (onay)",
            "Durum": "AÇIK" if cfg.get("enabled") else "KAPALI",
            "Yapılacak": "Yasal/broker önkoşulları tamamlandıktan sonra config.yaml içinde tek satırı değiştirin.",
        },
        {
            "Madde": "HSC_LIVE_ARMED=YES ortam değişkeni",
            "Sorumlu": "SİZ",
            "Durum": "VAR" if os.environ.get("HSC_LIVE_ARMED") == "YES" else "YOK",
            "Yapılacak": "Uygulamayı başlatmadan önce sistem ortamına HSC_LIVE_ARMED=YES tanımlayın.",
        },
        {
            "Madde": "Arayüzde onay ifadesi + oturum onayı",
            "Sorumlu": "SİZ",
            "Durum": "ANLIK",
            "Yapılacak": "Canlı işlem sayfasındaki GERÇEK PARA panelinde ifadeyi yazıp oturumu onaylayın.",
        },
        {
            "Madde": "Kill switch kapalı",
            "Sorumlu": "SİZ",
            "Durum": "KAPALI" if not st.session_state.get("signals_off") else "AÇIK",
            "Yapılacak": "Sol menüdeki 'Sinyalleri kapat' anahtarını kapatın.",
        },
        {
            "Madde": "SPK / BIST algoritmik işlem bildirimi",
            "Sorumlu": "SİZ / AVCILIK KURUMU",
            "Durum": "DOĞRULANDI" if source_attestation.is_current("SPK/BIST algoritmik işlem bildirimi") else "DOĞRULANMADI",
            "Yapılacak": "BIST taahhütnamesi ve SPK bildirimini aracı kurum üzerinden tamamlayın; Denetim → Kaynak doğrulama bölümünden tarih kaydedin.",
        },
        {
            "Madde": "Lisanslı gerçek zamanlı BIST verisi",
            "Sorumlu": "SİZ",
            "Durum": "DOĞRULANDI" if source_attestation.is_current("Lisanslı gerçek zamanlı veri") else "DOĞRULANMADI",
            "Yapılacak": "BIST DDA / yetkili sağlayıcı ile abonelik yapın; 15 dk gecikmeli veri gerçek emir için yeterli değildir.",
        },
        {
            "Madde": "OIDC + MFA oturum güvenliği",
            "Sorumlu": "BİZ (yazılım) + SİZ (sağlayıcı)",
            "Durum": "YOK",
            "Yapılacak": "Kimlik sağlayıcı (IdP) seçip secrets.toml [auth] yapılandırması gerekir; mevcut yerel PBKDF2 oturumu yeterli değildir.",
        },
        {
            "Madde": "Secrets saklama ve rotasyonu",
            "Sorumlu": "SİZ",
            "Durum": "POLİTİKA VAR" if secret_policy.load() else "KAYIT YOK",
            "Yapılacak": "docs/SECRET_ROTATION.md uygulayın; anahtarları OneDrive dışında tutun, IP allowlist açın, para çekme yetkisi vermeyin.",
        },
        {
            "Madde": "Demo ortamında emir testi / sertifikasyon",
            "Sorumlu": "SİZ + BROKER",
            "Durum": "KISMEN",
            "Yapılacak": "Broker test ortamında emir/iptal/kısmi dolum senaryolarını çalıştırın; uygulama birim testleri hazır.",
        },
        {
            "Madde": "Günlük broker mutabakatı",
            "Sorumlu": "BİZ (yazılım)",
            "Durum": "YOK",
            "Yapılacak": "Canlı hesap bakiyesi ile yerel kurgusal portföy arasında otomatik mutabakat ve fark halinde emir durdurma eklenecek.",
        },
        {
            "Madde": "7/24 servis ve izleme",
            "Sorumlu": "BİZ (yazılım) + SİZ (altyapı)",
            "Durum": "YOK",
            "Yapılacak": "Streamlit oturumu yeterli değil; worker + kuyruk + izleme + yedekleme gerekiyor.",
        },
    ]
    return items


def render() -> None:
    with st.expander("GERÇEK PARA hazırlık kontrol listesi", icon=":material/checklist:"):
        st.caption(
            "Bu liste yazılımın yapabileceği ile sizin yapmanız gereken işleri ayırır. "
            "Hiçbir madde otomatik 'tamam' işaretlenmez. Gerçek para için **onay yoktur**."
        )
        data = assess()
        st.dataframe(
            pd.DataFrame(data),
            hide_index=True,
            use_container_width=True,
            alt="Gerçek para geçişi için kimin ne yapacağını gösteren hazırlık kontrol listesi",
        )
        done = sum(1 for i in data if i["Durum"] in ("VAR", "AÇIK", "DOĞRULANDI"))
        st.caption(f"Kontrol edilen {len(data)} maddeden {done} tanesi olumlu durumda.")
