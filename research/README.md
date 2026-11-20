# Araştırma ve doğrulama betikleri

Bu klasör, gerçek Binance verisiyle yapılan araştırmaların **orijinal betiklerini**
içerir. Hiçbir betik API anahtarı veya şifre içermez; anahtarlar çalışma zamanında
`ui.secrets_access` üzerinden yerel `secrets.toml`'dan okunur.

## Kategoriler

**Strateji araştırması**
- `backtest_tune.py`, `backtest_broad.py` — 1dk/5dk momentum ve ortalama dönüşü (228 kombinasyon)
- `research_v2.py`, `research_v2b.py` — 15dk/1s/4s, iç/dış örneklem (83 kombinasyon)
- `research_daily.py`, `validate_daily.py` — **günlük EMA50 edge'inin bulunması ve doğrulanması**

**Piyasa / arbitraj analizi**
- `arb_scan.py`, `arb_scan2.py` — çapraz kur arbitrajı taraması
- `tls_probe.py`, `tr_probe.py`, `tr_min_order.py`, `tr_cheap_coins.py` — ağ/API/filtre keşfi
- `tr_scan.py`, `tr_live_check.py`, `tr_balance_dump.py`, `check_new_balance.py` — canlı sinyal/bakiye okuma

**Canlı operasyon kayıtları**
- `buy_form.py`, `sell_dust.py`, `close_position.py`, `do_real_trade.py`, `migrate_state.py`
- `run_scalper.py` — 30 dakikalık ilk canlı döngü

> Not: Şifre/anahtar karşılaştırma betikleri (`compare_keys.py`, `diff_key.py`,
> `diff_secret.py`, `oracle_probe.py`, `fix_secrets.py`) gizli değer içerdiği için
> **depoya alınmadı**.
