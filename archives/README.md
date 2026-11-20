# Çalışma verisi arşivi

Otonom sistemin gerçek çalışma kayıtlarının **gizli olmayan** kopyası. Canlı sistem
bu dosyaları `users/` altında tutar; burada yalnızca GitHub için okunabilir bir
anlık görüntü saklanır.

| Dosya | İçerik |
|---|---|
| `tr_autonomous.log` | Saatlik otonom analizler, kararlar ve nedenler |
| `tr_autonomous_heartbeat.json` | Son nabız, PID, son analiz zamanı |
| `tr_autonomous_state.json` | Öngörüler ve gerçek fiyatla self-test sonuçları |
| `tr_decision_journal.jsonl` | İşlem defteri: ne yapıldı / neden yapılmadı |
| `tr_scalper.log` | 15 saniyelik tarama turları, emir denemeleri |
| `tr_scalper_snapshots.jsonl` | Gerçek fiyat/kâr anlık görüntüleri |
| `tr_scalper_state.json` | Pozisyon ve gerçekleşen K/Z durumu |

**Depoya alınmayanlar:** `users/accounts.json` (şifre hash'leri), `*_armed.json`
(yerel kilit durumları), `.streamlit/secrets.toml` (API anahtarları), kilit dosyaları.
