"""
VOLATİLİTEYE GÖRE POZİSYON BOYUTU — ATR(14) / 30 günlük ortalama ATR.

  normal         (<= ort*1.20) -> %10
  yüksek         (>  ort*1.20) -> %7
  çok yüksek     (>  ort*1.50) -> %5

Bu SADECE tek işlem boyutunu etkiler. Günlük %10 limiti ve trailing DD %15 DEĞİŞMEZ.
"""

from __future__ import annotations

from typing import Any

from ui import market_regime, quant_lab

HIGH_MULT = 1.20
EXTREME_MULT = 1.50
PCT_NORMAL = 0.10
PCT_HIGH = 0.07
PCT_EXTREME = 0.05
BASE_DAYS = 30


def atr_state(symbol: str, frame: Any = None) -> dict[str, Any]:
    """Son ATR(14)'ü 30 günlük ortalama ATR ile karşılaştır."""
    f = frame if frame is not None else quant_lab.fetch(symbol, "1d", BASE_DAYS + 30)
    if f is None or len(f) < 20:
        return {"state": "Normal", "pct": PCT_NORMAL, "atr": 0.0,
                "avg": 0.0, "ratio": 1.0, "reason": "veri yok — normal boyut"}
    cur = market_regime._atr(f)
    # 30 günlük ortalama ATR: her gün için ATR hesapla (basit yaklaşım: 14'lük kayan)
    vals = []
    for i in range(max(14, len(f) - BASE_DAYS), len(f)):
        vals.append(market_regime._atr(f.iloc[:i + 1]))
    avg = float(sum(vals) / len(vals)) if vals else cur
    ratio = cur / avg if avg > 0 else 1.0
    if ratio > EXTREME_MULT:
        state, pct = "Çok Yüksek", PCT_EXTREME
        reason = f"ATR son {cur:.2f} > ortalama {avg:.2f} x1.5 — boyut %5'e düşürüldü"
    elif ratio > HIGH_MULT:
        state, pct = "Yüksek", PCT_HIGH
        reason = f"ATR son {cur:.2f} > ortalama {avg:.2f} x1.2 — boyut %7'ye düşürüldü"
    else:
        state, pct = "Normal", PCT_NORMAL
        reason = f"ATR {cur:.2f} ≈ ortalama {avg:.2f} — boyut %10"
    return {"state": state, "pct": pct, "atr": round(cur, 4),
            "avg": round(avg, 4), "ratio": round(ratio, 3), "reason": reason}


def sized_pct(symbol: str, balance: float, frame: Any = None) -> dict[str, Any]:
    """Volatiliteye göre ayarlanmış işlem tutarı."""
    st = atr_state(symbol, frame)
    amount = round(balance * st["pct"], 4)
    return {**st, "balance": balance, "amount": amount}
