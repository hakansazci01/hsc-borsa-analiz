"""
İşlem Defteri — her tarama turunda ne olduğu, neden işlem açılmadığı,
hangi emrin gönderildiği, gerçek sonuçları yapılandırılmış olarak saklar.

Sahte kayıt yok: her satır gerçek bir döngü/API cevabından üretilir.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth


JOURNAL = auth.USERS_DIR / "tr_decision_journal.jsonl"


def append(events: list[str], position: dict[str, Any] | None,
           kind: str = "tarama") -> None:
    rec = {
        "ts": time.time(),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": kind,
        "events": events,
        "position": (position or {}).get("symbol") if position else None,
        "pnl": (position or {}).get("pnl"),
    }
    try:
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        with JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def recent(limit: int = 60) -> list[dict[str, Any]]:
    if not JOURNAL.exists():
        return []
    try:
        lines = JOURNAL.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
    except OSError:
        return []
