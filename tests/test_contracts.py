"""Kontrat testleri: veri şeması ve gösterge çıktı sözleşmesi."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from borsa_bot.config import Config
from borsa_bot.data import NEEDED_COLUMNS
from borsa_bot.indicators import add_cross_flags, compute_indicators


ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden" / "THYAO_golden.csv"


def test_data_schema_contract() -> None:
    assert tuple(NEEDED_COLUMNS) == ("Open", "High", "Low", "Close", "Volume")


def test_golden_fixture_schema() -> None:
    frame = pd.read_csv(GOLDEN, index_col=0, parse_dates=True)
    assert list(frame.columns) == list(NEEDED_COLUMNS)
    assert len(frame) > 150
    assert frame["Close"].min() > 0


def test_indicator_columns_contract() -> None:
    cfg = Config()
    frame = pd.read_csv(GOLDEN, index_col=0, parse_dates=True)
    enriched = add_cross_flags(compute_indicators(frame, cfg.indicators))
    required = {
        "SMA_20", "SMA_50", "SMA_200", "EMA_12", "EMA_26", "RSI",
        "MACD", "MACD_Signal", "MACD_Hist", "BB_Upper", "BB_Lower",
        "Stoch_K", "OBV", "ATR", "VWAP", "Trend_Bullish", "OBV_Rising",
    }
    missing = required - set(enriched.columns)
    assert not missing, f"Eksik gösterge kolonları: {missing}"


def test_signal_details_contract() -> None:
    from borsa_bot.signals import generate_signal

    cfg = Config()
    frame = pd.read_csv(GOLDEN, index_col=0, parse_dates=True)
    enriched = add_cross_flags(compute_indicators(frame, cfg.indicators))
    info = generate_signal(enriched, {
        "signal_weights": cfg.signal_weights,
        "signal_thresholds": cfg.signal_thresholds,
    })
    for key in ("score", "signal", "details", "last_close", "rsi"):
        assert key in info, key
