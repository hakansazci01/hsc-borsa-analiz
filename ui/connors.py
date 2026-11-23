"""CONNORS RSI(2) — panik alımı, 15 dk timeframe.

Trend: Fiyat > SMA(200) ise SADECE LONG.
Giriş: RSI(2) < 10 kapanışta al.
Çıkış: Fiyat SMA(5) üstüne çıkınca sat.
Fırsat motoruna ek sinyal olarak bağlanır.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

RSI_PERIOD = 2
ENTRY_RSI = 10.0


def rsi2(closes: list[float], period: int = RSI_PERIOD) -> float:
    """Wilder RSI(2)."""
    s = pd.Series([float(x) for x in closes], dtype="float64")
    if len(s) < period + 1:
        return 50.0
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / period, adjust=False).mean()
    if float(loss.iloc[-1]) == 0:
        return 100.0
    rs = float(gain.iloc[-1]) / float(loss.iloc[-1])
    return round(100.0 - 100.0 / (1.0 + rs), 3)


def sma(closes: list[float], period: int) -> float:
    s = pd.Series([float(x) for x in closes], dtype="float64")
    return float(s.rolling(period).mean().iloc[-1]) if len(s) >= period else 0.0


def entry(closes: list[float]) -> tuple[bool, str]:
    """Fiyat > SMA200 ve RSI(2) < 10 → LONG adayı."""
    price = float(closes[-1]) if closes else 0.0
    s200 = sma(closes, 200)
    r2 = rsi2(closes)
    ok = s200 > 0 and price > s200 and r2 < ENTRY_RSI
    return ok, (f"Connors RSI(2)={r2:.1f} < {ENTRY_RSI:.0f} · "
                f"fiyat {price:.4f} {'>' if price > s200 else '<'} SMA200 {s200:.4f}")


def exit_signal(price: float, closes: list[float]) -> tuple[bool, str]:
    """Fiyat SMA5 üstüne çıkınca sat."""
    s5 = sma(closes, 5)
    ok = s5 > 0 and float(price) > s5
    return ok, f"Connors çıkış: fiyat {float(price):.4f} {'>' if ok else '<'} SMA5 {s5:.4f}"
