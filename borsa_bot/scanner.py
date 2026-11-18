"""
Tarama katmani: tum sembolleri analiz eder, siralar ve sonuclari dondurur.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from borsa_bot.alerts import alert, save_results
from borsa_bot.backtest import run_backtest
from borsa_bot.config import Config
from borsa_bot.data import fetch
from borsa_bot.indicators import add_cross_flags, compute_indicators
from borsa_bot.signals import generate_signal
from borsa_bot.visualize import plot_symbol


class Scanner:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def scan_symbol(self, symbol: str) -> dict[str, Any] | None:
        try:
            df = fetch(symbol, self.cfg)
            ind_cfg = self.cfg.indicators
            df = compute_indicators(df, ind_cfg)
            df = add_cross_flags(df)

            signal_info = generate_signal(df, {
                "signal_weights": self.cfg.signal_weights,
                "signal_thresholds": self.cfg.signal_thresholds,
            })
            signal_info["symbol"] = symbol

            chart_path = plot_symbol(df, symbol, signal_info, self.cfg.visualize)
            if chart_path:
                signal_info["chart"] = chart_path

            bt = run_backtest(df, {
                "backtest": self.cfg.backtest,
                "risk": self.cfg.risk,
                "signal_thresholds": self.cfg.signal_thresholds,
                "signal_weights": self.cfg.signal_weights,
                "guards": self.cfg.get("guards", default={}),
            })
            signal_info["backtest"] = bt

            alert(symbol, signal_info, {
                "alerts": self.cfg.alerts,
                "telegram_token": self.cfg.telegram_token,
                "telegram_chat_id": self.cfg.telegram_chat_id,
            })

            return signal_info

        except Exception as exc:
            print(f"\n[HATA] {symbol} analiz edilirken: {exc}")
            return None

    def scan_all(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for symbol in self.cfg.symbols:
            res = self.scan_symbol(symbol)
            if res:
                results.append(res)
        save_results(results, {
            "alerts": self.cfg.alerts,
        })
        return results

    def print_summary(self, results: list[dict[str, Any]]) -> None:
        print("\n" + "=" * 120)
        print(
            f"{'HISSE':<12} {'SINYAL':<14} {'PUAN':<6} {'FIYAT':<12} "
            f"{'RSI':<7} {'GETIRI(%)':<12} {'WIN%':<8} {'MDD(%)':<8} {'ISLEM':<7}"
        )
        print("-" * 120)
        for r in results:
            bt = r.get("backtest", {})
            print(
                f"{r['symbol']:<12} {r['signal']:<14} {r['score']:<6} "
                f"{r['last_close']:<12} {r['rsi']:<7} "
                f"{bt.get('total_return_pct', 0):<12} "
                f"{bt.get('win_rate_pct', 0):<8} "
                f"{bt.get('max_drawdown_pct', 0):<8} "
                f"{bt.get('total_trades', 0):<7}"
            )
        print("=" * 120 + "\n")

        buys = [r for r in results if r["signal"] in ("STRONG_BUY", "BUY")]
        if buys:
            best = max(buys, key=lambda r: r["score"])
            print(f"ONERILEN AL: {best['symbol']} (Puan: {best['score']}, Sinyal: {best['signal']})")
        else:
            print("Guncel olarak guclu AL sinyali veren hisse yok.")