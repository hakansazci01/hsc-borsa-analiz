# HKC Borsa Analiz — Detaylı Denetim Raporu

Tarih: 18.11.2026
Kapsam: `borsa_bot/` (11 modül), `ui/` (17 modül), `app_pages/` (8 sayfa), `streamlit_app.py`, `config.yaml`.

Yöntem:
1. Tüm dosyaların satır satır statik incelemesi (iki bağımsız denetim turu)
2. `compileall` + tüm modüllerin temiz Python sürecinde import edilmesi
3. AppTest ile 8 sayfa ve 40+ etkileşim (buton, seçim, kaydet/sıfırla, bot, indirme)
4. Uç durum testleri: boş izleme listesi, 800+ sembol havuzundan seçim, BIST100
5. Çalışan uygulamada Agent API ile tüm sayfalar + konsol uyarı takibi
6. Widget anahtarı çakışması taraması (30 anahtar, 0 çakışma)

---

## Kritik hatalar ve düzeltmeler

### K1 — Backtest'te son açık pozisyon iki kez sayılıyordu
`backtest.py`: Son barda pozisyon kapatılıp gelir `capital`'e ekleniyor, ancak `position` sıfırlanmadığı için `final_equity = capital + position * last_close` ile tekrar ekleniyordu.
**Etkisi:** Kapanmamış işlem varsa getiri, CAGR ve drawdown tamamen yanlıştı. Doğrulanan örnek: sermaye 99.950,05 ₺ iken `final_equity` 109.940,05 ₺ ve getiri %9,94 görünüyordu (gerçek ≈ −%0,05).
**Düzeltme:** `_close_position()` pozisyonu sıfırlıyor; `final_equity = capital` her durumda.

### K2 — Backtest ham puanı, canlı sinyal normalize puanı kullanıyordu
`generate_signal()` puanı `sum(weights)` ile normalize edip ±5 ölçeğinde sınıflandırıyor; backtest ise ham puanı doğrudan `classify()`'a veriyordu.
**Etkisi:** Ham 2,5 backtest'te AL iken canlıda `2,5/7*5 = 1,79 → NÖTR` oluyordu. Yani backtest, kullanılan stratejiyi test etmiyordu.
**Düzeltme:** `signals.score_to_signal()` tek paylaşımlı fonksiyon; her iki katman da bunu kullanıyor. Doğrulama: son bar için backtest sinyali ile canlı sinyal **birebir eşleşiyor** (NEUTRAL, −0.5393 ≈ −0.54).

### K3 — SAT sinyali açık pozisyonu kapatmıyordu
Giriş kodu `if position == 0:` bloğundaydı; açık long pozisyonda SAT/STRONG_SELL tamamen yok sayılıyordu.
**Düzeltme:** `elif position > 0 and sig in ("SELL","STRONG_SELL")` dalı eklendi; ertesi gün kapanışında kayma ile çıkış yapılıyor.

---

## Orta önemde hatalar ve düzeltmeler

| # | Hata | Düzeltme |
|---|---|---|
| M1 | Giriş gününün High/Low değeriyle stop kontrolü (look-ahead) | `entry_index` takibi; giriş günü kontrol atlanıyor |
| M2 | Kayma (slippage) hiç modellenmemişti | Giriş/çıkışta %0,1 varsayılan kayma + duyarlılık tablosu |
| M3 | `indicators.rsi_oversold/overbought` config'den okunmuyordu | `Config.signal_thresholds` bu iki anahtarı tek noktada birleştiriyor |
| M4 | CAGR her zaman 252 gün varsayımı (haftalık veride ~5× hata) | Gerçek `DatetimeIndex` aralığından yıl hesabı |
| M5 | `min_periods=1` ile 2 veriden "SMA200", çöken Bollinger bantları | SMA50/200, Bollinger ve Stokastik için `min_periods=window` |
| M6 | Sermaye eğrisi işlemin yapılmadığı barın kapanışında işaretleniyordu | Ertesi gün (dolgu) kapanışında işaretleme |
| M7 | Boş izleme listesinde `KeyError: 'Sinyal'` | Piyasa sayfasında erken `st.info` + `st.stop()` |
| M8 | Hisse detayında ilk açılışta periyot/aralık `None` | `default=` eklendi; yine de `None` gelirse settings değeri |
| M9 | WebSocket bağlantı hatası `cache_resource`'da kalıcı önbelleğe alınıyordu | Factory içinde hata yutuluyor, `live_quote()` yeniden deniyor |
| M10 | 800+ BIST sembolü için `.IS` eki yalnızca 24'lük sözlükte ekleniyordu | Universe üzerinden `.IS`, BIST100 hariç |
| M11 | Ayarlarda "sembol ekle" widget durumunu geç oluşturuyordu | `on_click` callback + `pending_symbol`, widget'tan önce uygulanıyor |
| M12 | Aynı widget hem `default=` hem `session_state` ile besleniyordu (uyarı) | Yalnızca `session_state`, `default=` kaldırıldı |

---

## Düşük önemde hatalar ve düzeltmeler

| # | Hata | Düzeltme |
|---|---|---|
| L1 | Raporlanan VWAP kümülatif, karar ise kaydırılmalı VWAP kullanıyordu | `VWAP_Rolling` rapora da yansıtıldı |
| L2 | NaN gösterge değerleri JSON'a `NaN` olarak yazılıyordu | `num()` yardımcısı ile NaN → varsayılan; `allow_nan=False` ile doğrulandı |
| L3 | Önbellek anahtarında `auto_adjust` yoktu; önbellek okuma temizleme atlıyordu | Anahtara eklendi; `_clean()` hem yolda hem ağda uygulanıyor |
| L4 | Tek satırlık veride OBV yanlış negatif sinyal üretiyordu | `_score()`'a `has_prev` parametresi |
| L5 | `add_cross_flags` SMA50/SMA200 kolonlarını varsayıyordu | Kolon varlığı kontrolü; yoksa nötr bayrak |
| L6 | CSV dışa aktarımda tutarsız anahtar `ValueError` verebilirdi | Tüm satırların anahtar birleşimi + `extrasaction="ignore"` |
| L7 | Paylaşılan WebSocket stream'de thread yarışı | `threading.Lock()` ile connect/subscribe koruması |
| L8 | `signals["1d"]` `None` olabileceğinde `.get()` zinciri patlıyordu | `(... or {})` zinciri |
| L9 | `allow_short: true` ölü kodu (`pass`) | Kaldırıldı; sistem yalnızca long destekliyor (açıkça belirtildi) |

---

## Düzeltmelerin ölçülebilir etkisi

| Sembol | Önce (eski backtest) | Sonra (doğru backtest) |
|---|---|---|
| THYAO.IS | 8 işlem, %12,5 kazanma, −%2,7 getiri | 0 işlem (canlı sinyal NÖTR ile tutarlı) |
| GARAN.IS | 10 işlem | 1 işlem |
| ASELS.IS | — | 1 işlem |
| ISCTR.IS | — | 3 işlem |
| SISE.IS | — | 2 işlem |

Bu düşüş hata değil, **hatanın düzelmesidir**: eski backtest canlı sinyalden daha agresif bir stratejiyi test ediyordu.

---

## İyileştirme turu (uzman sistem karşılaştırması)

| Kaynak | Öne çıkan yaklaşım | Uygulamaya eklenen |
|---|---|---|
| freqtrade | Protections: CooldownPeriod, StoplossGuard, MaxDrawdown | `borsa_bot/guards.py` — cooldown, stop guard, günlük limit, drawdown kademeleri |
| riskkit | DrawdownManager kademe merdiveni, SessionManager günlük limitler | Drawdown 3/5/8% kademeleri, min spacing, günlük zarar limiti |
| LEAN | Alpha → Portfolio → Risk → Execution ayrımı | Karar motoru, risk motoru ve emir taslağı ayrı katmanlar |
| vectorbt | Walk-forward + parametre kararlılığı | `ui/validation.py` + Strateji laboratuvarı sayfası |

Performans: backtest sinyal hesabı O(n²)'den O(n)'e indirildi (5 backtest: ~3,5 sn → 0,23 sn).

## Kalan sınırlamalar (güvenli biçimde düzeltilemez)

1. **Ücretsiz BIST verisi ~15 dk gecikmeli.** Lisanslı veri gerekir.
2. **Örneklem küçük** (1-3 işlem). İstatistiksel anlamlılık yok.
3. **THYAO beklentisi negatif** (önceki denetimde −%5,1). Strateji bu hisse için işlem önermiyor.
4. **Haber duyarımı sözlük tabanlı**; yorum hatası olabilir.
5. **Walk-forward doğrulama yok.**
6. **Aracı kurum emir iletimi yok** ve olmayacak; manuel emir taslağı üretiliyor.
7. **Günlük bar içinde stop/hedef sırası bilinmiyor**; stop önce kabul ediliyor (temkinli varsayım).
8. **yfinance kısmi gün barı** bazen geçerli Close ile gelebiliyor (düşük olasılık).

---

## Doğrulama matrisi

| Kontrol | Sonuç |
|---|---|
| `compileall` (tüm paketler) | ✅ |
| 26 modülün temiz import'u | ✅ |
| 8 sayfa + 40+ etkileşim (AppTest) | ✅ 0 istisna |
| Uç durumlar (boş liste, 800+ sembol, BIST100) | ✅ |
| Widget anahtar çakışması (30 anahtar) | ✅ 0 |
| Agent API — tüm sayfalar + bot | ✅ `ready`, 0 exception |
| Çalışan uygulama konsolu | ✅ uyarı yok |
| Backtest/canlı sinyal eşleşmesi | ✅ birebir |
| JSON `allow_nan=False` | ✅ |
| Varsayılan ayarlar dosyası | ✅ temiz (kullanıcı ayarı yok) |

**Sonuç:** Bilinen çalışma zamanı hatası yok. Bu, stratejinin doğru veya kârlı olduğu anlamına **gelmez**; Denetim sayfasının 9 maddelik kontrol listesi hâlâ **"GERÇEK PARA İÇİN ONAYLANMADI"** diyor.
