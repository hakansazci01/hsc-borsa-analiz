"""
Gemini tabanlı isteğe bağlı AI yorumu.

Amaç: Karar motorunun ürettiği somut verileri Türkçe, şeffaf ve temkinli
biçimde özetlemek. Modelden yeni veri/fiyat uydurması istenmez; yorum
her zaman "yatırım tavsiyesi değildir" notuyla döner. Ücretli/hatalı
çağrılarda sessizce devre dışı kalır.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

import streamlit as st

from ui.secrets_access import get


SYSTEM_INSTRUCTION = (
    "Sen BIST hisseleri için teknik analiz yorumcususun. Sana verilen verileri kullanarak "
    "kısa ve anlaşılır bir Türkçe değerlendirme yaz. Kurallar: "
    "(1) Verilenlerin dışında fiyat, haber, tarih veya oran uydurma. "
    "(2) Kesinlikle 'AL/SAT' emri verme; sadece mevcut sinyalin gerekçesini ve risklerini açıkla. "
    "(3) Zayıf veya çelişkili kanıt varsa bunu açıkça söyle. "
    "(4) Son cümle mutlaka 'Bu yorum yatırım tavsiyesi değildir.' olsun. "
    "(5) En fazla 120 kelime kullan."
)


def build_digest(symbol: str, decision: dict[str, Any], snap: dict[str, Any], regime: dict[str, Any] | None) -> str:
    info = snap.get("info", {}) or {}
    lines = [
        f"Sembol: {symbol}",
        f"Karar: {decision.get('decision')} (guven %{decision.get('confidence')}, skor {decision.get('score')})",
        f"Fiyat: {info.get('price')}, gunluk degisim %{decision.get('change_pct')}",
        f"Seans: {info.get('session')}, veri kaynagi: {snap.get('quote_source')}",
        f"Rejim: {regime.get('regime') if regime else 'bilinmiyor'}",
        "Teknik zaman dilimleri: " + ", ".join(
            f"{t['timeframe']}={t['recommendation']}(AL{t['buy']}/SAT{t['sell']})"
            for t in decision.get("technical", {}).get("timeframes", [])
        ),
        "KAP haberleri: " + ("; ".join(i["title"][:70] for i in decision.get("news", {}).get("items", [])[:5]) or "yok"),
    ]
    return "\n".join(lines)


@st.cache_data(ttl="15m", show_spinner=False)
def gemini_commentary(digest: str) -> tuple[str | None, str | None]:
    """Gemini'den kısa yorum alır. (yorum, hata) döndürür; hata varsa yorum None."""
    key = get("gemini", "api_key")
    if not key:
        return None, "Gemini anahtarı yapılandırılmadı."
    model = get("gemini", "model", "gemini-3.1-flash-lite")

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"parts": [{"text": digest}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 320},
    }
    url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={key}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        text = out["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text, None
    except Exception as exc:
        # Anahtarı/asla hata mesajında gösterme
        return None, f"AI yorumu alınamadı ({type(exc).__name__})."
