# Bağımsız denetim promptu

Aşağıdaki metni olduğu gibi kopyalayıp başka bir AI uygulamasına gönderin.

---

Senden bir alım-satım botunu **bağımsız olarak denetlemeni** istiyorum. Tahmin veya
"her şey tamam" deme — **her madde için VAR / YOK de ve dosya adı + satır numarası
ver**. Yoksa "YOK, KRİTİK EKSİK" yaz. Kaynak kodun içinden kanıt göster.

## Ortam

- Proje: `C:\Users\hakan\OneDrive\Desktop\al sat boto`
- Repo: `https://github.com/hakansazci01/hsc-borsa-analiz` (branch `main`, son commit `9bd1acd53a4bc0aa47bbe75d29546c5da2c938df`)
- Borsa: **Binance TR** (global Binance DEĞİL), gerçek para, bakiye ~₺506
- Framework: Streamlit + Python 3.12, sanal ortam `.venv`
- Test komutları:
  - `.venv\Scripts\python.exe tests\run_all.py`
  - `.venv\Scripts\python.exe -m pytest tests\test_app_flow.py -q`

## GÜVENLİK (koddan kanıtla)

1. API key / secret kodun içinde açık yazılı mı, yoksa `.streamlit/secrets.toml`
   veya ortam değişkeninde mi? Hangi dosya/satır?
2. Kodda `withdraw`, `transfer`, para çekme emri var mı? `git grep -i withdraw` sonucu ne?
3. API anahtarını Telegram/ntfy/başka bir URL'ye gönderen kod var mı?
4. Bot hangi BASE URL'e bağlanıyor? Global Binance'e bağlanma riski var mı?

## STRATEJİ

5. `ui/tr_scalper.py::signal()` tam olarak neyi çağırıyor? Satır numarasıyla göster.
6. Canlı strateji backtest'te kazanan **günlük EMA50 pullback** mi, yoksa eski
   1-dakikalık RSI7/EMA9/20 scalper kodu kaldı mı? Eski kod var mı?
7. Alım ve satım kurallarını matematiksel olarak yaz (hangi satır?).
8. Martingale yapıyor mu? Zarar edince işlem boyutu 2 katına çıkıyor mu?

## RİSK / SERMAYE (₺506'ya göre)

9. Tek işlem boyutu nasıl hesaplanıyor? Sabit mi, dinamik mi? 506 TL'de kaç TL,
   1000 TL'de kaç TL? Hangi satır?
10. Günlük zarar limiti nasıl hesaplanıyor? 506 TL'de kaç TL? Hangi satır?
11. Drawdown kilidi: trailing mi? Yüzde kaç? Referans bakiye ne? Hangi satır?
12. Kâr koruma: toplam kâr +50 TL'yi geçince stop giriş fiyatının üstüne çekiliyor mu?
13. Ani çöküş koruması: 5 dakikada %5 düşüşte ne oluyor, kaç dakika bekliyor?
14. Aynı anda en fazla kaç pozisyon açılıyor?

## KİLİTLER

15. `config.yaml` `binance_tr.enabled` şu an true mu? Hangi satır?
16. `confirmation_phrase` = `HSC-BINANCE-TR-ARM` doğrulanmadan emir atılabilir mi?
    `config_gate()` hangi satırda RED döndürüyor?
17. STOP_FILE varken emir atılabilir mi? Hangi satır?
18. Bu 3 kilidin testi var mı? Test adı ve sonucu ne?

## KAYIT / İZLEME

19. `trades.csv` var mı? Sütun isimlerini yaz. Kaç satır? Hangi satırda yazılıyor?
20. `tr_monitor.summary()` kaç işlem ve net K/Z döndürüyor? Geçmiş işlem Kayıp mı?
21. Her alım/satımda ntfy bildirimi gidiyor mu? Mesajda hangi alanlar var?
22. Saatlik "BOT YAŞIYOR" sinyali var mı? 2 saat gelmezse ne anlama geliyor?
23. Fren devreye girerse bildirim gidiyor mu?

## OTONOM ÇALIŞMA

24. Bilgisayar yeniden başlayınca bot otomatik başlıyor mu? Startup klasöründeki
    dosyanın adı ve içeriği ne? Windows görevleri hangi isimler, Last Result kaç?
25. Watchdog motor/scheduler/uygulama durmuşsa gerçekten yeniden başlatıyor mu?
    `watchdog_once()` hangi satırda, neyi kontrol ediyor?
26. `app_pages/bot_durumu.py` ışığı sadece config'e mi bakıyor, yoksa gerçek
    süreçlere mi? Üç süreçten biri durmuşsa ışık kırmızıya dönüyor mu?
27. Saatlik sağlık, gece 00:00 yedekleme (30 gün), Pazar strateji değerlendirmesi
    kodda var mı? Hangi dosya/satır?

## TEST VE SONUÇ

28. Testleri sen çalıştır. Kaç test, kaç geçti?
29. Son commit numarası ne? Git temiz mi?
30. Uygulama ayakta mı? `Invoke-WebRequest http://127.0.0.1:8501/_stcore/health`

## SONUÇ FORMATI

- Madde madde VAR / YOK + `dosya:satır` kanıtı
- En sonunda: **"₺506 gerçek para ile başlatmak güvenli mi? EVET / HAYIR + gerekçe"**
- Eksik varsa "gerçek parayla başlatmadan önce mutlaka eklenmesi gerekenler" listesi

## ÖNEMLİ

- API secret / şifre / anahtar DEĞERLERİNİ okuma, yazma veya rapora koyma.
- Sadece kodun mantığını ve satırları denetle.
- Hiçbir emir gönderme, para çekme, transfer yapma.
- Sanal/paper/dry-run modu ekleme; bu bot gerçek Binance TR ile çalışıyor.
