import sys
import time
from datetime import datetime
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import tr_scalper as t

st = t._load()
pos = st.get("position")
if pos:
    entry = float(pos.get("entry", 0))
    if not pos.get("entry_ts"):
        try:
            pos["entry_ts"] = datetime.strptime(pos["time"], "%Y-%m-%d %H:%M:%S").timestamp()
        except Exception:
            pos["entry_ts"] = time.time()
    pos["tp"] = round(entry * (1 + t.TAKE_PROFIT), 6)
    pos["sl"] = round(entry * (1 - t.STOP_LOSS), 6)
    pos["order_id"] = pos.get("order_id") or "1387910371"
    pos["cost"] = round(entry * float(pos.get("qty", 0)), 4)
    st["position"] = pos
    st.setdefault("fees_paid", round(entry * float(pos.get("qty", 0)) * 0.001, 4))
    t._save(st)
    print("pozisyon meta verisi tamamlandi")
    print(pos)
else:
    print("acik pozisyon yok")
