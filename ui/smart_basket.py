"""
AKILLI SEPET + FUNDING RATE — 8 coin'i tarar, en yüksek skorlu olanı seçer.

Skor (0-100):
  +40  rejim BOĞA (AYI = -40, YATAY = +10)
  +25  multi-timeframe onayı (günlük + 4s)
  +20  order book alış baskısı (buy * 20)
  +15  16-check gate geçti

Kurallar:
  - En yüksek skorlu coin'e alım; diğerlerine yapma.
  - Aynı anda en fazla 2 pozisyon; 3. coin'e girme.
  - Her pozisyon ayrı ayrı %10; toplam %20'yi geçmesin.
  - Funding rate yüksekse coin'i ele (Binance TR spot'ta veri yok -> N/A, atlanır).

Funding Rate: Binance TR spot API'sinde funding endpoint'i BULUNMUYOR (404 / dokümanda yok).
Sahte veri üretilmez; "N/A (spot)" döner ve filtre uygulanmaz.
"""

from __future__ import annotations

from typing import Any

from ui import (check_gate, correlation_guard, live_feed, market_regime,
                risk_brakes, tr_scalper as t)

MAX_POSITIONS = 2
FUNDING_LIMIT = 0.01  # %1 üzeri funding -> ele (gelecek futures için)


def funding_rate(symbol: str) -> dict[str, Any]:
    """Binance TR spot: funding rate yok — N/A döner, uydurulmaz."""
    for path in ("/open/v1/market/funding-rate", "/open/v1/funding-rate"):
        ok, data = t._request(path, {"symbol": symbol})
        if ok and isinstance(data, dict) and data.get("code") in (0, None):
            v = (data.get("data") or {}).get("fundingRate")
            if v is not None:
                return {"rate": round(float(v) * 100, 4), "available": True, "source": path}
    return {"rate": None, "available": False, "source": "N/A (spot)"}


def score(symbol: str) -> dict[str, Any]:
    """Tek coin için skor hesapla (gerçek verilerden)."""
    reg = market_regime.regime(symbol)
    mtf = market_regime.mtf_confirm(symbol)
    lf = live_feed.book_pressure()
    gate = check_gate.run(symbol, price=t.price(symbol))

    reg_pts = 40 if reg["bull"] else (-40 if reg["bear"] else 10)
    mtf_pts = 25 if mtf["ok"] else 0
    book_pts = round(lf["buy"] * 20) if lf["ok"] else 10
    gate_pts = 15 if gate["ok"] else 0
    total = reg_pts + mtf_pts + book_pts + gate_pts

    fr = funding_rate(symbol)
    funding_skip = bool(fr["available"] and fr["rate"] is not None
                        and fr["rate"] > FUNDING_LIMIT * 100)
    if funding_skip:
        total -= 30

    return {
        "symbol": symbol, "score": total,
        "regime": reg["name"], "regime_pts": reg_pts,
        "mtf_ok": mtf["ok"], "mtf_pts": mtf_pts,
        "book_buy": round(lf["buy"] * 100, 1), "book_pts": book_pts,
        "gate_ok": gate["ok"], "gate_pts": gate_pts,
        "funding": fr["rate"], "funding_skip": funding_skip,
        "reason": gate["summary"],
    }


def rank(symbols: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """8 coin'i skora göre sırala (en yüksek ilk)."""
    syms = symbols or t.SYMBOLS
    rows = [score(s) for s in syms]
    return sorted(rows, key=lambda r: r["score"], reverse=True)


def can_open(balance: float, open_count: int) -> tuple[bool, str]:
    """En fazla 2 pozisyon, toplam %20 limit."""
    if open_count >= MAX_POSITIONS:
        return False, f"MAKSİMUM {MAX_POSITIONS} POZİSYON — 3. coin'e girilmez"
    per = balance * 0.10
    if per * MAX_POSITIONS > balance * 0.20 + 0.01:
        return False, "toplam %20 limiti aşılır"
    return True, ""


def select() -> dict[str, Any]:
    """En iyi coin'i seç (funding skip olanları ele)."""
    rows = rank()
    eligible = [r for r in rows if not r["funding_skip"]]
    best = eligible[0] if eligible else rows[0]
    return {"selected": best["symbol"], "score": best["score"],
            "ranking": rows, "funding": best["funding"]}
