# Otonom Sistem — Gerçek Durum Özeti

**Son güncelleme:** 2026-11-21 06:01:33  
**Kaynak:** Yerel karar kayıtları, gerçek Binance TR API ve işlem defteri. Tahmin/simülasyon değildir.

## 1. Sistem sağlığı

| Ölçü | Değer |
|---|---|
| Toplam otonom karar | 39 |
| OPEN kararı | 0 |
| CLOSED kararı | 39 |
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
| İşlem defteri kaydı | 20 |

## 4. Neden işlem yok?

Son kararın gerekçesi: ayı rejimi (-20.79%)

Sistem yalnızca **doğrulanmış edge + yukarı rejim** birlikte olduğunda işlem açar. Bu koşul sağlanmadığı için para riske atılmaz; bu bir arıza değil, kasıtlı korumadır.

## 5. Sektör araştırması — karlı botlar ne yapıyor?

222M gerçek işlemlik akademik çalışma (2026): karlı botların sırrı doğru tahmin değil **doğru giriş fiyatı** (execution). Perakende %51,3 isabetle kaybederken botlar %49,9 isabetle 133M $ kâr ediyor; ~%70'i erken giriş ve spread ödememekten (limit emir). Bizim sistemde execution, rejim filtresi, disiplin ve doğrulanmış backtest **mevcut**. Eksikler: BNB komisyon indirimi (açılabilir), short/futures (spot long only), kolokasyon (günlük stratejide gerekmez) ve sermaye büyüklüğü.

## 6. KOD DENETİMİ — kanıtlı bulgular (VAR / YOK)

| Madde | Durum | Kanıt (dosya:satır) |
|---|---|---|
| API key/secret kodda açık | **YOK** | `ui/secrets_access.py:18,34-48` — `.streamlit/secrets.toml` + env |
| Withdraw/transfer emri | **YOK** | `git grep withdraw` → sadece `ui/api_keys.py:233,256` uyarı metni, `ui/binance_tr_bot.py:123` salt okunur alan |
| Anahtarı dışarı gönderme | **YOK** | `ui/notify.py:61-109` sadece metin bildirim; anahtar gönderen kod yok |
| Stop-Loss | **VAR %0,35** | `ui/tr_scalper.py:38,210,355` |
| Take-Profit | **VAR %0,80** | `ui/tr_scalper.py:37,209,350` |
| Trailing stop | **VAR %0,35** | `ui/tr_scalper.py:39-40,344-345` |
| Pozisyon boyutu | **VAR %15 / ₺50–100** | `ui/tr_scalper.py:32-33,195` |
| Aynı anda max işlem | **VAR 1** (tek `position`) | `ui/tr_scalper.py:328` + `sell` sonrası `st.pop("position")` :259 |
| Toplam zarar kilidi | **VAR ₺15** | `ui/tr_scalper.py:34,264-269` |
| Günlük zarar limiti | **YOK** ⚠️ | Sadece toplam realized PnL var; gün bazlı sıfırlama yok |
| Kasa drawdown kilidi | **YOK** ⚠️ | Kodda `drawdown` kontrolü emir yolunda yok |
| Ani çöküş koruması (5dk %10) | **YOK** ⚠️ | `ui/tr_scalper.py:322-375` tur başına fiyat kontrolü var ama %10 eşik yok |
| Martingale | **YOK** | `ui/tr_scalper.py:195` sabit bütçe; `qty*2` yok |
| Backtest (1 yıl) | **VAR ~1,4 yıl / 1000 günlük mum** | `ui/quant_lab.py:23`, `research/research_daily.py` |
| Max drawdown sonucu | **%16–62** (strateji) | `docs/STRATEJI_ARASTIRMA_SONUCU.md:87` |
| Paper/Testnet | **YOK ⚠️ (Binance TR)** | `config.yaml:110-118` `binance_tr` testnet alanı YOK; `binance_bot.py:59` sadece global Binance testnet |
| İşlem logu | **VAR JSONL** | `ui/tr_journal.py:21-29`, `ui/tr_scalper.py:249-255` |
| trades.csv | **YOK** ⚠️ | Sadece JSONL (event/position/pnl), fiyat/id ayrı alan değil |
| Hata/çökme bildirimi | **VAR ntfy** | `ui/trade_notify.py:38-46`, `ui/notify.py:102-117` |
| Bağlantı hatası | **YOK ediliyor, devam** | `ui/binance_tr_bot.py:96-101`, `ui/tr_runner.py:112-114` |
| RSI/MACD/Bollinger/Grid | **RSI var, diğerleri YOK** | `ui/tr_scalper.py:119-143` (RSI7 + EMA9/20 + hacim) |

## 7. Ne zaman işlem yapılacak?

- BTC günlük kapanışı EMA50'nin üstüne geçmeli
- Hedef coin günlük EMA50 üzerinde pullback yapmalı
- Öngörü isabeti en az %40 olmalı
- O an motor kendiliğinden açılır, ₺50–100 limit emir atar ve deftere+bildirime yazar

---

Bu rapor her otonom analiz turunda otomatik yenilenir (`reports/OTONOM_OZET.md`).
