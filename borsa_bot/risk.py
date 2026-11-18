"""
Risk yonetimi: pozisyon boyutlandirma, stop-loss, take-profit hesaplamalari.
"""

from __future__ import annotations

import math


def position_size(
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
) -> float:
    """
    Risk-e dayali pozisyon miktari hesapla.

    Kullanilacak sermaye = capital * risk_pct
    Iskelet risk = abs(entry - stop)
    Miktar = kullanilacak sermaye / iskelet risk
    """
    if entry_price <= 0 or stop_price <= 0:
        return 0.0
    risk_amount = capital * risk_pct
    per_share_risk = abs(entry_price - stop_price)
    if per_share_risk <= 0:
        return 0.0
    qty = risk_amount / per_share_risk
    return math.floor(qty * 100) / 100  # 2 ondalik yuvarla


def fixed_fraction_size(
    capital: float,
    fraction: float,
    price: float,
) -> float:
    """
    Sabit oranli pozisyon boyutu (capital * fraction / price).
    """
    if price <= 0:
        return 0.0
    alloc = capital * fraction
    qty = alloc / price
    return math.floor(qty * 100) / 100


def stop_levels(
    entry_price: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    direction: str = "long",
) -> tuple[float, float]:
    """
    Stop-loss ve take-profit fiyatlarini dondurur.

    direction: 'long' veya 'short'
    """
    if direction == "long":
        sl = entry_price * (1 - stop_loss_pct)
        tp = entry_price * (1 + take_profit_pct)
    else:
        sl = entry_price * (1 + stop_loss_pct)
        tp = entry_price * (1 - take_profit_pct)
    return round(sl, 4), round(tp, 4)