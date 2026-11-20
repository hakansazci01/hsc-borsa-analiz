"""Gunluk (1d) gercek veride trend stratejileri — train/test dogrulamali."""
import json, time, urllib.request, itertools
import numpy as np
import pandas as pd

FEE = 0.001
SYMS = ["BTCUSDT","ETHUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","LTCUSDT","LINKUSDT","BNBUSDT","SOLUSDT"]

def klines(sym, tf="1d", limit=1000):
    url=f"https://api.binance.me/api/v1/klines?symbol={sym}&interval={tf}&limit={limit}"
    for a in range(3):
        try:
            with urllib.request.urlopen(url,timeout=20) as r: rows=json.loads(r.read().decode())
            return pd.DataFrame([{"Open":float(x[1]),"High":float(x[2]),"Low":float(x[3]),
                                  "Close":float(x[4]),"Volume":float(x[5])} for x in rows])
        except Exception: time.sleep(1+a)
    return None

def ema(s,n): return s.ewm(span=n,adjust=False).mean()

def sig(f,kind,p):
    c,h,l,v=f["Close"],f["High"],f["Low"],f["Volume"]
    if kind=="ema_cross":
        a,b=ema(c,p[0]),ema(c,p[1])
        return ((a>b)&(a.shift(1)<=b.shift(1))).fillna(False),((a<b)&(a.shift(1)>=b.shift(1))).fillna(False)
    if kind=="breakout":
        n=p[0]; hh=h.shift(1).rolling(n).max(); ll=l.shift(1).rolling(n).min()
        return (c>hh).fillna(False),(c<ll).fillna(False)
    if kind=="ema_filter":
        n=p[0]; m=ema(c,n)
        return ((c>m)&(c.shift(1)<=m.shift(1))).fillna(False),((c<m)&(c.shift(1)>=m.shift(1))).fillna(False)
    if kind=="pullback":
        n=p[0]; m=ema(c,n)
        return ((c>m)&(l<=m)&(c.shift(1)<=m.shift(1))).fillna(False),(c<m*0.97).fillna(False)
    raise ValueError(kind)

def bt(f,kind,p,maxhold=90):
    ent,ex=sig(f,kind,p); c=f["Close"]; out=[]; i=200
    while i<len(c)-1:
        if not ent.iloc[i]: i+=1; continue
        px=c.iloc[i]; ep=None
        for j in range(i+1,min(i+maxhold+1,len(c))):
            if ex.iloc[j] or j==i+maxhold: ep=c.iloc[j]; break
        if ep is not None:
            out.append((ep-px)/px-2*FEE); i=j+1
        else: i+=1
    return out

P={
 "ema_cross":[(a,b) for a in (20,50,100) for b in (100,200) if a<b],
 "breakout":[(n,) for n in (20,50,100)],
 "ema_filter":[(n,) for n in (50,100,200)],
 "pullback":[(n,) for n in (50,100,200)],
}
rows=[]
for s in SYMS:
    f=klines(s)
    if f is None or len(f)<600: continue
    split=int(len(f)*0.6); tr,te=f.iloc[:split].copy(),f.iloc[split:].copy()
    for kind,pl in P.items():
        for p in pl:
            a=bt(tr,kind,p); b=bt(te,kind,p)
            if len(a)<3 or len(b)<2: continue
            rows.append({"sym":s,"strat":kind,"p":str(p),"ntr":len(a),
                         "tr":round(np.mean(a)*100,2),"nte":len(b),"te":round(np.mean(b)*100,2),
                         "tot":round(sum(a+b)*100,2)})
df=pd.DataFrame(rows)
print("kombinasyon:",len(df),"| train+test pozitif:", len(df[(df.tr>0)&(df.te>0)]))
print("\n=== EN IYI 15 (train) ===")
print(df.sort_values("tr",ascending=False).head(15).to_string(index=False))
print("\n=== TEST'I POZITIF OLANLAR ===")
print(df[df.te>0].sort_values("te",ascending=False).head(15).to_string(index=False))
