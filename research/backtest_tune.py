"""Gercek 1-dk Binance verisiyle komsu ayar arama (komisyon sonrası net)."""
import json
import sys
import urllib.request
import itertools
import pandas as pd

sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")

PAIRS = ["XRP_TRY", "DOGE_TRY", "ADA_TRY", "TRX_TRY", "LTC_TRY", "LINK_TRY", "FORM_TRY"]
FEE = 0.001  # her yon


def klines(sym):
    import time
    url = f"https://api.binance.me/api/v1/klines?symbol={sym.replace('_','')}&interval=1m&limit=500"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                rows = json.loads(r.read().decode())
            return pd.DataFrame([{
                "Open": float(x[1]), "High": float(x[2]), "Low": float(x[3]),
                "Close": float(x[4]), "Volume": float(x[5]),
            } for x in rows])
        except Exception:
            time.sleep(1 + attempt)
    return None


def indicators(f):
    c = f["Close"]
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1/7, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1/7, adjust=False).mean()
    rsi = 100 - 100/(1 + gain/loss.replace(0, float("nan")))
    e9 = c.ewm(span=9, adjust=False).mean()
    e20 = c.ewm(span=20, adjust=False).mean()
    return c, rsi, e9, e20, f["Volume"]


def simulate(f, oversold, tp, sl, maxhold=15):
    c, rsi, e9, e20, vol = indicators(f)
    trades = []
    i = 30
    while i < len(c) - 1:
        up = e9.iloc[i] > e20.iloc[i]
        # sadece asiri satim + ilk yukselis (en cok sinyal ureten bacak)
        entry = None
        if rsi.iloc[i] < oversold and c.iloc[i] > c.iloc[i-1]:
            entry = (c.iloc[i], i)
        if entry is None:
            i += 1
            continue
        px, ei = entry
        exit_px = None
        reason = ""
        for j in range(ei + 1, min(ei + maxhold + 1, len(c))):
            hi, lo, cl = f["High"].iloc[j], f["Low"].iloc[j], c.iloc[j]
            if cl >= px * (1 + tp):
                exit_px, reason = px * (1 + tp), "tp"
                break
            if lo <= px * (1 - sl):
                exit_px, reason = px * (1 - sl), "sl"
                break
            if j == ei + maxhold:
                exit_px, reason = cl, "time"
                break
        if exit_px is not None:
            gross = (exit_px - px)/px
            net = gross - 2*FEE
            trades.append((net, reason))
            i = j + 1
        else:
            i += 1
    return trades


data = {p: klines(p) for p in PAIRS}
data = {p: f for p, f in data.items() if f is not None and len(f) > 100}
print("veri alinan cift:", list(data), "(her biri ~500 dk)", flush=True)

results = []
for oversold, tp, sl in itertools.product((20, 25, 30, 35, 40), (0.003, 0.005, 0.008, 0.012), (0.002, 0.003, 0.004, 0.006)):
    all_tr = []
    for f in data.values():
        all_tr += simulate(f, oversold, tp, sl)
    if len(all_tr) < 12:
        continue
    wins = [t for t in all_tr if t[0] > 0]
    total = sum(t[0] for t in all_tr)
    results.append({
        "rsi": oversold, "tp": tp, "sl": sl,
        "trades": len(all_tr),
        "win%": round(len(wins)/len(all_tr)*100, 1),
        "net%": round(total*100, 2),
        "exp%": round(total/len(all_tr)*100, 3),
    })

res = pd.DataFrame(results).sort_values("net%", ascending=False)
print("\n=== EN IYI 12 ===")
print(res.head(12).to_string(index=False))
print("\n=== EN KOTU 5 ===")
print(res.tail(5).to_string(index=False))
print("\nToplam kombinasyon:", len(res))
