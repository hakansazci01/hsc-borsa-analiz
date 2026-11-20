import sys
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import binance_tr_bot as b, tr_scalper as t, quant_lab as q

s = b.account_status()
print("HESAP:", s.get("ok"))
for x in s.get("balances", []):
    print("  ", x)
print("scalper TRY:", t.available_try())
print("--- gunluk EMA50 (dogrulanmis edge) ---")
for sym in ("BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
            "LINKUSDT", "BNBUSDT", "SOLUSDT"):
    f = q.fetch(sym, "1d", 200)
    if f is None:
        continue
    m = q.ema(f["Close"], 50)
    last = float(f["Close"].iloc[-1])
    ma = float(m.iloc[-1])
    side = "UST" if last > ma else "ALT"
    print(f"  {sym:9s} fiyat={last:>10.2f} EMA50={ma:>10.2f} -> {side} ({(last/ma-1)*100:+.1f}%)")
