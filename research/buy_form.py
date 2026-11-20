import json
import sys
import time
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import tr_scalper as t

SYM = "FORM_TRY"
QTY = 0.7  # 0.7 * 8.10 = 5.67 TRY (minNotional 5, bakiye 7.12)

res = t._order(SYM, 0, QTY)  # 0 = AL, type 2 = MARKET
print("FORM_TRY ALIS:", "OK" if res.get("ok") else res.get("reason"))
if res.get("ok"):
    body = (res.get("data") or {}).get("data") or {}
    print("orderId:", body.get("orderId") or body.get("id"), "status:", body.get("status"))
    st = t._load()
    st["position"] = {
        "symbol": SYM, "qty": QTY, "entry": 8.10,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    t._save(st)
    print("pozisyon kaydedildi: TP +0.45% / SL -0.35%")
