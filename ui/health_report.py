"""
CANLI SAĞLIK RAPORU — her gün 23:00, 7 maddelik tek sayfalık rapor.

1) Bugün kaç işlem  2) Bugün K/Z  3) Açık pozisyon  4) Yedek sayısı/sağlamlık
5) Yeniden başlatma sayısı  6) Rejim  7) Yarın için plan

ntfy + daily_report.txt + panel.
Limitler değişmez.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ui import (autonomous_ops, disaster_recovery, market_regime,
                tr_monitor, tr_scalper as t)

REPORT_FILE = t.ROOT / "daily_report.txt"
STATE = t.ROOT / "users" / "last_health_report.json"
RESTART_LOG = t.ROOT / "users" / "restarts.jsonl"


def count_restarts_today() -> int:
    if not RESTART_LOG.exists():
        return 0
    today = time.strftime("%Y-%m-%d")
    n = 0
    for line in RESTART_LOG.read_text(encoding="utf-8").splitlines():
        if today in line:
            n += 1
    return n


def build() -> dict[str, Any]:
    today = time.strftime("%Y-%m-%d")
    rows = [h for h in tr_monitor.merged_history()
            if str(h.get("exit_time", "")).startswith(today)]
    today_pnl = round(sum(float(h.get("net_pnl", h.get("pnl", 0))) for h in rows), 2)
    pos = t._load().get("position") or {}
    pos_txt = (f"{pos.get('symbol')} · {pos.get('qty')} adet · "
               f"₺{float(pos.get('cost', 0)):.2f}") if pos else "Yok"
    ds = disaster_recovery.status()
    backups = list(disaster_recovery.BACKUPS.glob(f"{time.strftime('%Y%m%d')}_*"))
    reg = market_regime.regime("BTC_TRY")
    plan = ("Rejim AYI, beklemeye devam" if reg["bear"] else
            "Rejim YATAY, Grid modu hazır" if reg["range"] else
            "Rejim BOĞA, EMA50 pullback sinyali kollanacak")
    return {
        "at": time.strftime("%Y-%m-%d %H:%M"),
        "trades": len(rows), "pnl": today_pnl, "position": pos_txt,
        "backups": len(backups), "backup_ok": ds["status"],
        "restarts": count_restarts_today(), "regime": reg["name"], "plan": plan,
    }


def format_report(r: dict[str, Any]) -> str:
    return (
        f"GÜNLÜK SAĞLIK RAPORU — {r['at']}\n"
        f"1) Bugün işlem: {r['trades']}\n"
        f"2) Bugün K/Z: {r['pnl']:+.2f} TL\n"
        f"3) Açık pozisyon: {r['position']}\n"
        f"4) Bugün yedek: {r['backups']} · {r['backup_ok']}\n"
        f"5) Yeniden başlatma: {r['restarts']}\n"
        f"6) Rejim: {r['regime']}\n"
        f"7) Yarın planı: {r['plan']}"
    )


def send() -> dict[str, Any]:
    r = build()
    text = format_report(r)
    ok = autonomous_ops._send("HSC GÜNLÜK SAĞLIK RAPORU", text)
    REPORT_FILE.write_text(text + "\n", encoding="utf-8")
    STATE.write_text(json.dumps({**r, "sent": ok, "sent_at": time.strftime("%Y-%m-%d %H:%M")},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    autonomous_ops._log(f"GÜNLÜK SAĞLIK RAPORU gönderildi ({'OK' if ok else 'hata'})")
    return {**r, "sent": ok, "text": text}


def last() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return {"at": d.get("sent_at", "—"), "sent": bool(d.get("sent"))}
    except Exception:
        return {"at": "—", "sent": False}


def next_run() -> str:
    now = datetime.now()
    d = now if now.hour < 23 else now + timedelta(days=1)
    return d.strftime("%Y-%m-%d") + " 23:00"
