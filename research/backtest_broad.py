"""Daha genis gercek veri aramasi: 4 giris mantigi x 2 zaman dilimi."""
import json, sys, time, urllib.request, itertools
import pandas as pd
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")

PAIRS = ["XRP_TRY", "DOGE_TRY", "ADA_TRY", "TRX_TRY", "LTC_TRY", "LINK_TRY", "FORM_TRY"]
FEE = 0.001

def klines(sym, interval, limit=500):
    url = f"https://api.binance.me/api/v1/klines?symbol={sym.replace('_','')}&interval={interval}&limit={limit}"
    for a in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                rows = json.loads(r.read().decode())
            return pd.DataFrame([{"Open":float(x[1]),"High":float(x[2]),"Low":float(x[3]),
                                  "Close":float(x[4]),"Volume":float(x[5])} for x in rows])
        except Exception:
            time.sleep(1+a)
    return None

def ind(f):
    c=f["Close"]; d=c.diff()
    g=d.clip(lower=0).ewm(alpha=1/7,adjust=False).mean()
    l=(-d.clip(upper=0)).ewm(alpha=1/7,adjust=False).mean()
    rsi=100-100/(1+g/l.replace(0,float("nan")))
    e9=c.ewm(span=9,adjust=False).mean(); e20=c.ewm(span=20,adjust=False).mean()
    vavg=f["Volume"].rolling(20).mean()
    return c,rsi,e9,e20,f["Volume"],vavg

def entry_signals(f, mode, rsi_lim):
    c,rsi,e9,e20,vol,vavg=ind(f)
    sig=[False]*len(c)
    for i in range(30,len(c)-1):
        if mode=="oversold1" and rsi.iloc[i]<rsi_lim and c.iloc[i]>c.iloc[i-1]: sig[i]=True
        if mode=="oversold2" and rsi.iloc[i]<rsi_lim and c.iloc[i]>c.iloc[i-1]>c.iloc[i-2]: sig[i]=True
        if mode=="breakout" and e9.iloc[i]>e20.iloc[i] and c.iloc[i]>c.iloc[i-10:i].max() and vol.iloc[i]>vavg.iloc[i]*1.2: sig[i]=True
        if mode=="emacross" and e9.iloc[i]>e20.iloc[i] and e9.iloc[i-1]<=e20.iloc[i-1]: sig[i]=True
    return c,sig

def sim(f, mode, rsi_lim, tp, sl, maxhold):
    c,sig=entry_signals(f,mode,rsi_lim)
    out=[]
    i=30
    while i < len(c)-1:
        if not sig[i]: i+=1; continue
        px=c.iloc[i]; ex=None
        for j in range(i+1,min(i+maxhold+1,len(c))):
            if c.iloc[j]>=px*(1+tp): ex=px*(1+tp); break
            if f["Low"].iloc[j]<=px*(1-sl): ex=px*(1-sl); break
            if j==i+maxhold: ex=c.iloc[j]; break
        if ex is not None:
            out.append((ex-px)/px-2*FEE); i=j+1
        else: i+=1
    return out

rows=[]
for interval in ("1m","5m"):
    data={p:klines(p,interval) for p in PAIRS}
    data={p:f for p,f in data.items() if f is not None and len(f)>100}
    print(interval,"cift:",len(data),flush=True)
    for mode,rsi_lim,tp,sl,hold in itertools.product(
        ("oversold1","oversold2","breakout","emacross"),
        (15,20,25,30),
        (0.003,0.005,0.008),
        (0.003,0.005),
        (10,20)):
        tr=[]
        for f in data.values(): tr+=sim(f,mode,rsi_lim,tp,sl,hold)
        if len(tr)<10: continue
        wins=sum(1 for x in tr if x>0)
        rows.append({"tf":interval,"mode":mode,"rsi":rsi_lim,"tp":tp,"sl":sl,
                     "hold":hold,"n":len(tr),"win%":round(wins/len(tr)*100,1),
                     "net%":round(sum(tr)*100,2),"exp%":round(sum(tr)/len(tr)*100,3)})

df=pd.DataFrame(rows)
if df.empty:
    print("SONUC YOK"); raise SystemExit
print("\n=== EN IYI 20 (komisyon sonrası) ===")
print(df.sort_values("exp%",ascending=False).head(20).to_string(index=False))
print("\n=== POZITIF EXPECTANCY SAYISI:", (df["exp%"]>0).sum(), "/", len(df))
print("=== EN KOTU 3 ===")
print(df.sort_values("exp%").head(3).to_string(index=False))
