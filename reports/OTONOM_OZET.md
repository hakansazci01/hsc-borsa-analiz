# Otonom Sistem — Gerçek Durum Özeti

**Son güncelleme:** 2026-11-21 06:38:38  
**Kaynak:** Yerel karar kayıtları, gerçek Binance TR API ve işlem defteri. Tahmin/simülasyon değildir.

## 1. Sistem sağlığı

| Ölçü | Değer |
|---|---|
| Toplam otonom karar | 41 |
| OPEN kararı | 0 |
| CLOSED kararı | 41 |
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
| Kapanmış işlem | 0 |
| Net K/Z | **+0.00 ₺** |
| Toplam komisyon | 0.0000 ₺ |
| Kullanılabilir bakiye | **506.26 ₺** |
| Açık pozisyon | Yok |
| İşlem defteri kaydı | 22 |

## 4. Neden işlem yok?

Son kararın gerekçesi: ayı rejimi (-22.61%)

Sistem yalnızca **doğrulanmış edge + yukarı rejim** birlikte olduğunda işlem açar. Bu koşul sağlanmadığı için para riske atılmaz; bu bir arıza değil, kasıtlı korumadır.

## 5. Sektör araştırması — karlı botlar ne yapıyor?

222M gerçek işlemlik akademik çalışma (2026): karlı botların sırrı doğru tahmin değil **doğru giriş fiyatı** (execution). Perakende %51,3 isabetle kaybederken botlar %49,9 isabetle 133M $ kâr ediyor; ~%70'i erken giriş ve spread ödememekten (limit emir). Bizim sistemde execution, rejim filtresi, disiplin ve doğrulanmış backtest **mevcut**. Eksikler: BNB komisyon indirimi (açılabilir), short/futures (spot long only), kolokasyon (günlük stratejide gerekmez) ve sermaye büyüklüğü.

## 6. KOD KANITI — son değişiklikler

- Strateji: `ui/tr_scalper.py:154-166` `signal()` → `quant_lab.signals(frame,'pullback',(50,))`.
  1-dk RSI7/EMA9/20 TAMAMEN kaldırıldı. STOP-LOSS `:38` EMA50*0.97.
- Frenler (500 TL kasa): `ui/risk_brakes.py:25` günlük -50 TL; `:26` referans 500 TL;
  `:27` kasa %10 = -50 TL drawdown → STOP_FILE; `:28,30` 5 dk %5 çöküş → 30 dk.
- Tek işlem: `config.yaml:115-116` max_order_usdt/max_order_try = 50 TL;
  `ui/tr_scalper.py:90-93` okunur, `:226-233` emirde uygulanır.
- Config kilitleri: `ui/tr_scalper.py:53-59` enabled=false engeller; `:62-66` max_order_usdt
  config'den okunur, `:226-233` emirde uygulanır. STOP'a güvenilmez.
- Onay ifadesi: `ui/tr_scalper.py` `set_confirmed_phrase()` / `is_phrase_confirmed()` /
  `config_gate()` — `HSC-BINANCE-TR-ARM` doğrulanmadan enabled=true olsa bile RED.
  Test: `tests/test_live_guard.py::test_confirmation_phrase_gate` (doğru/yanlış/enabled=true).
- trades.csv: `ui/tr_scalper.py:285-294` her satışta 9 sütun yazar.
- İlk emir kontrolleri: config_gate → STOP → frenler → fiyat → step/minNotional →
  tutar limiti → imzalı POST /open/v1/orders.

## 7. Ne zaman işlem yapılacak?

- BTC günlük kapanışı EMA50'nin üstüne geçmeli
- Hedef coin günlük EMA50 üzerinde pullback yapmalı
- Öngörü isabeti en az %40 olmalı
- O an motor kendiliğinden açılır, ₺50–100 limit emir atar ve deftere+bildirime yazar

---

Bu rapor her otonom analiz turunda otomatik yenilenir (`reports/OTONOM_OZET.md`).
