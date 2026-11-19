# Anahtar döndürme ve sır yönetimi politikası

Bu proje yerel, paper-only bir karar destek uygulamasıdır. Yine de API
anahtarları sızdığında kötüye kullanılabilir. Aşağıdaki kurallar geçerlidir.

## Saklama

- Gerçek anahtarlar **yalnızca** `.streamlit/secrets.toml` dosyasındadır ve
  `.gitignore` ile depo dışındadır. Depoda yalnızca `secrets.toml.example` bulunur.
- Anahtar değerleri arayüzde gösterilmez, günlüğe yazılmaz, denetim kaydına
  eklenmez. `ui/secret_policy.py` yalnızca **döndürme tarihlerini** tutar.
- Bu dosya OneDrive / bulut senkronizasyonu altındaysa, senkronizasyon kapatılmalı
  veya proje senkronize olmayan bir dizine taşınmalıdır.

## Döndürme sıklığı

| Servis | Süre | Not |
|---|---|---|
| Gemini API key | 90 gün | Google AI Studio'dan yenisi üretilir |
| Finnhub API key | 90 gün | Dashboard → API Key |
| Alpaca paper key/secret | 90 gün | Paper ortamı bile olsa döndürülür |
| Twilio auth token | 90 gün | Konsoldan rotate |
| SMTP uygulama şifresi | 90 gün | Google App Password |
| Inngest signing/event key | 90 gün | Environment ayarları |
| Telegram bot token | 90 gün | @BotFather `/revoke` |
| ntfy konusu | 180 gün | Tahmin edilemez konu adı yenilenir |

Şüpheli sızıntı durumunda **beklemeden** döndürün.

## Acil durum

1. Sağlayıcının panelinden anahtarı iptal et / revoke et.
2. Yeni anahtar üret ve `secrets.toml` içine yaz.
3. Uygulamayı yeniden başlat, "Denetim → Hızlı bağlantı testleri" ile doğrula.
4. `Denetim → Anahtar döndürme takibi` ekranından yeni tarihi kaydet.
5. OneDrive gibi bir senkronizasyon varsa sürüm geçmişini de gözden geçir.

## Denetim

`ui/secret_policy.py` 90 günü aşan anahtarları kırmızı, 14 gün içinde
dolacakları turuncu gösterir. "Kayıt yok" durumu **temiz** anlamına gelmez.
