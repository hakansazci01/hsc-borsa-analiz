"""RİSK/GETİRİ KAPISI — stop mesafesi TP'ye göre matematiksel olarak vive olmalı.

Walk-forward kanıtı (2026-11-23):
  %0.6 TP - %0.25 komisyon = %0.35 net kazanç
  %5 stop + %0.25 komisyon = %5.25 net zarar
  %75 win rate ile expectancy = 0.75*0.35 - 0.25*5.25 = -1.05%  → KAYBETTİRİR

Denklem: p*net_win > (1-p)*net_loss  →  stop < p/(1-p) * net_win
Öneri: mikro stop = %1.0 (felaket stop %5/%7 ayrı ve korunur)
"""

from __future__ import annotations

from typing import Any

TP_PCT = 1.50   # mikro TP %1.5 (kullanıcı onayı)
FEE_PCT = 0.25
MICRO_STOP_PCT = 1.00
MIN_WIN_RATE = 0.60


def net_win_pct(tp: float = TP_PCT, fee: float = FEE_PCT) -> float:
    return float(tp) - float(fee)


def max_stop_pct(win_rate: float, tp: float = TP_PCT,
                 fee: float = FEE_PCT) -> float:
    """p*net_win > (1-p)*(stop + fee) → stop < p*net_win/(1-p) - fee."""
    p = min(0.99, max(0.01, float(win_rate)))
    raw = p / (1 - p) * net_win_pct(tp, fee) - float(fee)
    return round(max(0.0, raw), 4)


def check(stop_pct: float, win_rate: float = MIN_WIN_RATE,
          tp: float = TP_PCT, fee: float = FEE_PCT) -> dict[str, Any]:
    cap = max_stop_pct(win_rate, tp, fee)
    ok = float(stop_pct) <= cap
    return {"ok": ok, "stop_pct": float(stop_pct), "max_stop_pct": cap,
            "expectancy_pct": round(win_rate * net_win_pct(tp, fee)
                                    - (1 - win_rate) * (float(stop_pct) + fee), 4),
            "msg": (f"R/R: stop %{float(stop_pct):.2f} {'≤' if ok else '>'} "
                    f"geçerli tavan %{cap:.2f} (TP %{tp:.2f}, komisyon %{fee:.2f}, "
                    f"win %{win_rate*100:.0f}) — "
                    f"{'GEÇERLİ' if ok else 'KÂR BEKLENTİSİ NEGATİF, STOP DARALT'}")}
