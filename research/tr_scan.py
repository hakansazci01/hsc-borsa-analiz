import json
import urllib.request

import pandas as pd

PAIRS = ["DOGETRY", "XPRTRY", "XRPTRY", "ADATRY", "TRXTRY", "LINKTRY", "AVAXTRY", "LTCTRY", "BNBTRY"]


def klines(sym, interval="1m", limit=60):
    url = f"https://api.binance.me/api/v1/klines?symbol={sym}&interval={interval}&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            rows = json.loads(r.read().decode())
        return pd.DataFrame([{
            "Open": float(x[1]), "High": float(x[2]), "Low": float(x[3]),
            "Close": float(x[4]), "Volume": float(x[5]),
        } for x in rows])
    except Exception:
        return None


for sym in PAIRS:
    f = klines(sym, "1m", 60)
    if f is None or len(f) < 30:
        print(f"{sym:9s} veri yok")
        continue
    c = f["Close"]
    ema9 = c.ewm(span=9, adjust=False).mean()
    ema20 = c.ewm(span=20, adjust=False).mean()
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1/7, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/7, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    r = float(rsi.iloc[-1])
    trend = "YUKARI" if ema9.iloc[-1] > ema20.iloc[-1] else "ASAGI"
    decision = "AL" if trend == "YUKARI" and r > 55 else "SAT" if trend == "ASAGI" and r < 45 else "BEKLE"
    last = float(c.iloc[-1])
    print(f"{sym:9s} fiyat={last:>11.4f}  RSI7={r:>5.1f}  EMA9/20={trend:6s}  -> {decision}")
