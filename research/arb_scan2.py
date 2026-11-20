"""Gercek cift fiyatlarla capraz kur farki taramasi."""
import json, urllib.request, time
import pandas as pd

def get(url):
    for a in range(3):
        try:
            with urllib.request.urlopen(url, timeout=12) as r:
                return json.loads(r.read().decode())
        except Exception:
            time.sleep(0.5+a)
    return None

with urllib.request.urlopen("https://www.binance.tr/open/v1/common/symbols", timeout=15) as r:
    tr_syms = {s["symbol"] for s in json.loads(r.read().decode())["data"]["list"]}

rate = 50.40  # USDT/TRY gercek piyasa
base = ["BTC","ETH","XRP","DOGE","ADA","LTC","LINK","BNB","AVAX","SOL","TRX","DOT","MATIC","UNI","ATOM"]
rows=[]
for b in base:
    try_pair = f"{b}_TRY"
    if try_pair not in tr_syms:
        continue
    # TRY fiyat: Binance TR tip 1 -> api.binance.me
    d1 = get(f"https://api.binance.me/api/v1/ticker/price?symbol={b}TRY")
    d2 = get(f"https://api.binance.me/api/v3/ticker/price?symbol={b}USDT")
    if not d1 or not d2 or "price" not in d1 or "price" not in d2:
        continue
    p_try=float(d1["price"]); p_usdt=float(d2["price"])
    implied=p_usdt*rate
    diff=(p_try-implied)/implied*100
    rows.append({"coin":b,"TRY":p_try,"USDT":p_usdt,"impliedTRY":round(implied,4),
                 "fark%":round(diff,3),"net%":round(diff-0.2,3)})

df=pd.DataFrame(rows).sort_values("fark%",ascending=False)
print(df.to_string(index=False))
print("\nPozitif net arbitraj:", (df["net%"]>0).sum(), "/", len(df))
