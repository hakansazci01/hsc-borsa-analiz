"""Capraz piyasa arbitraji: TRY paritesi vs (USDT paritesi * USDTRY)."""
import json, urllib.request

def get(url):
    with urllib.request.urlopen(url, timeout=12) as r:
        return json.loads(r.read().decode())

# Binance TR sembol listesinde USDT_TRY var mi?
with urllib.request.urlopen("https://www.binance.tr/open/v1/common/symbols", timeout=15) as r:
    syms = json.loads(r.read().decode()).get("data", {}).get("list", [])
usdtry_pair = [s["symbol"] for s in syms if s["symbol"] in ("USDT_TRY", "TRY_USDT", "USDTTRY")]
print("USDTRY paritesi:", usdtry_pair)

names = [s["symbol"] for s in syms if s["symbol"].endswith("_TRY")][:30]
print("ornek TRY ciftleri:", names[:15])

# USD/TRY icin alternatif kaynaklar
sources = [
    ("binance_tr_usdttry", "https://www.binance.tr/open/v1/ticker/price?symbol=USDT_TRY"),
    ("binance_me_usdttry", "https://api.binance.me/api/v3/ticker/price?symbol=USDTTRY"),
    ("freefeed_usdtry", "https://api.frankfurter.app/latest?from=USD&to=TRY"),
]
rate = None
for name, url in sources:
    try:
        d = get(url)
        print(name, str(d)[:200])
        if name == "freefeed_usdtry" and "rates" in d:
            rate = float(d["rates"]["TRY"])
        elif isinstance(d, dict) and "price" in d:
            rate = float(d["price"])
    except Exception as e:
        print(name, "hata", type(e).__name__)
print("USDTRY:", rate)
