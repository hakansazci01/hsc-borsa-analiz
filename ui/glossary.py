"""
Teknik terimlerin sade dille karşılığı.

Amaç: kullanıcı karmaşık göstergeleri gördüğünde "bu ne anlama geliyor?"
sorusuna uygulamanın içinde hemen yanıt bulabilmesi. Hiçbir analiz sonucunu
değiştirmez; yalnızca açıklama sağlar.
"""

from __future__ import annotations

import streamlit as st


TERMS: dict[str, str] = {
    "AL / BEKLE / SAT": (
        "Sistemin hissenin yönü için verdiği trafik lambası. Yeşil AL alım düşünülebileceği, "
        "sarı BEKLE beklemenin daha uygun olduğu, kırmızı SAT satış baskısının öne çıktığı anlamına gelir. "
        "Bu bir emir değil, yalnızca karar desteğidir."
    ),
    "Güven skoru": (
        "Sinyalin ne kadar tutarlı olduğunu gösteren 0-100 arası değer. Yüksek olması daha fazla "
        "gösterge birbirini onaylıyor demektir; kazanç garantisi değildir."
    ),
    "RSI": (
        "Göreli Güç Endeksi. 30'un altına düşmesi aşırı satım (alım fırsatı olabilir), "
        "70'in üstüne çıkması aşırı alım (satış baskısı olabilir) olarak yorumlanır."
    ),
    "MACD": (
        "Kısa ve uzun vadeli ortalama arasındaki farkın değişimini gösterir. Sinyal çizgisini yukarı "
        "kesmesi genelde AL, aşağı kesmesi SAT yönü olarak okunur."
    ),
    "EMA / SMA": (
        "Üstel ve basit hareketli ortalamalar. Fiyatın son dönemdeki ortalama değerini gösterir; "
        "fiyatın bunların üzerinde olması genelde yükseliş eğilimi olarak okunur."
    ),
    "VWAP": (
        "Hacim ağırlıklı ortalama fiyat. O seanstaki 'adil fiyat' çizgisi kabul edilir; "
        "fiyatın üstünde olması alıcıların, altında olması satıcıların kontrolünde olduğunu düşündürür."
    ),
    "Bollinger bantları": (
        "Fiyatın normalde hareket ettiği üst ve alt sınırlar. Fiyat üst banda yaklaşırsa aşırı alım, "
        "alt banda yaklaşırsa aşırı satım ihtimali gündeme gelir."
    ),
    "Hacim": (
        "O gün el değiştiren hisse adedi. Fiyat hareketi hacimle desteklenirse sinyal daha güvenilir kabul edilir."
    ),
    "Piyasa rejimi": (
        "Piyasanın genel karakteri: yükseliş, düşüş, yatay veya hareketli (oynak). "
        "Rejim, hangi yöntemin ve hangi pozisyon büyüklüğünün uygun olduğunu belirler."
    ),
    "ATR": (
        "Ortalama Gerçek Aralık. Hisse bir günde ortalama ne kadar hareket ediyor gösterir; "
        "stop mesafesi buna göre ayarlanır."
    ),
    "R çarpanı": (
        "Kârın alınan riske oranı. Stop mesafesi 1R kabul edilir; +2R, alınan riskin iki katı kâr demektir. "
        "Farklı hisseleri adil karşılaştırmak için kullanılır."
    ),
    "Stop-loss": (
        "Zarar durdur seviyesi. Fiyat bu seviyeye gelirse kurgusal işlem kapatılır; "
        "kaybın büyümesini engellemek içindir."
    ),
    "Take-profit (hedef)": (
        "Kâr alma seviyesi. Fiyat buraya ulaştığında pozisyonun kapatılması hedeflenir. "
        "1.5R / 2.5R / 4R kademeleri riskin 1.5, 2.5 ve 4 katı kâr demektir."
    ),
    "Kelly kriteri": (
        "Kazanma oranı ve kazanç/kayıp dengesine göre ideal risk payını hesaplayan formül. "
        "Aşırı riski önlemek için yarım Kelly ve sert tavan uygulanır."
    ),
    "Monte Carlo": (
        "Geçmiş işlemleri rastgele yeniden sıralayarak binlerce olası gelecek senaryosu üretir. "
        "Tek bir tahmin değil, olasılık aralığı gösterir."
    ),
    "Backtest": (
        "Stratejinin geçmiş fiyat verisi üzerinde kurgusal olarak çalıştırılması. "
        "Geçmişte nasıl davranacağını gösterir; geleceği garanti etmez."
    ),
    "Sharpe / Sortino / Calmar": (
        "Risk/getiri ölçüleridir. Sharpe toplam volatiliteyi, Sortino sadece aşağı yönlü hareketi, "
        "Calmar ise getirinin maximum düşüşe oranını dikkate alır. 1 üzeri genelde iyi kabul edilir."
    ),
    "Maksimum düşüş": (
        "Kurgusal sermayenin ulaştığı en yüksek seviyeden gördüğü en büyük gerileme. "
        "Stratejinin dayanıklılığını gösterir; küçük olması iyidir."
    ),
    "İstatistiksel doğrulama": (
        "Stratejinin şans eseri iyi görünüp görünmediğini test eden kontrollerdir "
        "(permutasyon testi, Deflated Sharpe, walk-forward). Amaç kendimizi kandırmamaktır."
    ),
    "Kurgusal işlem (paper)": (
        "Gerçek para kullanılmadan, sadece simülasyonda açılan pozisyon. "
        "Uygulama hiçbir aracı kuruma emir göndermez."
    ),
}


def render_glossary(expanded: bool = False) -> None:
    """Sade dil sözlüğünü katlanabilir panel olarak gösterir."""
    with st.expander("Teknik terimler sade dille", icon=":material/menu_book:", expanded=expanded):
        st.caption("Burada göremeyeceğiniz bir terim mi var? Açıklama analizi etkilemez, sadece yardımcı olur.")
        for term, meaning in TERMS.items():
            st.markdown(f"**{term}:** {meaning}")
