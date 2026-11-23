"""GERÇEK TP KANITI KİLİDİ — ilk gerçek TP satışına kadar yeni pozisyon yok.

Geçici güvenlik kilidi: açık pozisyon varken ve henüz gerçek bir TP satışı
olmadıysa _scan_new() yeni pozisyon açmaz, sadece mevcut pozisyonu yönetir.
İlk gerçek TP dolumundan sonra kilit kendiliğinden açılır.
Sadece GERÇEK satışlar sayılır (simülasyonlar state'e yazmaz).
"""

from __future__ import annotations

import json
import time
from typing import Any

from ui import auth

STATE = auth.USERS_DIR / "tp_proof.json"


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def count() -> int:
    return int(_load().get("real_tp_count", 0) or 0)


def unlocked() -> bool:
    return count() >= 1


def record_real_tp(symbol: str, reason: str, net: float, order_id: Any = None) -> int:
    st = _load()
    n = int(st.get("real_tp_count", 0) or 0) + 1
    st.update(real_tp_count=n, last_symbol=symbol, last_reason=reason,
              last_net=round(float(net), 4), last_order_id=order_id,
              unlocked_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    _save(st)
    return n


def status() -> dict[str, Any]:
    st = _load()
    return {"real_tp_count": count(), "unlocked": unlocked(),
            "last_symbol": st.get("last_symbol", "—"),
            "last_reason": st.get("last_reason", "—"),
            "last_net": st.get("last_net", 0),
            "unlocked_at": st.get("unlocked_at", "—")}
