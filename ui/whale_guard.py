"""
BALİNA / HABER KORUMASI — son 5 dakikadaki %3+ hareket -> 30 dk alım yasağı.

Hem %3+ düşüş hem %3+ yükseliş şüphelidir (haber/balina veya sahte pump).
14-Check Gate'in 15. kontrolü olarak çalışır.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth, autonomous_ops, tr_scalper as t

MOVE_LIMIT = 0.03          # %3
COOLDOWN_SEC = 1800        # 30 dakika
WINDOW_MIN = 5
STATE = auth.USERS_DIR / "whale_guard_state.json"


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def move_5m(symbol: str) -> float:
    """Son 5 dakikadaki gerçek fiyat değişimi (1dk mumlardan)."""
    f = t.klines(symbol, "1m", WINDOW_MIN + 2)
    if f is None or len(f) < 3:
        return 0.0
    first = float(f["Close"].iloc[0])
    last = float(f["Close"].iloc[-1])
    if first <= 0:
        return 0.0
    return (last - first) / first


def check(symbol: str) -> dict[str, Any]:
    """Koruma kontrolü. Şüpheli hareket varsa cooldown yazar."""
    st = _load()
    until = float(st.get("until", 0) or 0)
    move = move_5m(symbol)
    now = time.time()
    if now < until:
        return {"blocked": True, "move_pct": round(move * 100, 2),
                "remaining_min": int((until - now) // 60),
                "reason": f"BALİNA / HABER ŞÜPHESİ - 30 DK BEKLEME — "
                          f"{int((until-now)//60)} dk kaldı"}
    if abs(move) > MOVE_LIMIT:
        st["until"] = now + COOLDOWN_SEC
        st["move_pct"] = round(move * 100, 2)
        st["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save(st)
        direction = "düşüş" if move < 0 else "yükseliş"
        msg = (f"BALİNA / HABER ŞÜPHESİ - 30 DK BEKLEME: "
               f"son 5 dk %{move*100:.2f} {direction}")
        autonomous_ops._log(msg)
        autonomous_ops._send("HSC BALİNA KORUMASI", msg)
        return {"blocked": True, "move_pct": round(move * 100, 2),
                "remaining_min": COOLDOWN_SEC // 60, "reason": msg}
    return {"blocked": False, "move_pct": round(move * 100, 2),
            "remaining_min": 0, "reason": ""}


def status() -> dict[str, Any]:
    st = _load()
    until = float(st.get("until", 0) or 0)
    active = time.time() < until
    return {"active": active, "move_pct": float(st.get("move_pct", 0) or 0),
            "remaining_min": max(0, int((until - time.time()) // 60))}
