"""
GERÇEK PARA emir yürütücüsü (varsayılan tamamen kapalı).

Bu modül otomatik emir döngüsü DEĞİLDİR: yalnızca kullanıcının açıkça
onayladığı tek bir sinyali, tüm kilitler geçtiğinde broker'a iletir.
Başarısızlık/kilit durumunda hiçbir ağ çağrısı yapmaz.
"""

from __future__ import annotations

from typing import Any

from ui import audit_log, auth, broker, live_guard, log_store
from ui.help_texts import h  # noqa: F401  (tooltip anahtarları için)


def _orders_path(username: str):
    return auth.user_dir(username) / live_guard.ORDERS_FILE


def _idempotency_key(username: str, symbol: str, side: str, qty: float, price: float) -> str:
    bucket = auth._now()[:10]  # dd.mm.YYYY
    return f"live|{username}|{symbol.upper()}|{side}|{qty}|{round(float(price), 2)}|{bucket}"


def execute(
    username: str,
    symbol: str,
    decision: str,
    qty: float,
    price: float,
    phrase: str = "",
    session_armed: bool = False,
    gate_level: str = "ok",
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tek seferlik, idempotent gerçek emir dener. Kilitler açık değilse göndermez."""
    decision = str(decision).upper()
    if decision not in ("AL", "SAT"):
        return {"ok": False, "reason": "Yönlü sinyal yok (AL/SAT gerekli); emir gönderilmedi."}
    if gate_level == "fail":
        return {"ok": False, "reason": "Veri kapısı sinyali bastırdı; emir gönderilmedi."}

    side = "buy" if decision == "AL" else "sell"
    ok, reasons, cfg = live_guard.check(
        username, symbol, qty, price, phrase=phrase,
        session_armed=session_armed, settings=settings,
    )
    if not ok:
        audit_log.append(username, "GERCEK_EMIR_ENGELLENDI", {
            "symbol": symbol, "decision": decision, "gate": "locked",
            "source": "canli emir kilidi",
            "idempotency_key": f"liveblock|{symbol}|{decision}|{auth._now()[:16]}",
        })
        return {"ok": False, "reason": "Emir gönderilmedi: " + "; ".join(reasons)}

    key = _idempotency_key(username, symbol, side, qty, price)
    for row in log_store.read(_orders_path(username), 500):
        if str(row.get("idempotency_key")) == key:
            return {"ok": False, "reason": "Bu emir zaten kayıtlı (tekrar gönderilmedi).", "existing": row}

    result = broker.place_live_order(
        symbol, qty, side=side, client_order_id=key[:48], limit_price=None
    )
    entry = {
        "time": auth._now(),
        "symbol": symbol.upper(),
        "decision": decision,
        "side": side,
        "qty": qty,
        "price": price,
        "ok": bool(result.get("ok")),
        "broker_id": result.get("id"),
        "status": result.get("status"),
        "reason": result.get("reason"),
        "source": "gercek emir",
        "idempotency_key": key,
    }
    log_store.append(_orders_path(username), entry)
    audit_log.append(username, "GERCEK_EMIR_DENEMESI", {
        "symbol": symbol, "decision": decision,
        "gate": "ok" if result.get("ok") else "hata",
        "source": "canli broker",
        "idempotency_key": key + "|audit",
    })
    return result


def recent_orders(username: str, limit: int = 20) -> list[dict[str, Any]]:
    return log_store.read(_orders_path(username), limit)
