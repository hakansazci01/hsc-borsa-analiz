# localhost.co/tools değerlendirmesi ve entegrasyon planı

Kaynak: https://localhost.co/tools/ (developer tool catalog, 10 kategori / ~50 araç)

## 1. Site ne sunuyor?

| Kategori | Araçlar | Bizim sistemle ilgi |
|---|---|---|
| code | Markdown viewer, JS/CSS/SQL/HTML formatter, Markdown→HTML, Regex tester | **Düşük** — arayüzümüz Streamlit, kod editörü değil |
| data | JSON/YAML validator, formatter, fixer, JSON↔YAML, JSON↔CSV, CSV↔JSON, JSON→Schema, JSON→Table, XML araçları | **Yüksek** — yapılandırma ve veri dosyalarımızın tamamı bu formatlarda |
| devops | Gitignore generator, cURL→code, **Cron expression builder** | **Orta** — cron, otomatik tarama/uyarı için faydalı |
| encoding | Base64, URL encode/decode, HTML entity | **Düşük** |
| generators | UUID, **Password generator**, QR, Lorem ipsum | **Orta** — güçlü şifre üretimi kayıt akışında işe yarar |
| security | JWT decoder, bcrypt generator, hash generator | **Düşük** — biz PBKDF2 kullanıyoruz, JWT/bcrypt kullanmıyoruz |
| seo / text / web / time | Keyword, case converter, word counter, color converter, query parser, unix timestamp | **Düşük** — trading paneli için gürültü |

Sonuç: Kataloğun tamamını almak gereksiz olur; sistemimiz bir **developer playground** değil, **karar destek paneli**. Sadece 3-4 araç gerçek değer katıyor.

---

## 2. Kesinlikle eklenmesi gereken: "Yapılandırma Doktoru" (Config Doctor)

**Neden şart?**
Sistem şu dosyalara bağımlı: `config.yaml`, `.streamlit/secrets.toml`, `user_settings.json`, `users/<kullanici>/settings.json`, `users/<kullanici>/portfolio.json`, `decisions.jsonl`, `results/signals.json`.

Bu dosyalardan biri bozulduğunda uygulama **sessizce yanlış çalışıyor** veya hiç açılmıyor. Gerçek bir örnek yaşandı: RSI eşikleri `indicators` altındaydı ama sinyal motoru `signal` altında arıyordu; sistem 30/70 varsayılanını kullanıp hiç uyarı vermiyordu. Denetim turunda bulunmasaydı fark edilmeyecekti.

**Ne yapacak?**
- `config.yaml` → YAML syntax + zorunlu anahtarlar + tip kontrolü (sayı mı, liste mi)
- `secrets.toml` → TOML syntax + hangi servisin hangi anahtarının eksik olduğu (değer göstermeden)
- kullanıcı JSON'ları → JSON syntax + şema kontrolü (jsonschema ile)
- `results/signals.json`, `decisions.jsonl` → bozuk satır tespiti
- Çıktı: **yeşil/sarı/kırmızı** durum kartları + "hangi dosyanın hangi satırı" bilgisi + düzeltme önerisi

**Nereden geliyor?** localhost.co → *YAML Validator + JSON Validator + JSON to JSON Schema* bileşimi.

**Gereçler:** `pyyaml` (var), `jsonschema` (var), `tomllib` (Python 3.12 ile geliyor). Ek kurulum yok.

---

## 3. İkinci öncelik: Güçlü şifre üretici (kayıt ekranına entegre)

**Neden?** Kullanıcı hesapları eklendi; kullanıcılar kısa/tekrarlanan şifre seçebiliyor. Kayıt formunda "Güçlü şifre öner" düğmesi + güç göstergesi (uzunluk, büyük/küçük harf, rakam, sembol) eklenmeli.

**Nereden geliyor?** localhost.co → *Password Generator*.

**Gereçler:** Python `secrets` (var). Ek kurulum yok.

---

## 4. Üçüncü öncelik: Zamanlayıcı / Cron yardımcıları

**Neden?** "Anlık takip" için 60 sn fragment yenileme var; bunun ötesinde **seans saatlerinde otomatik tarama** ve KAP/Telegram uyarıları için cron ifadeleri gerekebilir. Kullanıcı "her gün 10:00'da tara" diyebilmeli.

**Nereden geliyor?** localhost.co → *Cron Expression Builder*.

**Gereçler:** `croniter` (yok, `pip install croniter` gerekir) veya basit dakika/saat seçicileriyle bağımlılıksız çözüm. Streamlit tarafında gerçek zamanlayıcı için `st.Fragment(run_every=...)` veya sunucu tarafı bir worker gerekir; tek makinede fragment yeterli.

---

## 5. Dördüncü öncelik: Veri dönüştürücüler (CSV ↔ JSON / JSON → Tablo)

**Neden?** Kullanıcı kendi geçmiş işlemlerini CSV'den getirip kurgusal portföye aktarabilir; `results/signals.csv` ve `signals.json` zaten üretiliyor. JSON→Tablo görünümü denetimde işe yarar.

**Nereden geliyor?** localhost.co → *CSV to JSON, JSON to CSV, JSON to Table*.

**Gereçler:** `pandas` + `json` (var). Ek kurulum yok.

---

## 6. Eklenmemesi gerekenler ve gerekçe

- Markdown/CSS/SQL/HTML formatter, regex tester → uygulama kod editörü değil
- JWT decoder, bcrypt generator, hash generator → auth PBKDF2 ile kendi içimizde; kullanıcıya açık bir araç değil
- Lorem ipsum, QR, slug, keyword density, color converter, unix timestamp → trading karar süreciyle ilgisiz
- XML araçları → sistemde XML veri yok

Bunları eklemek arayüzü şişirir, bakım maliyetini artırır ve kullanıcıyı asıl işinden (sinyal analizi) uzaklaştırır.

---

## 7. Uygulama planı (fazlar)

| Faz | İş | Süre | Risk | Öncelik |
|---|---|---|---|---|
| 1 | `ui/config_doctor.py` + "Denetim" sayfasında **Yapılandırma Doktoru** kartı | Tamamlandı | Düşük | **Şart** |
| 2 | Kayıt formuna güçlü şifre önerisi + güç göstergesi | Tamamlandı | Düşük | Yüksek |
| 3 | Otomatik tarama zamanlayıcısı (cron yardımcı + basit UI) | Tamamlandı | Orta | Orta |
| 4 | CSV/JSON içe/dışa aktarma paneli (Hesabım sayfası) | Tamamlandı | Düşük | Orta |

**Önerilen sıra:** Faz 1 → Faz 2 → (kullanıcı talep ederse) Faz 3 → Faz 4.

---

## 8. Başarı kriterleri

- Config Doctor, kasıtlı bozulan bir `config.yaml` / JSON dosyasını **doğru satır ve alanla** yakalayabilmeli
- Şifre önericisi ürettiği şifre mevcut `auth.register` doğrulamasından geçmeli
- Hiçbir yeni araç mevcut sayfaların çalışmasını bozmamalı (AppTest + agent API ile 16 sayfa doğrulanmalı)
- Eklenen tüm dosyalar `.gitignore` kapsamında olmalı, gizli değerler arayüzde gösterilmemeli
