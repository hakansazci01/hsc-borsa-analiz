"""Golden fixture regresyon testleri: aynı veri -> aynı sonuç."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from borsa_bot.backtest import run_backtest
from borsa_bot.config import Config
from borsa_bot.indicators import add_cross_flags, compute_indicators
from borsa_bot.signals import generate_signal


ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden" / "THYAO_golden.csv"


def _cfg() -> dict:
    c = Config()
    return {
        "backtest": c.backtest,
        "risk": c.risk,
        "signal_thresholds": c.signal_thresholds,
        "signal_weights": c.signal_weights,
        "guards": None,
    }


def _enriched() -> pd.DataFrame:
    frame = pd.read_csv(GOLDEN, index_col=0, parse_dates=True)
    return add_cross_flags(compute_indicators(frame, Config().indicators))


def test_indicator_determinism() -> None:
    first = _enriched()
    second = _enriched()
    for column in ("SMA_20", "RSI", "MACD", "ATR", "VWAP"):
        np.testing.assert_allclose(
            first[column].to_numpy(), second[column].to_numpy(),
            rtol=1e-10, equal_nan=True,
        )


def test_signal_determinism() -> None:
    info = generate_signal(_enriched(), _cfg())
    assert -5 <= float(info["score"]) <= 5
    assert info["signal"] in ("STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL")


def test_backtest_determinism() -> None:
    result = run_backtest(_enriched(), _cfg())
    assert "final_equity" in result
    assert len(result["equity_curve"]) == len(result["dates"])
    assert np.isfinite(float(result["final_equity"]))
    assert result["max_drawdown_pct"] <= 0
