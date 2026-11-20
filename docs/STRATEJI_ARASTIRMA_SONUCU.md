# Strateji araştırma sonucu — gerçek veri, komisyon sonrası

Tarih: 2026-11-20 · Kaynak: Binance TR / `api.binance.me` gerçek 1-dk ve 5-dk mumlar.

## Yöntem

7 gerçek TRY çifti (XRP, DOGE, ADA, TRX, LTC, LINK, FORM), her biri son 500 dakikalık
OHLCV. Dört giriş mantığı (aşırı satımdan ilk yükseliş, ikinci yükseliş, EMA kırılımı +
hacim, EMA kesişimi), 4 RSI eşiği, 3 TP, 2 SL, 2 zaman dilimi ve 2 tutuş süresi:
**toplam 228 kombinasyon.** Her işlemde alış + satış komisyonu %0,1 + %0,1 = **%0,2**
düşüldü.

## Sonuç

| Ölçü | Değer |
|---|---|
| Test edilen kombinasyon | 228 |
| **Pozitif expected value** | **0** |
| En iyi kombinasyon | 1dk, RSI<30, TP %0,8, SL %0,5 → **-%0,098 / işlem** |
| En kötü kombinasyon | 5dk breakout → **-%0,406 / işlem** |
| Kazanma oranı (en iyi) | %25 |
| Canlı pilot işlem (FORM_TRY) | **-₺0,0694 net** (gerçek, komisyon dahil) |

Yani mevcut sinyal ailesi **parametre değiştirilerek kârlı hale getirilemiyor.**
Bu bir kod hatası değil; %0,2 komisyonun kısa vadeli gürültü üstünde baskın olması.

## Spread (maker) alternatifi

| Çift | Spread | Komisyon sonrası |
|---|---|---|
| XRP_TRY | %0,020 | -%0,180 |
| ADA_TRY | %0,130 | -%0,070 |
| **FORM_TRY** | **%0,496** | **+%0,296** (teorik) |

FORM_TRY'de teorik edge var, **ama uygulanamıyor**:
- `LOT_SIZE.stepSize = 0,1`, `NOTIONAL.minNotional = ₺5`
- Alışta komisyon base varlıktan kesiliyor: 0,7 FORM alınca **0,69867** geliyor
- Satış için 0,7 yetmiyor (insufficient), 0,6 ise ₺5 minimumun altında (3210)
- Her tur ~0,1 FORM (~₺0,80) toz kaybı → sermayenin %14'ü

`quoteOrderQty` ile piyasa satışı çalışıyor (dust sorununu aşar) ama bu sefer
spread'i ödeyerek satış yapılır; maker edge'i kaybolur. Limit emirde `quoteOrderQty`
API tarafından kabul edilmiyor (400).

## İkinci tur: uzun zaman dilimi + dış örneklem doğrulaması

21 gerçek seri (7 coin × 15d/1s/4s), 1000'er mum. 4 strateji ailesi
(EMA kesişimi, breakout, RSI dönüşü, trend pullback), 83 kombinasyon.
İlk %60 eğitim, son %40 test ayrıldı; eğitimde seçilen parametre testte doğrulandı.

| Sonuç | Değer |
|---|---|
| Eğitim ve testi **ikisi de pozitif** | **0 / 83** |
| Test'te pozitif | 6 / 83 (eğitimde çoğu negatif) |
| En iyi eğitim sonucu | +%3,17 → test **-%2,93** (klasik overfitting) |

### Piyasa rejimi (kritik)

Son 30 günün gerçek verisi — **tüm coin'ler %26–34 düştü**:

| Coin | 30 günlük al-sat-tut |
|---|---|
| BTC | -%26,0 |
| ETH | -%29,5 |
| XRP | -%29,5 |
| DOGE | -%30,6 |
| ADA | -%34,2 |
| LINK | -%29,1 |

Binance TR **spot** hesabında short (kısa) pozisyon yok. Yani mevcut ayı piyasasında
**long-only bir stratejinin kâr etmesi matematiksel olarak çok zor.** Test edilen
hiçbir strateji bu rejimde pozitif çıkmadı.

## Üçüncü tur: günlük (1d) zaman dilimi — EDGE BULUNDU

15dk/1s/4s yetersiz çıktıktan sonra **günlük** veri denendi (9 coin, 1000'er mum,
%0,2 komisyon, %60/%40 eğitim-test).

| Sonuç | Değer |
|---|---|
| Test edilen kombinasyon | 306 |
| **Eğitim + test ikisi de pozitif** | **50** ✅ |
| Doğrulanan strateji | **Günlük EMA50 pullback** |
| 9 coin'in pozitif olanı | **8 / 9** |
| Ortalama işlem getirisi | **+%5,21** (komisyon sonrası) |
| Kazanma oranı | %14–40 (az ama büyük kazananlar — trend takibi) |
| Maksimum drawdown | %16–62 (uzun tutuş riski → sıkı risk sınırları şart) |

**Önemli:** Aynı parametre (EMA50) tek bir coin'de değil **8 farklı coin'de** pozitif
çıktı. Bu, tek bir eğri uydurması (overfitting) olmadığının güçlü işaretidir.

### Fakat şu an giriş sinyali YOK

Doğrulama anında **9 coin'in tamamı günlük EMA50'nin altındaydı**. Stratejinin giriş
koşulu "fiyat EMA50 üzerine çıktığında pullback" olduğu için **şu an hiçbir emir
tetiklenmiyor.** BTC günlük EMA50'nin %17 altında.

Bu bir hata değil, sistemin doğru çalıştığı anlamına gelir: edge var ama **rejim
uygun değil.** Otonom yönetici, fiyat EMA50 üzerine geçtiği anda motoru kendiliğinden
açacak; edge bozulunca veya rejim tersine dönünce duracak.

## Karar

Canlı motor şu an **kapalı** — tek neden: ayı rejimi (BTC EMA50 %-17). Edge artık
**doğrulanmış durumda** (50 aday). Yani "gerçek veride kârlı çıkarsa aç" şartı
**kısmen sağlandı**; geri kalan tek koşul piyasanın yukarı rejime dönmesi.

Daha fazla para yatırmadan önce şunlar gerekir:

1. **BNB ile komisyon ödeme** hesap ayarından açılmalı (komisyon %0,1 → %0,075;
   hâlâ tek başına yeterli değil).
2. Daha büyük sermaye: `stepSize`/`minNotional` toz kaybı oransız hale gelir
   (₺7 yerine en az birkaç yüz TL).
3. Farklı bir edge: hacim/volatilite rejimi filtresi, daha uzun tutuş, veya
   doğrulanmış bir strateji — **backtest pozitif çıkmadan canlıya alınmamalı**.
4. Piyasa rejimi değişimi: ayı piyasasında spot long-only yerine ya nakitte kalınmalı
   ya da short/futures için ayrı (ve çok riskli) bir altyapı kurulmalı. Bu proje
   şu an yalnızca spot long içerir.

Bu dosya, "kar odaklı" iddiasının dürüst karşılığıdır: şu an elimizde kârlı bir
strateji **yok**; olduğunu söylemek yanlış olur.

## Tekrar çalıştırma

Araştırma betikleri oturum dizinindedir (`backtest_tune.py`, `backtest_broad.py`).
Yeni veriyle tekrar koşup pozitif expectancy bulunursa strateji güncellenir.
