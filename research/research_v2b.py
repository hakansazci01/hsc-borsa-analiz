import json, time, urllib.request
import numpy as np
import pandas as pd

FEE = 0.001
SYMS = ["BTCUSDT","ETHUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","LTCUSDT","LINKUSDT"]

def klines(sym, tf="4h", limit=1000):
    url=f"https://api.binance.me/api/v1/klines?symbol={sym}&interval={tf}&limit={limit}"
    for a in range(3):
        try:
            with urllib.request.urlopen(url,timeout=20) as r: rows=json.loads(r.read().decode())
            return pd.DataFrame([{"Open":float(x[1]),"High":float(x[2]),"Low":float(x[3]),
                                  "Close":float(x[4]),"Volume":float(x[5])} for x in rows])
        except Exception: time.sleep(1+a)
    return None

print("=== AL-SAT TUT (buy & hold) 4h, ~166 gun ===")
for s in SYMS:
    f=klines(s)
    if f is None: continue
    r=(f["Close"].iloc[-1]/f["Close"].iloc[0]-1)*100
    print(f"{s:10s} buy&hold net(%-0.2)= {r-0.2:+.2f}%  (baslangic {f['Close'].iloc[0]:.4f} -> {f['Close'].iloc[-1]:.4f})")

print("\n=== SON 30 GUN ===")
for s in SYMS:
    f=klines(s)
    if f is None: continue
    f=f.tail(180)
    r=(f["Close"].iloc[-1]/f["Close"].iloc[0]-1)*100
    print(f"{s:10s} 30gun buy&hold = {r-0.2:+.2f}%")
