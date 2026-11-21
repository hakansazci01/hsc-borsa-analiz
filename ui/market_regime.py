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
    """ADX + EMA50 ile REJİM: ADX<25 -> YATAY; üst/alt + ADX>25 -> BOĞA/AYI."""
    f = daily_data(symbol)
    if f is None or len(f) < 60:
        return {"name": "YATAY", "bull": False, "bear": False, "range": True,
                "reason": "veri yok — güvenli yatay"}
    c = f["Close"]
    ma = quant_lab.ema(c, 50)
    px, ema = float(c.iloc[-1]), float(ma.iloc[-1])
    adx = _adx(f)
    if adx < TREND_ADX:
        name, bull, bear, rng = "YATAY", False, False, True
        reason = f"ADX {adx:.1f} < {TREND_ADX:.0f} — yatay, Grid için bekle"
    elif px > ema:
        name, bull, bear, rng = "BOĞA", True, False, False
        reason = f"fiyat {px:.4f} > EMA50 {ema:.4f} ve ADX {adx:.1f} > {TREND_ADX:.0f}"
    else:
        name, bull, bear, rng = "AYI", False, True, False
        reason = f"fiyat {px:.4f} < EMA50 {ema:.4f} ve ADX {adx:.1f} > {TREND_ADX:.0f}"
    return {"name": name, "bull": bull, "bear": bear, "range": rng,
            "adx": round(adx, 2), "price": px, "ema50": ema, "reason": reason}


def atr_stop(price: float, symbol: str, frame: Any = None) -> dict[str, Any]:
    """Stop mesafesi = 1.5 * ATR(14). frame verilirse onu kullan (test için)."""
    f = frame if frame is not None else quant_lab.fetch(symbol, "1d", 60)
    atr = _atr(f) if f is not None else 0.0
    if atr <= 0:
        atr = price * 0.01  # güvenli fallback (veri yoksa dar stop)
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


def grid_levels(base_price: float, part: float, parts: int = GRID_PARTS) -> list[dict[str, Any]]:
    """Grid kademeleri: her %1 düşüşte AL, her %1 yükselişte SAT."""
    levels = []
    for i in range(1, parts + 1):
        levels.append({
            "level": i,
            "buy_price": round(base_price * (1 - GRID_STEP * i), 6),
            "sell_price": round(base_price * (1 + GRID_STEP * i), 6),
            "amount": part,
        })
    return levels


def grid_decision(current_price: float, anchor: float, bought: int, sold: int,
                  parts: int = GRID_PARTS) -> dict[str, Any]:
    """Fiyatın kaç kademe düştüğüne/çıktığına göre AL/SAT/BEKLE."""
    drop = (anchor - current_price) / anchor
    rise = (current_price - anchor) / anchor
    target_buys = min(parts, int(drop / GRID_STEP + 1e-9))
    target_sells = min(parts, int(rise / GRID_STEP + 1e-9))
    if target_buys > bought:
        return {"action": "AL", "levels": target_buys - bought,
                "reason": f"%{drop*100:.2f} düşüş — {target_buys-bought} kademe AL"}
    if target_sells > sold:
        return {"action": "SAT", "levels": target_sells - sold,
                "reason": f"%{rise*100:.2f} yükseliş — {target_sells-sold} kademe SAT"}
    return {"action": "BEKLE", "levels": 0,
            "reason": f"düşüş %{drop*100:.2f} / yükseliş %{rise*100:.2f} — kademe yok"}


def loss_streak_block(state: dict[str, Any]) -> tuple[bool, str]:
    """Üst üste 3 zarar -> 24 saat dur; süre bitince sayacı sıfırla, tekrar dene."""
    until = float(state.get("loss_streak_until", 0) or 0)
    if time.time() < until:
        left = int(until - time.time())
        return True, f"3 ARDIŞIK ZARAR, 24 SAAT DURDURULDU — {left//3600} sa {left%3600//60} dk kaldı"
    # 24 saat dolduysa sayacı sıfırla
    if until and time.time() >= until:
        state["loss_streak"] = 0
        state["loss_streak_until"] = 0
        state["loss_streak_notified"] = False
    streak = int(state.get("loss_streak", 0) or 0)
    if streak >= LOSS_STREAK_LIMIT:
        state["loss_streak_until"] = time.time() + LOSS_COOLDOWN_SEC
        return True, "3 ARDIŞIK ZARAR, 24 SAAT DURDURULDU"
    return False, ""


def loss_streak_count(state: dict[str, Any]) -> int:
    """Panel için: üst üste kaç zarar var (0-3)."""
    return min(int(state.get("loss_streak", 0) or 0), LOSS_STREAK_LIMIT)
