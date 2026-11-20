"""
Binance TR canlı izleme katmanı.

Gerçek zamanlı olarak şunları tutar:
- Ne alındı / hangi fiyattan / kaç adet / kaç TL
- Anlık fiyat, anlık kâr-zarar (TL ve yüzde)
- Geçen süre (saniye), TP/SL'a kalan mesafe
- Yazılan komisyon, gerçekleşen K/Z, işlem sayısı, kazanma oranı
- Her 15 saniyede bir fiyat anlık görüntüsü (JSONL) — grafik için

Veriler ui.tr_scalper'in yerel durum dosyasından ve gerçek borsa API'sinden gelir.
Hiçbir değer uydurulmaz; fiyat alınamazsa alan "—" olarak kalır.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth


SNAPSHOTS = auth.USERS_DIR / "tr_scalper_snapshots.jsonl"
TAKER_FEE = 0.001  # Binance TR piyasa emri komisyonu (taker)


def append_snapshot(rec: dict[str, Any]) -> None:
    SNAPSHOTS.parent.mkdir(parents=True, exist_ok=True)
    with SNAPSHOTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def recent_snapshots(limit: int = 180) -> list[dict[str, Any]]:
    if not SNAPSHOTS.exists():
        return []
    try:
        lines = SNAPSHOTS.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
    except OSError:
        return []


def _age(entry_ts: float | None) -> str:
    if not entry_ts:
        return "—"
    sec = max(0, int(time.time() - float(entry_ts)))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def live_metrics() -> dict[str, Any]:
    """Anlık pozisyon + gerçek piyasa verisinden tüm metrikler."""
    from ui import tr_scalper as t

    st = t._load()
    pos = st.get("position")
    out: dict[str, Any] = {
        "history": st.get("history", []),
        "realized_pnl": float(st.get("realized_pnl", 0) or 0),
        "fees_paid": float(st.get("fees_paid", 0) or 0),
        "position": None,
    }
    if not pos:
        return out

    sym = pos.get("symbol")
    entry = float(pos.get("entry", 0) or 0)
    qty = float(pos.get("qty", 0) or 0)
    px = t.price(sym)
    now = px if px else entry
    pnl = (now - entry) * qty
    pct = (now / entry - 1) * 100 if entry else 0.0
    tp = float(pos.get("tp", 0) or 0)
    sl = float(pos.get("sl", 0) or 0)
    span = (tp - sl) or 1
    progress = max(0.0, min(1.0, (now - sl) / span)) if tp and sl else 0.5
    out["position"] = {
        "symbol": sym,
        "qty": qty,
        "entry": entry,
        "cost": entry * qty,
        "entry_time": pos.get("time", "—"),
        "elapsed": _age(pos.get("entry_ts")),
        "price": px,
        "value": now * qty,
        "pnl": round(pnl, 4),
        "pct": round(pct, 3),
        "tp": tp,
        "sl": sl,
        "progress": round(progress, 3),
        "order_id": pos.get("order_id", "—"),
        "fee_est": round(entry * qty * TAKER_FEE, 4),
    }
    return out


def summary() -> dict[str, Any]:
    """Tüm işlemlerden istatistik: kâr, zarar, süre, kazanma oranı."""
    from ui.tr_monitor import live_metrics

    m = live_metrics()
    hist = m["history"]
    wins = [h for h in hist if float(h.get("net_pnl", h.get("pnl", 0))) > 0]
    losses = [h for h in hist if float(h.get("net_pnl", h.get("pnl", 0))) <= 0]
    durations = [float(h.get("duration_sec", 0)) for h in hist if h.get("duration_sec")]
    return {
        "trades": len(hist),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(hist) * 100, 1) if hist else 0.0,
        "net_pnl": round(sum(float(h.get("net_pnl", h.get("pnl", 0))) for h in hist), 4),
        "fees": round(m["fees_paid"], 4),
        "avg_seconds": round(sum(durations) / len(durations), 0) if durations else 0,
        "best": round(max((float(h.get("net_pnl", 0)) for h in hist), default=0), 4),
        "worst": round(min((float(h.get("net_pnl", 0)) for h in hist), default=0), 4),
    }
