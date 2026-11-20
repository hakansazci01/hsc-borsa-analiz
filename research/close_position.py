import sys
import time
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import tr_scalper as t

st = t._load()
pos = st.get("position")
if not pos:
    print("acik pozisyon yok")
    raise SystemExit

px = t.price("FORM_TRY") or 8.12
try_bal = t.available_try()
form_dust = t.asset_balance("FORM")
# Gercek net:_mevcut TRY + kalan FORM degeri - baslangic TRY (7.1238677)
net = round(try_bal + form_dust * px - 7.1238677, 4)
entry_ts = float(pos.get("entry_ts", time.time()))
hist = st.get("history", [])
hist.append({
    "symbol": "FORM_TRY",
    "qty": 0.6,
    "entry": 8.10,
    "exit": px,
    "gross_pnl": round(net + 0.0114, 4),
    "fee": 0.0114,
    "net_pnl": net,
    "pnl": net,
    "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    "duration_sec": round(time.time() - entry_ts, 0),
    "reason": "zaman/quote satis (0.09867 FORM toz kaldı)",
})
st["history"] = hist[-20:]
st["realized_pnl"] = round(sum(float(h.get("net_pnl", 0)) for h in hist), 4)
st.pop("position", None)
t._save(st)
print("pozisyon kapatildi. net K/Z:", net, "TRY:", try_bal, "FORM tozu:", form_dust)
