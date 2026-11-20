"""Gunluk pullback(50) stratejisini coklu coin'de derin dogrula."""
import json, urllib.request, time
import numpy as np
import pandas as pd

FEE=0.001
SYMS=["BTCUSDT","ETHUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","LTCUSDT","LINKUSDT","BNBUSDT","SOLUSDT"]

def kl(s):
    u=f"https://api.binance.me/api/v1/klines?symbol={s}&interval=1d&limit=1000"
    for a in range(3):
        try:
            with urllib.request.urlopen(u,timeout=20) as r: rows=json.loads(r.read().decode())
            return pd.DataFrame([{"Open":float(x[1]),"High":float(x[2]),"Low":float(x[3]),
                                  "Close":float(x[4]),"Volume":float(x[5])} for x in rows])
        except Exception: time.sleep(1+a)
    return None

def ema(s,n): return s.ewm(span=n,adjust=False).mean()

def trades(f,n=50,maxhold=90):
    c,l=f["Close"],f["Low"]; m=ema(c,n)
    ent=((c>m)&(l<=m)&(c.shift(1)<=m.shift(1))).fillna(False)
    ex=(c<m*0.97).fillna(False)
    out=[]; i=200
    while i<len(c)-1:
        if not ent.iloc[i]: i+=1; continue
        px=c.iloc[i]; ep=None; reason=""
        for j in range(i+1,min(i+maxhold+1,len(c))):
            if ex.iloc[j]: ep=c.iloc[j]; reason="sinyal"; break
            if j==i+maxhold: ep=c.iloc[j]; reason="zaman"; break
        if ep is not None:
            out.append({"ret":(ep-px)/px-2*FEE,"gun":j-i,"neden":reason})
            i=j+1
        else: i+=1
    return out

allrows=[]
for s in SYMS:
    f=kl(s)
    if f is None: continue
    tr=trades(f)
    if not tr: continue
    rets=[x["ret"] for x in tr]
    # equity curve
    eq=np.cumprod([1+r for r in rets])
    dd=float((eq/np.maximum.accumulate(eq)-1).min()*100)
    c=f["Close"]; m=ema(c,50)
    above=float(c.iloc[-1])>float(m.iloc[-1])
    allrows.append({"coin":s,"islem":len(tr),"kazanma%":round(sum(1 for r in rets if r>0)/len(rets)*100,1),
                    "ort_islem%":round(np.mean(rets)*100,2),"toplam%":round((eq[-1]-1)*100,1),
                    "max_dd%":round(dd,1),"ort_gun":round(np.mean([x["gun"] for x in tr]),0),
                    "SU_AN":("⇧ EMA50 üstü" if above else "⇩ EMA50 altı")})

df=pd.DataFrame(allrows)
print(df.to_string(index=False))
print("\nOrtalama islem getirisi:",round(df["ort_islem%"].mean(),2),"%")
print("Pozitif coin:", (df["ort_islem%"]>0).sum(), "/", len(df))
