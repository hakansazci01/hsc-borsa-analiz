"""
Tam calisma testi: Tüm moduller, tüm semboller, tüm raporlar.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from borsa_bot.config import Config
from borsa_bot.scanner import Scanner


def main():
    cfg = Config()
    symbols = cfg.symbols

    print("=" * 70)
    print(" HSC BORSA ANALİZ - TAM CALISMA TESTI")
    print("=" * 70)
    print()
    print("[AYARLAR]")
    print(f"  Semboller      : {symbols}")
    print(f"  Veri periyodu  : {cfg.data.get('period')}")
    print(f"  Veri araligi   : {cfg.data.get('interval')}")
    print(f"  RSI asiri dusuk: {cfg.signal_thresholds.get('rsi_oversold')}")
    print(f"  RSI asiri yuksek: {cfg.signal_thresholds.get('rsi_overbought')}")
    print(f"  Strong Buy esigi: {cfg.signal_thresholds.get('strong_buy')}")
    print(f"  Buy esigi       : {cfg.signal_thresholds.get('buy')}")
    print(f"  Stop Loss       : %{cfg.risk.get('stop_loss_pct') * 100}")
    print(f"  Take Profit     : %{cfg.risk.get('take_profit_pct') * 100}")
    print(f"  Komisyon        : %{cfg.risk.get('commission_pct') * 100}")
    print(f"  Pozisyon boyutu : %{cfg.risk.get('position_size_pct') * 100}")
    print(f"  Baslangic       : {cfg.risk.get('initial_capital')}")
    print()

    scanner = Scanner(cfg)
    print("[TARAMA] Tum semboller analiz ediliyor...")
    results = scanner.scan_all()
    scanner.print_summary(results)

    print()
    print("[SONUC]")
    print(f"  Toplam analiz edilen hisse: {len(results)}")
    buys = [r for r in results if r["signal"] in ("STRONG_BUY", "BUY")]
    sells = [r for r in results if r["signal"] in ("STRONG_SELL", "SELL")]
    neutrals = [r for r in results if r["signal"] == "NEUTRAL"]
    print(f"  AL sinyali  : {len(buys)} hisse -> {[b['symbol'] for b in buys]}")
    print(f"  SAT sinyali : {len(sells)} hisse -> {[s['symbol'] for s in sells]}")
    print(f"  NÖTR      : {len(neutrals)} hisse -> {[n['symbol'] for n in neutrals]}")
    print()

    print("[DOSYALAR]")
    charts = list(Path("charts").glob("*.png")) if Path("charts").exists() else []
    results_files = list(Path("results").glob("*")) if Path("results").exists() else []
    print(f"  Grafik dosyalari ({len(charts)}):")
    for c in sorted(charts):
        print(f"    - {c.name}")
    print(f"  Rapor dosyalari ({len(results_files)}):")
    for f in sorted(results_files):
        print(f"    - {f.name}")
    print()
    print("=" * 70)
    print(" TAM CALISMA BASARILI")
    print("=" * 70)


if __name__ == "__main__":
    main()