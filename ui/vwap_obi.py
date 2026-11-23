"""VWAP RECLAIM + OBI — BB/RSI'YA EK sinyal (yerine geçmez).

VWAP: gün başı 00:00 UTC sıfırlanır. Fiyat VWAP altındayken izlenir;
VWAP'ı yukarı kırıp 1 dk üstünde kapatırsa LONG adayı.
OBI: ilk 5 kademe (Bid-Ask)/(Bid+Ask). > +0.50 onay, < 0 spoofing → girme.
OBI sinyali en fazla 15 sn geçerli. Sığ tahta (BTC/ETH dışı) kullanılmaz.
"""

from __future__ import annotations

import datetime as _dt
import time
from typing import Any

DEEP_BOOKS = ("BTC_TRY", "ETH_TRY")
OBI_MIN = 0.50
SIGNAL_TTL_SEC = 15.0
ABOVE_SEC = 60.0


def is_deep(symbol: str) -> bool:
    return str(symbol).upper() in DEEP_BOOKS


def session_vwap(klines: list[list[Any]]) -> dict[str, Any]:
    """00:00 UTC'den bu yana 1dk mumlardan hacim ağırlıklı ortalama."""
    now = _dt.datetime.now(_dt.timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start.timestamp() * 1000)
    num = den = 0.0
    used = 0
    for k in klines or []:
        try:
            ts = int(k[0])
            if ts < start_ms:
                continue
            h, l, c, v = float(k[2]), float(k[3]), float(k[4]), float(k[5])
            typical = (h + l + c) / 3.0
            num += typical * v
            den += v
            used += 1
        except (TypeError, ValueError, IndexError):
            continue
    if den <= 0:
        return {"ok": False, "vwap": 0.0, "bars": used,
                "reason": "VWAP hesaplanamadı (yeni gün verisi yok)"}
    return {"ok": True, "vwap": round(num / den, 8), "bars": used,
            "session_start": start.strftime("%Y-%m-%d %H:%M UTC")}


def obi_formula(bids: list[list[Any]], asks: list[list[Any]]) -> dict[str, Any]:
    """(Bid-Ask)/(Bid+Ask) — ilk 5 kademe."""
    try:
        bid = sum(float(x[1]) for x in (bids or [])[:5])
        ask = sum(float(x[1]) for x in (asks or [])[:5])
    except (TypeError, ValueError, IndexError):
        return {"ok": False, "value": 0.0, "reason": "depth okunamadı"}
    total = bid + ask
    if total <= 0:
        return {"ok": False, "value": 0.0, "reason": "depth boş"}
    value = round((bid - ask) / total, 4)
    return {"ok": value >= OBI_MIN, "value": value,
            "reason": f"OBI {value:+.3f} {'≥' if value >= OBI_MIN else '<'} +0.50"}


def reclaim_check(symbol: str, price: float, vwap: float, prev_price: float,
                  obi: dict[str, Any], signal_age_sec: float,
                  above_sec: float, fresh_limit: float | None = None) -> tuple[bool, str]:
    """Tüm koşullar birlikte tutarsa LONG adayı.

    fresh_limit verilirse (mikro sistemde 2 sn) depth5 sunucu zamanı `T` ile
    ölçülen sinyal yaşı bu sınırı aşarsa giriş reddedilir.
    """
    checks = {
        "derin tahta": is_deep(symbol),
        "VWAP altındaydı": float(prev_price) <= float(vwap),
        "VWAP üstü kapanış": float(price) > float(vwap),
        "1 dk üstünde": float(above_sec) >= ABOVE_SEC,
        "OBI > +0.50": bool(obi.get("ok")),
        "OBI ≥ 0 (spoofing yok)": float(obi.get("value", 0)) >= 0,
        "sinyal ≤ 15 sn": float(signal_age_sec) <= SIGNAL_TTL_SEC,
    }
    if fresh_limit is not None:
        checks[f"depth tazeliği ≤ {fresh_limit:g} sn"] = float(signal_age_sec) <= float(fresh_limit)
    bad = [k for k, ok in checks.items() if not ok]
    detail = " · ".join(f"{k} {'OK' if ok else 'X'}" for k, ok in checks.items())
    return (not bad), detail
