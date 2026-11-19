# Gerçek para ile işlem için gereksinimler (Yol Haritası)

> **Durum: UYGULAMA GERÇEK PARA İÇİN ONAYLANMAMIŞTIR.**
> Bu doküman bir *plan* ve *eksiklik analizidir*. Depoda **varsayılan olarak tamamen
> kilitli** bir gerçek emir kodu yolu bulunmaktadır (`ui/live_guard.py`,
> `ui/live_bot.py`, `ui/broker.py::place_live_order`). Kilitler açılmadan hiçbir ağ
> çağrısı yapılmaz; canlı API anahtarı depoda yoktur. Bu, "gerçek para hazır" anlamına
> **gelmez**: yasal/broker önkoşulları ve aşağıdaki eksiklikler devam etmektedir.

## Neden sadece "emir gönder" değil?

Paper modunda hata = yanlış görünen bir sayı. Gerçek paradaysa hata = **kaybedilen
sermaye, yasal sorumluluk ve veri/broker yasağı**. Bu yüzden aşağıdaki katmanların
tamamı gerekir.

---

## 1. Yasal ve düzenleyici önkoşullar

- **SPK / BIST mevzuatı:** Algoritmik emir iletim sistemleri için Borsa İstanbul'un
  *Algoritmik Emir İletim Sistemleri Taahhütnamesi* kapsamında; kullanılan yazılım,
  sunucu lokasyonu, protokol (FIX/OUCH), test tarihleri ve sonuçları BIST'e bildirilir.
- **Aracı kurum izni:** Perakende müşteriye API/emir erişimi veren, yetkili bir
  aracı kurumla sözleşme gerekir. Birçok kurum API'yi yalnızca kurumsal müşterilere açar.
- **Kullanım amacı:** Yalnızca kendi hesabınız için otomasyon ile başkalarına sinyal/
  yönetim hizmeti sunmak arasında büyük yasal fark vardır. İkincisi yatırım danışmanlığı/
  portföy yönetimi lisansı gerektirebilir.
- **KYC / MASAK:** Kimlik doğrulama, fon kaynağı ve vergi/record-keeping yükümlülükleri.
- **Bildirim ve değişiklik kontrolü:** Algoritma veya model versiyonu değiştiğinde
  aracı kuruma/BIST'e bildirim zorunluluğu olabilir (AI model versiyonu dahil).

## 2. Broker / emir API'si

- Desteklenen emir tipleri: piyasa, limit, stop, stop-limit, iptal, değiştirme,
  kısmi dolum (partial fill), lot büyüklüğü ve fiyat adımı (tick) kuralları.
- **Emir yaşam döngüsü:** `NEW → ACK → PARTIAL → FILLED / CANCELLED / REJECTED`;
  her durum için zaman damgası ve broker emir numarası.
- **Idempotency:** aynı emrin Streamlit rerun / ağ hatası nedeniyle iki kez gitmemesi
  için deterministik anahtar (`symbol + decision + as_of + qty`).
- **Before/after reconciliation:** yerel kurgusal portföy ile broker hesabı günlük
  mutabakatı; fark varsa işlemi durdur.
- Rate limit, backoff + jitter, devre kesici (circuit breaker), açık/okunabilir hata mesajları.

## 3. Veri

- **Lisanslı gerçek zamanlı fiyat:** 15 dakika gecikmeli ücretsiz veri gerçek işlem
  için yeterli değildir (BIST DDA / yetkili veri sağlayıcı gerekir).
- Kurumsal işlem (bedelsiz/bedelli/temettü) **düzeltilmiş** ve zamanında (point-in-time)
  fiyat serisi; mevcut karantina mekanizması genişletilir.
- Kaynak, alınma zamanı, gecikme ve bozuk veri bayrağı her emir kaydına eklenir.
- İkinci kaynaktan çapraz doğrulama ve "uyuşmazlık varsa emir yok" kuralı.

## 4. Execution / OMS katmanı (yeni)

- **Pre-trade kontroller:** yeterli nakit, pozisyon/lot sınırı, seans ve tedbir
  (VBTS) durumu, fiyat bandı, günlük zarar limiti, kill switch.
- **Risk limitleri:** azami açık pozisyon, tek hissede yoğunlaşma, günlük zarar
  ve drawdown eşiği; kaldıraç yok (başlangıçta).
- **Kill switch:** tek anahtarla tüm yeni emirlerin durması (mevcut paper kill switch
  gerçek moda da geçerli olmalı).
- **Emir kuyruğu ve durum makinesi**, tekrar deneme politikası, zaman aşımı,
  kısmi dolumda tutarlı portföy güncellemesi.
- **Değiştirilemez denetim kaydı:** istek, cevap, karar gerekçesi, veri yaşı,
  model/sürüm, kullanıcı onayı, timestamp (mevcut `audit_log` genişletilir).

## 5. Güvenlik

- Broker API anahtarları **asla** depoya/OneDrive'a yazılmaz; secrets manager veya
  şifreli yerel depot; IP allowlist; en az yetki (read+trade, withdrawal yok).
- **OIDC + MFA** (mevcut yerel PBKDF2 oturumu yerine); oturum süresi/kilit mekanizması.
- Gerçek mod ayrı bir görünümde, ek onay ve görünür uyarılarla açılır; paper mod
  varsayılan kalır.
- Tüm dış çağrılar TLS, loglarda anahtar/token asla görünmez.

## 6. Güvenilirlik ve operasyon

- Sürekli çalışan servis (Streamlit oturumu yeterli değil): worker + kuyruk + izleme.
- Health/readiness kontrolü: veri tazeliği, broker bağlantısı, saat senkronizasyonu,
  yazılabilir depolama, kill switch durumu.
- Yedekleme, geri yükleme, olay müdahale planı, log saklama süresi, düzenli tatbikat.
-Broker tarafı sertifikasyon / test ortamında kabul testleri.

## 7. Test ve doğrulama (önce paper, sonra küçük canlı)

- Mevcut 14 test + 16 sayfa AppTest'i koru; ayrıca:
  - broker kontrat testleri (gerçek API şeması, emir durumları),
  - replay/senaryo testleri (kesinti, kısmi dolum, reject, bağlantı kopması),
  - emir idempotency testleri, mutabakat testleri,
  - kill switch ve limit testleri,
  - gerçek moda geçişte **kademeli limit** (çok küçük sermaye, kısa süre, gözetim).

## 8. Kullanıcı arayüzü

- Ayrı **GERÇEK PARA** modu: varsayılan kapalı, açmak için ek onay adımı.
- Her emir öncesi net özet: sembol, yön, adet, fiyat, tutar, stop/hedef, risk %.
- "Bu bir yatırım tavsiyesi değildir" ve "otomatik emir" uyarıları kalıcı.
- Canlı modda tüm kararlar ve emirler denetim kaydında; kullanıcı iptal/edite edebilir.

---

## Mevcut durum vs gereksinim

| Katman | Bizde var mı? | Eksik |
|---|---|---|
| Sinyal/gerekçe/istatistiksel doğrulama | ✅ | — |
| Risk motoru, pozisyon boyutu, Monte Carlo | ✅ | canlı limitlerin broker ile eşleşmesi |
| Denetim kaydı, veri kapısı, kill switch (paper) | ✅ | gerçek emir kapsamına genişletme |
| **Lisanslı gerçek zamanlı veri** | ❌ | BIST DDA / yetkili sağlayıcı |
| **Broker API + OMS** | ⚠️ kilitli iskelet var | gerçek anahtar, mutabakat, dolum yönetimi, test sertifikasyonu |
| **SPK/BIST bildirim ve taahhüt** | ❌ | tamamı |
| **OIDC + MFA + secrets vault** | ❌ | tamamı (mevcut kilitler oturum onayı + ortam değişkeni + onay ifadesi) |
| **7/24 servis, mutabakat, operasyon** | ❌ | tamamı |

## Önerilen sıra

1. Yasal/broker önkoşullar netleşmeden **hiçbir gerçek emir kodu yazılmaz**.
2. Gerçek zamanlı lisanslı veri + kurumsal işlem düzeltmesi tamamlanır.
3. OMS, pre-trade limitler, idempotency, mutabakat, değiştirilemez denetim.
4. OIDC + MFA + secrets vault + IP allowlist.
5. Broker test ortamında kademeli doğrulama → çok küçük canlı pilot → gözetimli ölçekleme.

## Binance testnet ile güvenli başlangıç (önerilen)

Canlı BIST yerine önce **sanal para** ile gerçek emir mekaniğini test edebilirsiniz:

1. `testnet.binance.vision` adresine gidin → **API Management** → yeni API anahtarı oluşturun.
   Bu anahtar **gerçek borsa anahtarından farklıdır** ve sanal bakiyeyi kullanır.
2. API izinlerinde **yalnızca "Enable Spot Trading"** açık olsun;
   **"Enable Withdrawals" kesinlikle kapalı** kalsın. Mümkünse IP kısıtlaması ekleyin.
3. Anahtarı **sohbete yapıştırmayın**; kendi bilgisayarınızda
   `.streamlit/secrets.toml` dosyasına şunu yazın:
   ```toml
   [binance]
   api_key = "buraya-testnet-key"
   secret_key = "buraya-testnet-secret"
   ```
4. `config.yaml` → `binance.enabled: true` ve `binance.testnet: true` (varsayılan).
5. Uygulamayı başlatmadan önce ortam değişkeni: `HSC_BINANCE_ARMED=YES`.
6. **Canlı işlem** sayfasındaki *Binance botu* panelinde: sembol → **15m sinyal al** →
   onay ifadesi (`HSC-BINANCE-ARM`) → oturum onayı → miktar → **Binance emir gönder**.

Güvenlik kilitleri: `enabled` + ortam değişkeni + onay ifadesi + oturum onayı + anahtar +
kill switch + izinli sembol + tek emir limiti. Bunlardan biri eksikse **hiçbir ağ çağrısı yapılmaz**.

Canlı Binance için ayrıca `HSC_BINANCE_LIVE=YES` ve `binance.testnet: false` gerekir;
**bunu acele etmeden, küçük tutarlarla ve gözetim altında yapın.**

## Görev paylaşımı (kim ne yapacak?)

**Yazılım tarafı (bizim yapabileceğimiz):**
- Gerçek emir kod yolu, kilitler, idempotency, denetim kaydı ✅ (mevcut)
- Hazırlık kontrol paneli (`ui/live_readiness.py`) ✅ (mevcut)
- Otomatik mutabakat, 7/24 worker/kuyruk/izleme, IdP entegrasyonu, broker test senaryoları ⬜ (sıradaki işler)

**Kullanıcı / yetkili kurum tarafı (bizim yapamayacağımız):**
1. Yetkili aracı kurumda hesap + **canlı API anahtarı** (para çekme yetkisi olmadan, IP allowlist ile)
2. **SPK / BIST algoritmik işlem bildirimi ve taahhütnamesi** (aracı kurum üzerinden)
3. **Lisanslı gerçek zamanlı BIST verisi** aboneliği
4. KYC / MASAK ve vergi kayıt yükümlülükleri
5. Kimlik sağlayıcı (IdP) seçimi ve MFA yapılandırması
6. Ortam değişkeni `HSC_LIVE_ARMED=YES`, `config.yaml` onayı ve arayüz onayı
7. Broker test ortamında kabul testleri ve gözetimli küçük canlı pilot

**Yapılmayacaklar:** chat'te paylaşılan e-posta/şifre kullanılmayacak; gizli bilgiler
asla depoya konulmayacak; siz açıkça onaylamadan ve yasal önkoşullar tamamlanmadan
`live_trading.enabled` açılmayacak.

> Bu doküman bir taahhüt değildir. Mevcut uygulama **paper-only** ve
> **GERÇEK PARA İÇİN ONAYLANMADI** durumunu korumaktadır.
