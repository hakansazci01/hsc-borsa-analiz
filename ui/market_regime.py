"""
Piyasa rejimi ve gelişmiş filtreler — gerçek Binance TR verisinden hesaplanır.

- REJİM: ADX(14) + EMA50 → AYI / BOĞA / YATAY
- ATR(14) bazlı stop: 1.5 * ATR
- GRID: yatay piyasada 5 parça, %1 adımlar
- ARDIŞIK ZARAR: 3 zarar → 24 saat dur
- MULTI-TIMEFRAME: günlük + 4s EMA50 onayı

Limitler DEĞİŞMEZ: dinamik %10, günlük %10, trailing DD %15, kâr kilidi +50.
"""

from __future__ import annotations

import json
import time
from typing import Any

from ui import quant_lab


ADX_PERIOD = 14
ATR_PERIOD = 14
ATR_MULT = 1.5
TREND_ADX = 25.0
RANGE_PCT = 0.05       # son 7 günde %5 içinde -> yatay
RANGE_DAYS = 7
GRID_PARTS = 5
GRID_STEP = 0.01       # %1
LOSS_STREAK_LIMIT = 3
LOSS_COOLDOWN_SEC = 86400
MTF_TF = "4h"


def _atr(frame, period: int = ATR_PERIOD) -> float:
    if frame is None or len(frame) < period + 1:
        return 0.0
    pc = frame["Close"].shift(1)
    tr = (frame["High"] - frame["Low"]).combine((frame["High"] - pc).abs(), max)
    tr = tr.combine((frame["Low"] - pc).abs(), max)
    return float(tr.tail(period).mean())


def _adx(frame, period: int = ADX_PERIOD) -> float:
    """Wilder ADX (14) — trend gücü 0-100."""
    if frame is None or len(frame) < period * 2:
        return 0.0
    h, l, c = frame["High"], frame["Low"], frame["Close"]
    up = h.diff()
    dn = -l.diff()
    plus = up.where((up > dn) & (up > 0), 0.0)
    minus = dn.where((dn > up) & (dn > 0), 0.0)
    tr = (h - l).combine((h - c.shift(1)).abs(), max).combine((l - c.shift(1)).abs(), max)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    pdi = 100 * plus.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, 1)
    mdi = 100 * minus.ewm(alpha=1 / period, adjust=False).mean() / atr.replace(0, 1)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, 1)
    return float(dx.ewm(alpha=1 / period, adjust=False).mean().iloc[-1])


def daily_data(symbol: str) -> Any:
    return quant_lab.fetch(symbol, "1d", 200)


def regime(symbol: str) -> dict[str, Any]:
    """ADX + EMA50 + 7 gün aralığı ile AYI / BOĞA / YATAY."""
    f = daily_data(symbol)
    if f is None or len(f) < 60:
        return {"name": "YATAY", "bull": False, "bear": False, "range": True,
                "reason": "veri yok — güvenli yatay"}
    c = f["Close"]
    ma = quant_lab.ema(c, 50)
    px, ema = float(c.iloc[-1]), float(ma.iloc[-1])
    adx = _adx(f)
    last7 = c.tail(RANGE_DAYS)
    spread = (float(last7.max()) - float(last7.min())) / float(last7.min()) if float(last7.min()) > 0 else 0
    if adx < TREND_ADX and spread <= RANGE_PCT:
        name, bull, bear, rng = "YATAY", False, False, True
        reason = f"ADX {adx:.1f}<{TREND_ADX:.0f} ve 7g aralık %{spread*100:.1f}≤%{RANGE_PCT*100:.0f}"
    elif px > ema:
        name, bull, bear, rng = "BOĞA", True, False, False
        reason = f"fiyat {px:.4f} > EMA50 {ema:.4f}, ADX {adx:.1f}"
    else:
        name, bull, bear, rng = "AYI", False, True, False
        reason = f"fiyat {px:.4f} < EMA50 {ema:.4f}, ADX {adx:.1f}"
    return {"name": name, "bull": bull, "bear": bear, "range": rng,
            "adx": round(adx, 2), "spread_pct": round(spread * 100, 2),
            "price": px, "ema50": ema, "reason": reason}


def atr_stop(price: float, symbol: str) -> dict[str, Any]:
    """Stop mesafesi = 1.5 * ATR(14)."""
    f = quant_lab.fetch(symbol, "1d", 60)
    atr = _atr(f) if f is not None else 0.0
    if atr <= 0:
        atr = price * 0.03  # fallback: mevcut %3 stop
    distance = atr * ATR_MULT
    return {"atr": round(atr, 6), "stop": round(price - distance, 6),
            "distance": round(distance, 6), "pct": round(distance / price * 100, 2)}


def mtf_confirm(symbol: str) -> dict[str, Any]:
    """Günlük + 4s EMA50 onayı — ikisi de üstünde olmalı."""
    d = daily_data(symbol)
    f4 = quant_lab.fetch(symbol, MTF_TF, 200)
    if d is None or f4 is None or len(d) < 60 or len(f4) < 60:
        return {"ok": False, "reason": "veri yok"}
    dp = float(d["Close"].iloc[-1]) > float(quant_lab.ema(d["Close"], 50).iloc[-1])
    f4p = float(f4["Close"].iloc[-1]) > float(quant_lab.ema(f4["Close"], 50).iloc[-1])
    return {"ok": bool(dp and f4p), "daily": dp, "h4": f4p,
            "reason": f"günlük={'üst' if dp else 'alt'}, 4s={'üst' if f4p else 'alt'}"}


def grid_plan(balance: float) -> dict[str, Any]:
    """₺50'yi 5 parçaya böl — TOPLAM limit aşılmaz."""
    total = min(100.0, max(50.0, balance * 0.10))
    part = round(total / GRID_PARTS, 4)
    return {"active": True, "total": round(total, 4), "part": part,
            "parts": GRID_PARTS, "step_pct": GRID_STEP * 100,
            "reason": f"yatay rejim — {GRID_PARTS}x{part} TL, %{GRID_STEP*100} adım"}


def loss_streak_block(state: dict[str, Any]) -> tuple[bool, str]:
    """Üst üste 3 zarar -> 24 saat dur."""
    until = float(state.get("loss_streak_until", 0) or 0)
    if time.time() < until:
        left = int(until - time.time())
        return True, f"3 ardışık zarar: {left//3600} sa {left%3600//60} dk kaldı"
    streak = int(state.get("loss_streak", 0) or 0)
    if streak >= LOSS_STREAK_LIMIT:
        state["loss_streak_until"] = time.time() + LOSS_COOLDOWN_SEC
        return True, "3 ARDIŞIK ZARAR, 24 SAAT DURDURULDU"
    return False, ""
