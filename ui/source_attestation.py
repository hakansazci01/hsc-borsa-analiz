"""
Kaynak doğrulama attestation'ları.

BIST VBTS/tedbir listeleri, KAP veri akışı ve temettü ex-date takvimi için
ücretsiz, güvenilir, makine okunabilir bir kaynak yok. Bu yüzden otomatik
scraping yapılmaz; kullanıcı resmi kaynağı *elle* doğrular ve son geçerlilik
tarihini kaydeder.

Kritik kural: kayıt yoksa veya süresi geçtiyse "temiz" varsayılmaz.
Sistem durumu UNKNOWN olarak gösterilir ve manuel kontrol istenir.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import streamlit as st

from ui import auth, log_store


ATTESTATION_FILE = "source_attestations.json"

SOURCES: tuple[str, ...] = (
    "BIST VBTS / tedbir listesi",
    "KAP özel durum akışı",
    "Temettü ex-date takvimi",
    "Fiyat verisi sağlayıcısı (auto_adjust ayarı)",
    "SPK/BIST algoritmik işlem bildirimi",
    "Lisanslı gerçek zamanlı veri",
)


def _path() -> Path:
    return auth.USERS_DIR / ATTESTATION_FILE


def load() -> dict[str, Any]:
    data = auth.read_json(_path(), {})
    return data if isinstance(data, dict) else {}


def is_current(name: str) -> bool:
    record = load().get(name) or {}
    until = str(record.get("valid_until") or "")
    if not until:
        return False
    try:
        return date.fromisoformat(until) >= date.today()
    except ValueError:
        return False


def save(name: str, url: str, verified: date, until: date, note: str) -> None:
    data = load()
    data[name] = {
        "url": str(url)[:500],
        "last_verified": verified.isoformat(),
        "valid_until": until.isoformat(),
        "note": str(note)[:500],
        "saved_at": auth._now(),
    }
    auth.write_json(_path(), data)
    log_store.append(
        auth.USERS_DIR / "source_attestation_log.jsonl",
        {"time": auth._now(), "event": "SOURCE_ATTESTED", "source": name, "valid_until": until.isoformat()},
    )


def render_panel() -> None:
    with st.expander("Kaynak doğrulama ve bilinmeyen durumlar", icon=":material/verified_user:"):
        st.caption(
            "Bu kaynaklar için güvenilir ücretsiz API yoktur. Otomatik veri çekilmez; "
            "resmi adresi siz kontrol edip son doğrulama tarihini kaydedersiniz. "
            "Kayıt yoksa veya süresi geçtiyse sistem **bilinmiyor** kabul eder, temiz varsaymaz."
        )
        data = load()
        for name in SOURCES:
            current = is_current(name)
            record = data.get(name) or {}
            st.markdown(f"**{name}**")
            st.badge(
                "DOĞRULANDI" if current else "DOĞRULANMADI / SÜRESİ GEÇTİ",
                color="green" if current else "red",
                icon=":material/check_circle:" if current else ":material/warning:",
            )
            with st.container(border=True):
                url = st.text_input(
                    "Resmi kaynak adresi", value=str(record.get("url") or ""),
                    key=f"att_url_{name}",
                )
                c1, c2 = st.columns(2)
                verified = c1.date_input(
                    "Son kontrol", value=date.today() - timedelta(days=1),
                    key=f"att_ver_{name}",
                )
                until = c2.date_input(
                    "Geçerlilik bitişi", value=date.today() + timedelta(days=30),
                    key=f"att_until_{name}",
                )
                note = st.text_input(
                    "Not (örn. sürüm/tarih)", value=str(record.get("note") or ""),
                    key=f"att_note_{name}",
                )
                if st.button("Doğrulamayı kaydet", key=f"att_save_{name}"):
                    if not url.strip():
                        st.warning("Kaynak adresi gerekli.", icon=":material/warning:")
                    elif until < verified:
                        st.warning("Bitiş tarihi son kontrolden önce olamaz.", icon=":material/warning:")
                    else:
                        save(name, url, verified, until, note)
                        st.toast(f"{name} doğrulaması kaydedildi.", icon=":material/check:")
                        st.rerun()
