import json
import urllib.request

with urllib.request.urlopen("https://www.binance.tr/open/v1/common/symbols", timeout=15) as r:
    syms = json.loads(r.read().decode()).get("data", {}).get("list", [])

targets = [s for s in syms if s.get("symbol", "").endswith("_TRY") and
           s.get("symbol", "").split("_")[0] in
           ("DOGE", "XRP", "TRX", "ADA", "LTC", "BNB", "SHIB", "ADA", "AVAX", "LINK")]
for s in targets[:12]:
    f = {x.get("filterType"): x for x in s.get("filters", [])}
    lot = f.get("LOT_SIZE", {})
    notional = f.get("NOTIONAL", {})
    sym = s["symbol"]
    try:
        with urllib.request.urlopen(
            f"https://api.binance.me/api/v3/ticker/price?symbol={sym.replace('_','')}", timeout=10
        ) as r:
            px = float(json.loads(r.read().decode()).get("price", 0))
    except Exception:
        px = 0
    min_qty = float(lot.get("minQty", 0) or 0)
    min_not = float(notional.get("minNotional", 0) or 0)
    min_cost = max(min_qty * px, min_not) if px else min_not
    print(f"{sym:10s} fiyat={px:>12.4f}  minQty={min_qty:<10.4f}  minNotional={min_not:<6.0f}  en_kucuk_maliyet={min_cost:>8.2f} TRY")
