import sys
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import tr_scalper as t

# En asiri satimda olan cifti sec (mean-reversion bahsi)
ranked = []
for s in t.PAIRS:
    r = t.signal(s)
    ranked.append((float(r.get("rsi", 50)), s, r))
ranked.sort()
for rsi, sym, r in ranked:
    print(f"{sym:9s} RSI={rsi:5.1f} -> {r.get('decision')}")

rsi, sym, sig = ranked[0]
print(f"\nSECILEN: {sym} (RSI {rsi}) - gercek ALIS emri")
res = t.buy(sym)
print("ALIS SONUCU:", "OK" if res.get("ok") else res.get("reason"))
print("Miktar:", res.get("qty"), "Fiyat:", res.get("price"))
if res.get("ok"):
    d = res.get("data", {})
    if isinstance(d, dict):
        body = d.get("data") or {}
        print("orderId:", body.get("orderId") or body.get("id"), "status:", body.get("status"))
