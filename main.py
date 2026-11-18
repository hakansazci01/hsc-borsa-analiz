"""
Borsa Al/Sat Sinyal Botu - Ana giris noktasi.

Kullanim:
    python main.py scan
    python main.py backtest --symbol THYAO.IS
    python main.py chart --symbol AAPL
"""

from __future__ import annotations

import argparse
import sys

from borsa_bot.config import Config
from borsa_bot.scanner import Scanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Borsa Al/Sat Sinyal Botu")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Tum sembolleri tara ve sinyal uret")
    p_scan.add_argument("--symbols", nargs="*", help="Override sembol listesi")

    p_bt = sub.add_parser("backtest", help="Tek bir sembol icin geriye donuk test calistir")
    p_bt.add_argument("--symbol", required=True, help="Hisse senedi sembolu")

    p_chart = sub.add_parser("chart", help="Tek bir simbol icin grafik olustur")
    p_chart.add_argument("--symbol", required=True, help="Hisse senedi sembolu")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    cfg = Config()

    if args.command == "scan":
        symbols = args.symbols or cfg.symbols
        if not symbols:
            print("config.yaml'da sembol tanimli degil.")
            return 1
        # Override symbols dinamik olarak
        cfg._raw["symbols"] = symbols
        scanner = Scanner(cfg)
        print(f"Analiz baslatiliyor: {len(symbols)} hisse senedi...\n")
        results = scanner.scan_all()
        scanner.print_summary(results)
        return 0

    if args.command == "backtest":
        from borsa_bot.data import fetch
        from borsa_bot.indicators import add_cross_flags, compute_indicators
        from borsa_bot.backtest import run_backtest

        symbol = args.symbol
        df = fetch(symbol, cfg)
        df = compute_indicators(df, cfg.indicators)
        df = add_cross_flags(df)

        bt_cfg = {
            "backtest": cfg.backtest,
            "risk": cfg.risk,
            "signal_thresholds": cfg.signal_thresholds,
            "signal_weights": cfg.signal_weights,
            "guards": cfg.get("guards", default={}),
        }
        bt = run_backtest(df, bt_cfg)

        print(f"\n{symbol} - Geriye Donuk Test Sonuclari")
        print("-" * 50)
        print(f"Baslangic Sermayesi : {bt.get('initial_capital')}")
        print(f"Final Sermaye       : {bt.get('final_equity')}")
        print(f"Toplam Getiri       : {bt.get('total_return_pct')}%")
        print(f"Yilliklesik Getiri (CAGR) : {bt.get('cagr_pct')}%")
        print(f"Kazanma Oran        : {bt.get('win_rate_pct')}%")
        print(f"Islem Sayisi        : {bt.get('total_trades')}")
        print(f"Kazanici Islem      : {bt.get('winning_trades')}")
        print(f"Maksimum Cekilme    : {bt.get('max_drawdown_pct')}%")
        return 0

    if args.command == "chart":
        from borsa_bot.data import fetch
        from borsa_bot.indicators import add_cross_flags, compute_indicators
        from borsa_bot.signals import generate_signal
        from borsa_bot.visualize import plot_symbol

        symbol = args.symbol
        df = fetch(symbol, cfg)
        df = compute_indicators(df, cfg.indicators)
        df = add_cross_flags(df)

        signal_info = generate_signal(df, {
            "signal_weights": cfg.signal_weights,
            "guards": cfg.get("guards", default={}),
            "signal_thresholds": cfg.signal_thresholds,
        })
        signal_info["symbol"] = symbol

        path = plot_symbol(df, symbol, signal_info, cfg.visualize)
        if path:
            print(f"Grafik kaydedildi: {path}")
        else:
            print("Grafik kaydi kapali (config.yaml'de visualize.save_charts = false).")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())