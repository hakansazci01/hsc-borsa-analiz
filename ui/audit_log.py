"""
HSC denetim kaydı — eklemeli, idempotent karar günlüğü.

Stripe'in canonical log line ve finansal denetim izleri yaklaşımından esinlenir:
her karar/yanıt, hangi veriyle ve hangi doğrulama sonucuyla üretildiyse
o şekilde saklanır. Kayıtlar yalnızca eklenir (append-only); düzeltme yapılacaksa
yeni bir olay yazılır. Streamlit yeniden çalıştırmalarında aynı olay iki kez
yazılmaz (idempotency key).

Gerçek emir veya kişisel veri gönderimi yoktur; tüm kayıtlar yereldir.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from ui import auth, log_store


AUDIT_FILE = "hsc_audit.jsonl"
_MAX_DEDUPE_LINES = 400


def _path(username: str):
    return auth.user_dir(username) / AUDIT_FILE


def append(username: str, event_type: str, payload: dict[str, Any]) -> bool:
    """Olayı ekler. Aynı anahtarlı olay zaten varsa tekrar yazmaz."""
    key = str(payload.get("idempotency_key") or "")
    path = _path(username)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_keys: set[str] = set()
    for row in log_store.read(path, _MAX_DEDUPE_LINES):
        if row.get("idempotency_key"):
            existing_keys.add(str(row["idempotency_key"]))
    if key and key in existing_keys:
        return False

    record = {
        "time": auth._now(),
        "type": str(event_type),
        **payload,
        "idempotency_key": key,
    }
    log_store.append(path, record)
    return True


def recent(username: str, limit: int = 40) -> list[dict[str, Any]]:
    path = _path(username)
    if not path.exists():
        return []
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, ValueError):
        return []
    return rows[-limit:]


def render_panel(username: str, limit: int = 20) -> None:
    """Son kararları kullanıcıya şeffaf biçimde gösterir."""
    with st.expander(
        "Karar denetim kaydı — hangi veriyle hangi karar?",
        icon=":material/history:",
    ):
        rows = recent(username, limit)
        if not rows:
            st.caption("Henüz kayıt yok. İlk analizden sonra burada görünecek.")
            return
        table = pd.DataFrame([
            {
                "Zaman": r.get("time", ""),
                "Olay": r.get("type", ""),
                "Sembol": r.get("symbol", "—"),
                "Karar": r.get("decision", "—"),
                "Doğrulama": r.get("gate", "—"),
                "Kaynak": r.get("source", "—"),
            }
            for r in reversed(rows)
        ])
        st.dataframe(
            table, hide_index=True, use_container_width=True,
            alt="Son kararların denetim kaydı: zaman, olay türü, sembol, karar, doğrulama seviyesi ve veri kaynağı.",
        )
        st.caption(
            "Kayıtlar yerel ve eklemelidir (append-only). Aynı veriyle aynı karar "
            "yeniden yazılmaz; geçmiş değiştirilmez. Bu bir performans iddiası değil, "
            "şeffaflık kaydıdır."
        )
