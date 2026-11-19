"""
İnsan odaklı asistan katmanı.

Amaç: "AI gibi" parlamak değil, kullanıcının kararını *değerlendirmesine*
yardım etmek. 2025-2026 fintech AI yönergelerinden türetilen ilkeler:

- Güveni artırmak değil, **doğru güven (appropriate reliance)** sağlamak
- Tek taraflı "AL" yerine **lehte / aleyhte / geçersizleştiren** kanıtlar
- Belirsizliği ve veri yaşını saklamamak, gerektiğinde yanıt vermekten kaçınmak
- Kullanıcıyı onaylamak için değil, riskleri göstermek için çalışmak (anti-sycophancy)
- Gemini anahtarı yoksa da **işe yarar** deterministik yanıt üretmek

Bu modül hiçbir emir göndermez, yatırım tavsiyesi vermez, gerçek fiyat iddia etmez.
"""

from __future__ import annotations

import re
from typing import Any


LIMITS_TEXT = (
    "Gecikmeli BIST verisiyle **kurgusal** portföyünü analiz ederim. "
    "Canlı fiyat, gerçek emir ve yatırım tavsiyesi **vermem**; "
    "gördüğün her sonuç bir sinyal/yorumdur, kesinlik değildir."
)


INTENTS: dict[str, tuple[str, ...]] = {
    "capabilities": ("ne yaparsın", "ne yapabilirsin", "kimsin", "nedir bu", "yardım", "merhaba", "selam"),
    "portfolio": ("portföyüm", "portfoyum", "pozisyonlarım", "portföyümü incele", "kurgusal portföy"),
    "why": ("neden", "niye", "gerekçe", "neden al", "neden sat", "neden bekle"),
    "suitability": ("bana uygun mu", "risk profilim", "riskime uygun", "uygun mu", "suitable"),
    "changes": ("bugün ne değişti", "ne değişti", "haber", "son sinyal", "değişim"),
    "benchmark": ("xu100", "bist 100", "endeks", "kıyasla", "karsilastir", "benchmark"),
    "provenance": ("kaynak", "kaynağı", "verinin", "veri yaşı", "ne zaman", "güncel mi", "gecikme", "tazelik"),
    "risk": ("risk", "stop", "kayıp", "zarar", "korelasyon", "yoğunlaşma"),
    "live_price": ("şu an", "anlık fiyat", "canlı fiyat", "gerçek zamanlı", "şu anki fiyat"),
    "prediction": ("yarın", "yükselecek mi", "düşecek mi", "kesin", "garanti", "kaçırır mıyım"),
    "order": ("emir ver", "al emri", "sat emri", "gerçek para", "broker", "hesabıma al"),
}


# Kullanıcıyı onaylamaya çalışan / gerçek emir isteyen ifadelerde durdurucu kurallar.
GUARD_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\b(emir ver|emrini ver|al emri|sat emri|gerçek para|broker|aracı kurum)\b", re.I),
        "emir",
        "Bu uygulama **emir göndermez** ve gerçek parayla işlem yapmaz. "
        "Tüm pozisyonlar kurgusaldır; alım/satım kararını yalnızca sen verirsin.",
    ),
    (
        re.compile(r"\b(kesin|garanti|mutlaka|yüzde yüz|100%|kaçırma)\b", re.I),
        "kesinlik",
        "Hiçbir sinyal **kesin** değildir. Ücretsiz veri ~15 dk gecikmeli ve "
        "geçmiş performans geleceği garanti etmez. Kesinlik içeren bir yargı veremem.",
    ),
    (
        re.compile(r"\b(şu anki fiyat|canlı fiyat|gerçek zamanlı fiyat|anlık fiyat)\b", re.I),
        "canli_fiyat",
        "Şu anki **gerçek fiyatı** veremem; elimdeki veri gecikmeli. "
        "Güncel fiyatı KAP veya aracı kurum ekranından kontrol etmelisin.",
    ),
    (
        re.compile(r"\b(yarın.*(yüksel|düş|art|azal)|yükselir mi|düşer mi)\b", re.I),
        "tahmin",
        "Yarınki fiyatı tahmin edemem. Sana ancak **senaryo ve olasılık** "
        "çerçevesi sunabilirim; yön garantisi veremem.",
    ),
    (
        re.compile(r"\b(haklıyım|doğru değil mi|almalıyım değil mi|onayla|kabul et)\b", re.I),
        "onay",
        "Ben senin görüşünü **onaylamak için** değil, riskleri ve karşıt kanıtları "
        "göstermek için buradayım. Bu sinyali geçersiz kılacak ne olabilir?",
    ),
]


def detect_intent(text: str) -> str:
    """Kullanıcı cümlesini basit, deterministik bir niyete eşler."""
    value = (text or "").strip().lower()
    if not value:
        return "capabilities"
    # Önce güvenlik/kısıt kategorileri (daha spesifik olanlar önce)
    for intent in ("order", "live_price", "prediction"):
        if any(word in value for word in INTENTS[intent]):
            return intent
    for intent, words in INTENTS.items():
        if intent in ("order", "live_price", "prediction"):
            continue
        if any(word in value for word in words):
            return intent
    return "general"


def guard_check(text: str) -> str | None:
    """Yanıt verilmeden önce uygulanması gereken güvenlik uyarısını döndürür."""
    for pattern, _kind, message in GUARD_RULES:
        if pattern.search(text or ""):
            return message
    return None


def suggestions(intent: str, symbol: str | None = None) -> list[str]:
    """Bağlama uygun, kullanıcının aklına gelmeyecek soruları önerir."""
    target = symbol or "bu hisse"
    base: dict[str, list[str]] = {
        "capabilities": [
            "Portföyümü incele",
            f"{target} için neden bu sinyal?",
            "Verinin kaynağı ve yaşı nedir?",
        ],
        "portfolio": [
            "Portföyümde nerede yoğunlaşma var?",
            "Açık pozisyonlarımın riskini sırala",
            "Risk profilime uygun muyum?",
        ],
        "why": [
            f"{target} için karşıt kanıtlar neler?",
            "Bu sinyali ne geçersiz kılar?",
            "XU100'a göre karşılaştır",
        ],
        "suitability": [
            "Risk profilimi nereden düzenlerim?",
            "Portföy yoğunlaşmamı göster",
            "Kurgusal işlemlerin maliyetini dahil et",
        ],
        "changes": [
            "Son sinyal değişimlerini göster",
            "Bugün hangi hissede KAP haberi var?",
            "Sinyal performans defterini aç",
        ],
        "benchmark": [
            "BIST 100'a göre farkım ne?",
            "Hisseyi sektörüyle karşılaştır",
            "Korelasyon matrisini göster",
        ],
        "provenance": [
            "Veri kaç dakika önce alındı?",
            "Hesaplamada hangi göstergeler kullanıldı?",
            "Eksik veri var mı?",
        ],
        "risk": [
            "Stop mesafemi ATR'ye göre hesapla",
            "En kötü senaryoda ne kadar kaybederim?",
            "Korelasyon riskimi göster",
        ],
        "general": [
            "Ne yapabilirsin?",
            "Portföyümü incele",
            f"{target} sinyalini açıkla",
        ],
    }
    return base.get(intent, base["general"])


def two_sided_rationale(
    rec: dict[str, Any] | None,
    info: dict[str, Any] | None,
    bt: dict[str, Any] | None,
    regime: dict[str, Any] | None,
) -> str:
    """Gözlenen verilerden lehte / aleyhte / geçersizleştiren kanıtlar üretir."""
    if not rec or not info:
        return (
            "Bu hisse için yeterli veri yok; yorum üretmek yerine **veri bekliyorum**. "
            "Başka bir hisse deneyin veya birazdan tekrar sorun."
        )

    action = str(rec.get("action", "BEKLE"))
    confidence = int(rec.get("confidence", 0) or 0)
    signal = str(info.get("signal", "NEUTRAL"))
    rsi = info.get("rsi")
    score = info.get("score")
    drawdown = abs(float((bt or {}).get("max_drawdown_pct", 0) or 0))
    regime_name = str((regime or {}).get("regime", "Yatay"))

    supportive: list[str] = []
    against: list[str] = []
    invalidators: list[str] = []

    if signal in ("BUY", "STRONG_BUY"):
        supportive.append("göstergelerin ağırlıklı toplamı alım yönünde")
    else:
        against.append("göstergelerin ağırlıklı toplamı alım yönünde değil")
    if isinstance(rsi, (int, float)):
        if float(rsi) < 35:
            supportive.append(f"RSI {float(rsi):.0f} ile aşırı satım bölgesinde")
        elif float(rsi) > 65:
            against.append(f"RSI {float(rsi):.0f} ile aşırı alım bölgesinde")
        else:
            invalidators.append("RSI net bir yön vermiyor")
    if isinstance(score, (int, float)):
        if float(score) >= 2:
            supportive.append(f"sinyal puanı {float(score):+.2f} ile eşiğin üzerinde")
        elif float(score) <= -2:
            against.append(f"sinyal puanı {float(score):+.2f} ile satış yönünde")
        else:
            against.append(f"sinyal puanı {float(score):+.2f} eşik bölgesinde")
    if drawdown > 20:
        against.append(f"geçmiş testteki maksimum düşüş %{drawdown:.1f} yüksek")
    if regime_name in ("Düşüş", "Yüksek oynaklık"):
        against.append(f"piyasa rejimi {regime_name.lower()} — temkinli olunmasını gerektiriyor")
    invalidators.append("KAP'ta yeni bir açıklama veya seans dışı fiyat hareketi")
    invalidators.append("hacimde ani düşüş veya sinyal yönünün tersine dönmesi")

    def _bullets(items: list[str]) -> str:
        return " · ".join(items) if items else "belirgin bir kanıt yok"

    return (
        f"**Karar:** {action} · güven %{confidence}\n\n"
        f"**Lehte olanlar:** {_bullets(supportive)}\n\n"
        f"**Aleyhte olanlar:** {_bullets(against)}\n\n"
        f"**Bunu geçersiz kılacaklar:** {_bullets(invalidators)}\n\n"
        f"*Bu bir yorumdur; gözlemler ile yorumlar ayrı tutulmuştur. "
        "Gecikmeli veri nedeniyle kesin fiyat veya yön garantisi verilmez.*"
    )
