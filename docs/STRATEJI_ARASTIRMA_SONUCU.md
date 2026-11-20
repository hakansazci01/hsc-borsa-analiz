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

## Karar

Zararlı beklentisi kanıtlanmış stratejiyle **canlı işlem durduruldu**. Daha fazla para
yatırmadan önce şunlar gerekir:

1. **BNB ile komisyon ödeme** hesap ayarından açılmalı (komisyon %0,1 → %0,075;
   hâlâ tek başına yeterli değil).
2. Daha büyük sermaye: `stepSize`/`minNotional` toz kaybı oransız hale gelir
   (₺7 yerine en az birkaç yüz TL).
3. Farklı bir edge: hacim/volatilite rejimi filtresi, daha uzun tutuş, veya
   doğrulanmış bir strateji — **backtest pozitif çıkmadan canlıya alınmamalı**.

Bu dosya, "kar odaklı" iddiasının dürüst karşılığıdır: şu an elimizde kârlı bir
strateji **yok**; olduğunu söylemek yanlış olur.

## Tekrar çalıştırma

Araştırma betikleri oturum dizinindedir (`backtest_tune.py`, `backtest_broad.py`).
Yeni veriyle tekrar koşup pozitif expectancy bulunursa strateji güncellenir.
