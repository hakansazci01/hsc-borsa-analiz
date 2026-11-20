import json
import urllib.request

for url in (
    "https://api.binance.me/api/v1/klines?symbol=BTCUSDT&interval=15m&limit=3",
    "https://www.binance.tr/open/v1/common/symbols",
    "https://www.binance.tr/open/v1/ticker/price?symbol=BTC_USDT",
):
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            body = r.read(400).decode(errors="replace")
            print(url.split("/")[2], "->", r.status, body[:180])
    except Exception as e:
        print(url.split("/")[2], "->", type(e).__name__, str(e)[:80])
