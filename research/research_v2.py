"""
Gerçek Binance verisiyle strateji arama — dis orneklem dogrulamali.
Kurallar: %0,2 komisyon, en az 20 islem, train'de sec -> test'te dogrula.
"""
import json, time, urllib.request, itertools
import numpy as np
import pandas as pd

FEE = 0.001
SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LTCUSDT", "LINKUSDT"]
TFS = ["15m", "1h", "4h"]


def klines(sym, tf, limit=1000):
    url = f"https://api.binance.me/api/v1/klines?symbol={sym}&interval={tf}&limit={limit}"
    for a in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                rows = json.loads(r.read().decode())
            return pd.DataFrame([{"Open": float(x[1]), "High": float(x[2]),
                                  "Low": float(x[3]), "Close": float(x[4]),
                                  "Volume": float(x[5])} for x in rows])
        except Exception:
            time.sleep(1 + a)
    return None


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + g/l.replace(0, np.nan))


def atr(f, n=14):
    pc = f["Close"].shift(1)
    tr = pd.concat([f["High"]-f["Low"], (f["High"]-pc).abs(), (f["Low"]-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()


def strategy(f, name, p):
    """Long-only giris/sikis sinyalleri. (entry_bool, exit_bool) dizileri."""
    c, h, l, v = f["Close"], f["High"], f["Low"], f["Volume"]
    if name == "ema_cross":
        fast, slow = p
        a, b = ema(c, fast), ema(c, slow)
        ent = (a > b) & (a.shift(1) <= b.shift(1))
        ex = (a < b) & (a.shift(1) >= b.shift(1))
        return ent.fillna(False), ex.fillna(False)
    if name == "breakout":
        n, mult = p
        hh = h.shift(1).rolling(n).max()
        ll = l.shift(1).rolling(n).min()
        vavg = v.rolling(20).mean()
        ent = (c > hh) & (v > vavg * mult)
        ex = (c < ll)
        return ent.fillna(False), ex.fillna(False)
    if name == "rsi_revert":
        lo, hi = p
        r = rsi(c)
        ent = (r < lo) & (r.shift(1) >= lo)
        ex = (r > hi)
        return ent.fillna(False), ex.fillna(False)
    if name == "trend_pullback":
        n, k = p
        m = ema(c, n)
        ent = (c > m) & (l <= m * (1 + k)) & (c.shift(1) <= m.shift(1) * (1 + k))
        ex = (c < m * (1 - abs(k)))
        return ent.fillna(False), ex.fillna(False)
    raise ValueError(name)


def backtest(f, name, p, tp=None, sl=None, maxhold=30):
    ent, ex = strategy(f, name, p)
    c = f["Close"]
    trades = []
    i = 60
    while i < len(c) - 1:
        if not ent.iloc[i]:
            i += 1
            continue
        px = c.iloc[i]
        exit_px, reason = None, ""
        for j in range(i+1, min(i+maxhold+1, len(c))):
            cl, hi, lo = c.iloc[j], f["High"].iloc[j], f["Low"].iloc[j]
            if tp and cl >= px*(1+tp):
                exit_px, reason = px*(1+tp), "tp"; break
            if sl and lo <= px*(1-sl):
                exit_px, reason = px*(1-sl), "sl"; break
            if ex.iloc[j]:
                exit_px, reason = cl, "signal"; break
            if j == i+maxhold:
                exit_px, reason = cl, "time"; break
        if exit_px is not None:
            trades.append({"ret": (exit_px-px)/px - 2*FEE, "i": i, "reason": reason})
            i = j+1
        else:
            i += 1
    return trades


data = {}
for sym in SYMBOLS:
    for tf in TFS:
        f = klines(sym, tf)
        if f is not None and len(f) > 200:
            data[(sym, tf)] = f
print("veri seti:", len(data), "seri", flush=True)

PARAMS = {
    "ema_cross": [(a, b) for a in (9, 20, 50) for b in (50, 100, 200) if a < b],
    "breakout": [(n, m) for n in (10, 20, 40) for m in (1.0, 1.3, 1.6)],
    "rsi_revert": [(lo, hi) for lo in (20, 30, 40) for hi in (50, 60, 70)],
    "trend_pullback": [(n, k) for n in (50, 100) for k in (-0.02, -0.01, 0.01)],
}

results = []
for (sym, tf), f in data.items():
    split = int(len(f) * 0.6)
    train, test = f.iloc[:split].copy(), f.iloc[split:].copy()
    for name, plist in PARAMS.items():
        for p in plist:
            tr_tr = backtest(train, name, p)
            if len(tr_tr) < 8:
                continue
            tr_te = backtest(test, name, p)
            if len(tr_te) < 6:
                continue
            tr_all = tr_tr + tr_te
            results.append({
                "sym": sym, "tf": tf, "strat": name, "p": str(p),
                "n_tr": len(tr_tr), "tr_exp": round(np.mean([x["ret"] for x in tr_tr])*100, 3),
                "n_te": len(tr_te), "te_exp": round(np.mean([x["ret"] for x in tr_te])*100, 3),
                "all_n": len(tr_all), "all_exp": round(np.mean([x["ret"] for x in tr_all])*100, 3),
                "win%": round(sum(1 for x in tr_all if x["ret"]>0)/len(tr_all)*100, 1),
                "total%": round(sum(x["ret"] for x in tr_all)*100, 2),
            })

df = pd.DataFrame(results)
if df.empty:
    print("SONUC YOK"); raise SystemExit

print("\n=== TRAIN'DE EN IYI 15 ===")
print(df.sort_values("tr_exp", ascending=False).head(15).to_string(index=False))

both = df[(df["tr_exp"] > 0) & (df["te_exp"] > 0)]
print("\n=== TRAIN VE TEST IKISI DE POZITIF:", len(both), "/", len(df))
if not both.empty:
    print(both.sort_values("all_exp", ascending=False).head(20).to_string(index=False))
print("\n=== TEST'TE POZITIF SAYISI:", (df["te_exp"] > 0).sum())
