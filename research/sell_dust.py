import sys
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import tr_scalper as t

# Toz BTC'yi piyasa emriyle sat (MARKET_LOT_SIZE minQty = 0)
res = t._order("BTC_TRY", 1, 0.0000094)
print("TOZ BTC SATIS:", "OK" if res.get("ok") else res.get("reason"))
if res.get("ok"):
    d = res.get("data") or {}
    body = d.get("data") or {}
    print("orderId:", body.get("orderId") or body.get("id"), "status:", body.get("status"))
