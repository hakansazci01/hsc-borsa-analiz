import sys
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import quant_lab, tr_scalper, autonomous

COINS = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
         "LINKUSDT", "BNBUSDT", "SOLUSDT")
above = 0
for s in COINS:
    f = quant_lab.fetch(s, "1d", 200)
    if f is None:
        continue
    m = quant_lab.ema(f["Close"], 50)
    last = float(f["Close"].iloc[-1])
    ma = float(m.iloc[-1])
    ok = last > ma
    above += int(ok)
    print(f"{s:9s} {'UST' if ok else 'ALT'} ({(last/ma-1)*100:+.1f}%)")
print("EMA50 ustundeki coin:", above, "/", len(COINS))

print("\n--- 1dk sinyaller ---")
for p in tr_scalper.tradeable_pairs():
    x = tr_scalper.signal(p)
    print(f"  {p:9s} {x.get('decision'):6s} RSI={x.get('rsi')}")

print("\n--- otonom ---")
s = autonomous._load()
d = s.get("last_decision", {})
print("karar:", d.get("decision"), d.get("at"), "| robust:", d.get("robust"),
      "| isabet:", autonomous.accuracy(s))
