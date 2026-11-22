"""KÂR / ZARAR İSTATİSTİĞİ — trades.csv'den GERÇEK rakam.

Vaat yok: bugün işlem sayısı, kârlı/zararlı, net K/Z, son 7 gün neti,
win rate, ortalama kâr/zarar yüzdesi, en iyi/en kötü coin.
Tüm veri gerçek dolum kayıtlarındandır (komisyon + slippage dahil).
"""

from __future__ import annotations

import csv
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ui import auth

CSV = auth.ROOT / "trades.csv" if hasattr(auth, "ROOT") else Path(__file__).resolve().parent.parent / "trades.csv"


def _rows() -> list[dict[str, Any]]:
    if not CSV.exists():
        return []
    try:
        with CSV.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except Exception:
        return []
    # Slippage kayıtları (sembol '—') işlem değildir
    return [r for r in rows if str(r.get("sembol", "")).strip() not in ("", "—")]


def _money(r: dict[str, Any]) -> float:
    return float(r.get("net_kar_zarar", 0) or 0)


def _pct(r: dict[str, Any]) -> float:
    """İşlem bazında net K/Z yüzdesi (alış maliyeti üzerinden)."""
    try:
        cost = float(r.get("alış_fiyatı", 0) or 0) * float(r.get("adet", 0) or 0)
        return (_money(r) / cost * 100) if cost > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def stats() -> dict[str, Any]:
    rows = _rows()
    today = time.strftime("%Y-%m-%d")
    today_rows = [r for r in rows if str(r.get("tarih", "")).startswith(today)]

    week_ago = datetime.now() - timedelta(days=7)
    week_rows = []
    for r in rows:
        try:
            d = datetime.strptime(str(r.get("tarih", ""))[:10], "%Y-%m-%d")
        except Exception:
            continue
        if d >= week_ago:
            week_rows.append(r)

    pnls = [_money(r) for r in rows]
    wins = [_pct(r) for r in rows if _money(r) > 0]
    losses = [_pct(r) for r in rows if _money(r) < 0]

    by_coin: dict[str, float] = {}
    for r in rows:
        sym = str(r.get("sembol", "—"))
        by_coin[sym] = by_coin.get(sym, 0.0) + _money(r)
    best = max(by_coin.items(), key=lambda x: x[1]) if by_coin else ("—", 0.0)
    worst = min(by_coin.items(), key=lambda x: x[1]) if by_coin else ("—", 0.0)

    return {
        "today_trades": len(today_rows),
        "today_wins": sum(1 for r in today_rows if _money(r) > 0),
        "today_losses": sum(1 for r in today_rows if _money(r) < 0),
        "today_net": round(sum(_money(r) for r in today_rows), 2),
        "week_net": round(sum(_money(r) for r in week_rows), 2),
        "all_trades": len(pnls),
        "win_rate": round(sum(1 for x in pnls if x > 0) / len(pnls) * 100, 1) if pnls else 0.0,
        "avg_win_pct": round(sum(wins) / len(wins), 3) if wins else 0.0,
        "avg_loss_pct": round(sum(losses) / len(losses), 3) if losses else 0.0,
        "best_coin": best[0], "best_coin_net": round(best[1], 2),
        "worst_coin": worst[0], "worst_coin_net": round(worst[1], 2),
    }
