# Otonom Sistem — Gerçek Durum Özeti

**Son güncelleme:** 2026-11-21 03:47:29  
**Kaynak:** Yerel karar kayıtları, gerçek Binance TR API ve işlem defteri. Tahmin/simülasyon değildir.

## 1. Sistem sağlığı

| Ölçü | Değer |
|---|---|
| Toplam otonom karar | 36 |
| OPEN kararı | 0 |
| CLOSED kararı | 36 |
| Son karar | **CLOSED** |
| Piyasa rejimi | ASAGI (bear) |
| Doğrulanmış kârlı edge | 49 |

## 2. Öngörü başarısı (self-test)

| Ölçü | Değer |
|---|---|
| Gerçek fiyatla test edilen öngörü | 20 |
| Doğru | 18 |
| Yanlış | 2 |
| İsabet oranı | **%90.0** |

> Her öngörü, bir sonraki turda gerçekleşen BTC fiyatıyla karşılaştırılır.

## 3. İşlem ve sermaye

| Ölçü | Değer |
|---|---|
| Gönderilen emir kaydı | 0 |
| Kapanmış işlem | 1 |
| Net K/Z | **-0.07 ₺** |
| Toplam komisyon | 0.0057 ₺ |
| Kullanılabilir bakiye | **506.26 ₺** |
| Açık pozisyon | Yok |
| İşlem defteri kaydı | 15 |

## 4. Neden işlem yok?

Son kararın gerekçesi: ayı rejimi (-20.05%)

Sistem yalnızca **doğrulanmış edge + yukarı rejim** birlikte olduğunda işlem açar. Bu koşul sağlanmadığı için para riske atılmaz; bu bir arıza değil, kasıtlı korumadır.

## 5. Sektör araştırması — karlı botlar ne yapıyor?

222M gerçek işlemlik akademik çalışma (2026): karlı botların sırrı doğru tahmin değil **doğru giriş fiyatı** (execution). Perakende %51,3 isabetle kaybederken botlar %49,9 isabetle 133M $ kâr ediyor; ~%70'i erken giriş ve spread ödememekten (limit emir). Bizim sistemde execution, rejim filtresi, disiplin ve doğrulanmış backtest **mevcut**. Eksikler: BNB komisyon indirimi (açılabilir), short/futures (spot long only), kolokasyon (günlük stratejide gerekmez) ve sermaye büyüklüğü.

## 6. Ne zaman işlem yapılacak?

- BTC günlük kapanışı EMA50'nin üstüne geçmeli
- Hedef coin günlük EMA50 üzerinde pullback yapmalı
- Öngörü isabeti en az %40 olmalı
- O an motor kendiliğinden açılır, ₺50–100 limit emir atar ve deftere+bildirime yazar

---

Bu rapor her otonom analiz turunda otomatik yenilenir (`reports/OTONOM_OZET.md`).
