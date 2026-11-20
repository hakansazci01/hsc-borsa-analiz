import ssl
import urllib.request

URLS = [
    "https://www.binance.tr/open/v1/time",
    "https://api.binance.com/api/v3/ping",
    "https://api.binance.me/api/v3/ping",
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

for url in URLS:
    for label, ctx in (
        ("default", ssl.create_default_context()),
        ("tls12", ssl._create_unverified_context()),
    ):
        if label == "tls12":
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
                body = resp.read(200).decode(errors="replace")
                print(f"{url} [{label}] -> {resp.status} {body[:80]}")
        except Exception as exc:
            print(f"{url} [{label}] -> {type(exc).__name__}: {str(exc)[:90]}")
