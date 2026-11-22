"""OFI / L2 DEPTH KORUMASI — sadece alımı engelleyen fren, alımı zorlamaz.

Kurallar:
  - bid/ask dengesizliği: bid toplamı > %70 ise "sahte alım baskısı" → toxic
  - spread > %0.5 ise → toxic
  - veri alınamazsa → temiz (fail-open) ama nedeni loglanır
"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any

BASE = "https://api.binance.me/api/v1/depth"
_cache: dict[str, Any] = {"at": 0.0, "result": None}


def check(symbol: str) -> dict[str, Any]:
    plain = symbol.replace("_", "")
    now = time.time()
    if _cache.get("result") and _cache.get("symbol") == plain and now - _cache["at"] < 20:
        return _cache["result"]

    reason = ""
    bid_pct = 50.0
    spread_pct = 0.0
    try:
        with urllib.request.urlopen(f"{BASE}?symbol={plain}&limit=20", timeout=8) as r:
            data = json.loads(r.read().decode())
        bids = data.get("bids") or []
        asks = data.get("asks") or []
        if not bids or not asks:
            raise ValueError("boş order book")
        bid_sum = sum(float(x[1]) for x in bids)
        ask_sum = sum(float(x[1]) for x in asks)
        total = bid_sum + ask_sum
        bid_pct = round(bid_sum / total * 100, 1) if total else 50.0
        best_bid, best_ask = float(bids[0][0]), float(asks[0][0])
        mid = (best_bid + best_ask) / 2
        spread_pct = round((best_ask - best_bid) / mid * 100, 4) if mid else 0.0
        if bid_pct > 70.0:
            reason = f"bid %{bid_pct:.1f} > %70 — sahte alım baskısı"
        elif spread_pct > 0.5:
            reason = f"spread %{spread_pct:.2f} > %0,5"
    except Exception as exc:
        reason = f"L2 veri alınamadı ({type(exc).__name__}) — fail-open"

    result = {
        "ok": not reason or "veri alınamadı" in reason,
        "state": "Temiz" if (not reason or "veri alınamadı" in reason) else "Toxic",
        "bid_pct": bid_pct,
        "spread_pct": spread_pct,
        "reason": reason,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _cache.update(symbol=plain, at=now, result=result)
    return result
