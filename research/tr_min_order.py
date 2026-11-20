import json
import urllib.request

url = "https://www.binance.tr/open/v1/common/symbols"
with urllib.request.urlopen(url, timeout=15) as r:
    data = json.loads(r.read().decode())

symbols = data.get("data", {}).get("list", [])
for s in symbols:
    if s.get("symbol") in ("BTC_TRY", "BTC_USDT", "ETH_TRY", "ETH_USDT"):
        print("===", s.get("symbol"), "type:", s.get("type"))
        for f in s.get("filters", []):
            print("  ", f)
