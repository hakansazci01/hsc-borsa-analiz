import sys
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui import binance_tr_bot as b

status = b.account_status()
print("hesap:", "OK" if status.get("ok") else status.get("reason"))
if status.get("ok"):
    print("bakiye varligi:", [x.get("asset") for x in status.get("balances", [])])
    import json, urllib.request, hashlib, hmac, time, urllib.parse
    from ui.secrets_access import get
    params = {"timestamp": int(time.time() * 1000), "recvWindow": 5000}
    q = urllib.parse.urlencode(params)
    sig = hmac.new(get("binance_tr", "secret_key").encode(), q.encode(), hashlib.sha256).hexdigest()
    url = "https://www.binance.tr/open/v1/account/spot?" + q + "&signature=" + sig
    req = urllib.request.Request(url, headers={"X-MBX-APIKEY": get("binance_tr", "api_key")})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    for a in (data.get("data", {}).get("accountAssets") or []):
        free = float(a.get("free", 0) or 0)
        if free > 0:
            print("  ", a.get("asset"), "serbest:", round(free, 4))
    print("canTrade:", data.get("data", {}).get("canTrade"), "canWithdraw:", data.get("data", {}).get("canWithdraw"))

for sym in ("BTC_USDT", "ETH_USDT"):
    try:
        sig = b.quick_signal(sym)
        print(sym, "->", sig.get("decision"), "fiyat:", sig.get("price"), "RSI:", sig.get("rsi"))
    except Exception as e:
        print(sym, "hata:", type(e).__name__, str(e)[:60])
