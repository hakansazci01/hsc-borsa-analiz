"""CRASH BID — çöküşte bekleyen limit alım (yeni motor).

1 dk'da %2+ ani düşüş olursa: son kapanışın %2 altına LIMIT alış koy,
fiyatla birlikte kaydır. Dolarsa +%2'de sat, 4 saatte gelmezse marketten çık.
Normal skor tablosunu BYPASS eder, tek seferlik %5-7 pozisyon açar.

Not: 495 gün / 43 işlem / %79 win / +%0.48 net rakamları KAYNAKTAN GELEN
IDDİADIR; bu modül o iddiayı doğrulamaz, sadece kuralı uygular.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth

STATE = auth.USERS_DIR / "crash_bid.json"
DROP_PCT = 2.0
BID_DISCOUNT = 0.02
TARGET_PCT = 0.02
TIMEOUT_SEC = 4 * 3600
SIZE_MIN = 0.05
SIZE_MAX = 0.07


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def detect_drop(prev_close: float, price: float) -> dict[str, Any]:
    """1 dakikada %2+ düşüş var mı?"""
    if prev_close <= 0:
        return {"ok": False, "drop_pct": 0.0, "reason": "önceki kapanış yok"}
    drop = (prev_close - float(price)) / prev_close * 100
    ok = drop >= DROP_PCT
    return {"ok": ok, "drop_pct": round(drop, 3),
            "reason": f"1dk düşüş %{drop:.2f} {'≥' if ok else '<'} %{DROP_PCT:.0f}"}


def plan(last_close: float, step: float = 0.00000001) -> dict[str, Any]:
    """Limit alış planı — fiyat %2 altı, hedef dolumdan +%2."""
    bid = float(last_close) * (1 - BID_DISCOUNT)
    if step > 0:
        bid = round(int(bid / step) * step, 8)
    return {"bid_px": bid, "target_px": round(bid * (1 + TARGET_PCT), 8),
            "expires_at": time.time() + TIMEOUT_SEC,
            "size_pct": SIZE_MIN, "at": time.strftime("%Y-%m-%d %H:%M:%S")}


def slide_bid(last_close: float, step: float = 0.00000001) -> float:
    """Fiyat değiştikçe limit emri kaydır (her dakika yeni kapanış)."""
    return plan(last_close, step)["bid_px"]


def exit_decision(fill_price: float, price: float, filled_at: float,
                  now_ts: float | None = None) -> tuple[str, str]:
    """Dolduktan sonra: +%2 hedef veya 4 saat timeout."""
    now = now_ts if now_ts is not None else time.time()
    fill = float(fill_price)
    if fill <= 0:
        return "HOLD", "dolum fiyatı yok"
    gain = (float(price) - fill) / fill
    if gain >= TARGET_PCT:
        return "SELL", f"CRASH BID hedefi %{gain*100:.2f} ≥ %{TARGET_PCT*100:.0f}"
    if now - float(filled_at) >= TIMEOUT_SEC:
        return "SELL", "CRASH BID 4 saat doldu — marketten çık"
    return "HOLD", f"CRASH BID bekleniyor (%{gain*100:.2f})"


def active() -> dict[str, Any]:
    return _load().get("active") or {}


def start(symbol: str, p: dict[str, Any]) -> None:
    _save({"active": {**p, "symbol": symbol,
                      "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}})


def mark_filled(fill_price: float, qty: float) -> None:
    st = _load()
    a = st.get("active") or {}
    if a:
        a.update(filled=True, fill_price=fill_price, qty=qty,
                 filled_at=time.time())
    st["active"] = a
    _save(st)


def clear() -> None:
    st = _load()
    st["active"] = {}
    _save(st)
