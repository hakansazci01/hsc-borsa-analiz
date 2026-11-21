"""
Kantitatif araştırma laboratuvarı — gerçek veri, komisyon, iç/dış örneklem.

Hiçbir sonuç uydurulmaz. Veri alınamazsa "veri yok" döner; kârlı bir strateji
bulunamazsa karar "İŞLEM YOK" olur. Amaç iddia değil, ölçümdür.
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

import numpy as np
import pandas as pd

FEE = 0.001  # her yon, Binance TR spot VIP0
SYMBOLS = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LTCUSDT", "LINKUSDT")
TIMEFRAMES = ("15m", "1h", "4h", "1d")


def fetch(symbol: str, tf: str, limit: int = 1000) -> pd.DataFrame | None:
    url = f"https://api.binance.me/api/v1/klines?symbol={symbol}&interval={tf}&limit={limit}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                rows = json.loads(resp.read().decode())
            return pd.DataFrame([{
                "Open": float(x[1]), "High": float(x[2]), "Low": float(x[3]),
                "Close": float(x[4]), "Volume": float(x[5]),
            } for x in rows])
        except Exception:
            time.sleep(1 + attempt)
    return None


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))


def signals(frame: pd.DataFrame, kind: str, p: tuple[Any, ...]):
    c, h, l, v = frame["Close"], frame["High"], frame["Low"], frame["Volume"]
    if kind == "ema_cross":
        a, b = ema(c, p[0]), ema(c, p[1])
        return ((a > b) & (a.shift(1) <= b.shift(1))).fillna(False), \
               ((a < b) & (a.shift(1) >= b.shift(1))).fillna(False)
    if kind == "breakout":
        n, mult = p
        hh, ll = h.shift(1).rolling(n).max(), l.shift(1).rolling(n).min()
        va = v.rolling(20).mean()
        return ((c > hh) & (v > va * mult)).fillna(False), (c < ll).fillna(False)
    if kind == "rsi_revert":
        lo, hi = p
        r = rsi(c)
        return ((r < lo) & (r.shift(1) >= lo)).fillna(False), (r > hi).fillna(False)
    if kind == "trend_pullback":
        n, k = p
        m = ema(c, n)
        return ((c > m) & (l <= m * (1 + k))).fillna(False), (c < m * (1 - abs(k))).fillna(False)
    if kind == "ema_filter":
        n = p[0]
        m = ema(c, n)
        return ((c > m) & (c.shift(1) <= m.shift(1))).fillna(False), \
               ((c < m) & (c.shift(1) >= m.shift(1))).fillna(False)
    if kind == "pullback":
        n = p[0]
        m = ema(c, n)
        return ((c > m) & (l <= m) & (c.shift(1) <= m.shift(1))).fillna(False), \
               (c < m * 0.97).fillna(False)
    raise ValueError(kind)


def backtest(frame: pd.DataFrame, kind: str, p: tuple[Any, ...],
             maxhold: int = 30, slippage: float = 0.0) -> list[dict]:
    """Backtest — slippage: alım fiyatın %üstünden, satım %altından.

    Varsayılan slippage=0 → mevcut çağrılar (strateji) aynı sonucu verir.
    Stratejiye dokunulmaz; sadece getiri hesabına kayma eklenir.
    """
    ent, ex = signals(frame, kind, p)
    c = frame["Close"]
    out: list[dict] = []
    i = 60
    while i < len(c) - 1:
        if not ent.iloc[i]:
            i += 1
            continue
        px = c.iloc[i] * (1 + slippage)  # alış kayması
        exit_px = None
        for j in range(i + 1, min(i + maxhold + 1, len(c))):
            if ex.iloc[j] or j == i + maxhold:
                exit_px = c.iloc[j] * (1 - slippage)  # satış kayması
                break
        if exit_px is not None:
            out.append({"ret": (exit_px - px) / px - 2 * FEE, "i": i})
            i = j + 1
        else:
            i += 1
    return out


def regime(frame: pd.DataFrame) -> dict[str, Any]:
    """Piyasa rejimi: günlük EMA50 üstünde mi? (doğrulanmış stratejiyle uyumlu)."""
    c = frame["Close"]
    if len(c) < 60:
        return {"name": "veri yetersiz", "bull": None}
    m = ema(c, 50)
    last = float(c.iloc[-1])
    ma = float(m.iloc[-1])
    return {
        "name": "YUKARI (bull)" if last > ma else "ASAGI (bear)",
        "bull": last > ma,
        "price": round(last, 4),
        "ema50": round(ma, 4),
        "dist_pct": round((last / ma - 1) * 100, 2),
    }


def research() -> dict[str, Any]:
    """Tüm serilerde iç/dış örneklem taraması yapar, dürüst karar döndürür."""
    params = {
        "ema_cross": [(a, b) for a in (9, 20, 50) for b in (50, 100, 200) if a < b],
        "breakout": [(n, m) for n in (10, 20, 40) for m in (1.0, 1.3, 1.6)],
        "rsi_revert": [(lo, hi) for lo in (20, 30, 40) for hi in (50, 60, 70)],
        "trend_pullback": [(n, k) for n in (50, 100) for k in (-0.02, -0.01, 0.01)],
        "ema_filter": [(n,) for n in (50, 100, 200)],
        "pullback": [(n,) for n in (50, 100)],
    }
    rows: list[dict[str, Any]] = []
    fetched = 0
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            frame = fetch(sym, tf)
            if frame is None or len(frame) < 400:
                continue
            fetched += 1
            split = int(len(frame) * 0.6)
            tr, te = frame.iloc[:split].copy(), frame.iloc[split:].copy()
            for kind, plist in params.items():
                for p in plist:
                    hold = 90 if tf == "1d" else 30
                    a = backtest(tr, kind, p, maxhold=hold)
                    b = backtest(te, kind, p, maxhold=hold)
                    min_a, min_b = (4, 2) if tf == "1d" else (8, 6)
                    if len(a) < min_a or len(b) < min_b:
                        continue
                    rows.append({
                        "symbol": sym, "tf": tf, "strategy": kind, "params": str(p),
                        "train_n": len(a), "train_exp": float(np.mean([x["ret"] for x in a])) * 100,
                        "test_n": len(b), "test_exp": float(np.mean([x["ret"] for x in b])) * 100,
                    })
    if not rows:
        return {"ok": False, "reason": "Gerçek veri alınamadı", "series": 0}
    df = pd.DataFrame(rows)
    valid = df[(df["train_exp"] > 0) & (df["test_exp"] > 0)]
    best = df.sort_values("train_exp", ascending=False).iloc[0]
    # 4h son seri rejimi
    last_frame = fetch("BTCUSDT", "1d", 200)
    return {
        "ok": True,
        "series": fetched,
        "combinations": len(df),
        "robust_count": len(valid),
        "best_train": {
            "key": f"{best['symbol']} {best['tf']} {best['strategy']} {best['params']}",
            "train": round(float(best["train_exp"]), 3),
            "test": round(float(best["test_exp"]), 3),
        },
        "verdict": "İŞLEM YOK — doğrulanmış kârlı strateji yok"
                   if len(valid) == 0 else f"{len(valid)} aday doğrulandı, manuel inceleme gerekir",
        "regime": regime(last_frame) if last_frame is not None else {"name": "veri yok", "bull": None},
    }
