import sys, json, time, urllib.request, urllib.parse, hashlib, hmac
sys.path.insert(0, r"C:\Users\hakan\OneDrive\Desktop\al sat boto")
from ui.secrets_access import get

params = {"timestamp": int(time.time() * 1000), "recvWindow": 5000}
q = urllib.parse.urlencode(params)
sig = hmac.new(get("binance_tr", "secret_key").encode(), q.encode(), hashlib.sha256).hexdigest()
url = "https://www.binance.tr/open/v1/account/spot?" + q + "&signature=" + sig
req = urllib.request.Request(url, headers={"X-MBX-APIKEY": get("binance_tr", "api_key")})
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.loads(r.read().decode())

d = data.get("data", {})
print("status:", d.get("status"), "canTrade:", d.get("canTrade"), "canWithdraw:", d.get("canWithdraw"))
assets = d.get("accountAssets") or []
print("accountAssets sayisi:", len(assets))
for a in assets:
    print(json.dumps(a, ensure_ascii=False)[:300])
print("diger anahtarlar:", [k for k in d.keys() if k != "accountAssets"])
