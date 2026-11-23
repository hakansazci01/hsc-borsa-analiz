"""İki motor çakışmaz: aynı coin'de aynı anda ters işlem yok.

AMM (BTC/ETH, 5 sn) ve YÖNLÜ (Top-10, 60 sn) aynı sembolü aynı anda
işgal edemez. İlk gelen kazanır; diğeri logda 'çakışma engeli' görür.
"""

from __future__ import annotations

import json
import time
from typing import Any

from ui import auth

STATE = auth.USERS_DIR / "motor_guard.json"


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def claim(symbol: str, motor: str, ttl_sec: float = 900.0) -> None:
    st = _load()
    active = st.get("active", {}) if isinstance(st.get("active"), dict) else {}
    active[symbol] = {"motor": motor, "at": time.time(), "ttl": ttl_sec}
    st["active"] = active
    _save(st)


def release(symbol: str, motor: str) -> None:
    st = _load()
    active = st.get("active", {}) if isinstance(st.get("active"), dict) else {}
    if active.get(symbol, {}).get("motor") == motor:
        active.pop(symbol, None)
    st["active"] = active
    _save(st)


def conflict(symbol: str, motor: str) -> str | None:
    st = _load()
    active = st.get("active", {}) if isinstance(st.get("active"), dict) else {}
    e = active.get(symbol)
    if not e:
        return None
    if e.get("motor") == motor:
        return None
    if time.time() - float(e.get("at", 0)) > float(e.get("ttl", 900)):
        release(symbol, str(e.get("motor", "")))
        return None
    return f"{symbol} → {e.get('motor')} motorunda ({int(time.time()-float(e.get('at',0)))} sn)"


def active() -> dict[str, Any]:
    return _load().get("active", {}) or {}
