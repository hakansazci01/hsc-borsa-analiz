"""
AUTO-OPTİMİZASYON — her Pazar 23:00, haftalık rapora göre 2 parametreyi ayarlar.

Kurallar:
  ATR çarpanı (1.2-2.0):
    stop'lar çok erken patladıysa (stop sayısı >= 3) -> +0.3 (1.5 -> 1.8)
    stop hiç patlamadıysa (0) -> -0.3 (1.5 -> 1.2)
    aksi halde sabit kalır.
  Grid aralığı (%0.5-%2.0):
    grid çok sık al-sat yaptıysa (>= 10 kademe) -> +0.5 (1.0 -> 1.5)
    çok az yaptıysa (<= 2 kademe) -> -0.3 (1.0 -> 0.7)
  Korelasyon eşiği: 0.85 SABİT, değiştirilmez (raporda gösterilir).

LIMITLER DEĞİŞMEZ: dinamik %10, günlük %10, trailing %15.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ui import autonomous_ops, params, tr_scalper as t

OPTIMIZE_WEEKDAY = 6  # Pazar (Python: Pazartesi=0)
OPTIMIZE_HOUR = 23
HISTORY_FILE = params.HISTORY_FILE


def _week_trades() -> list[dict[str, Any]]:
    p = t.TRADES_CSV
    rows: list[dict[str, Any]] = []
    if not p.exists():
        return rows
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                d = datetime.strptime(str(r.get("tarih", ""))[:10], "%Y-%m-%d")
            except Exception:
                continue
            if d >= datetime.now() - timedelta(days=7):
                rows.append(r)
    return rows


def optimize() -> dict[str, Any]:
    """Haftalık raporu değerlendir, parametreleri sınırlar içinde güncelle."""
    before = params.load()
    trades = _week_trades()
    stops = sum(1 for r in trades if "stop" in str(r.get("strateji_adı", "")).lower()
                or "ATR" in str(r.get("strateji_adı", "")))
    grid_trades = sum(1 for r in trades if "grid" in str(r.get("strateji_adı", "")).lower())

    new_atr = before["atr_mult"]
    new_grid = before["grid_step_pct"]
    reasons: list[str] = []

    if stops >= 3:
        new_atr = params.clamp("atr_mult", new_atr + 0.3)
        reasons.append(f"stop'lar erken patladı ({stops}) -> ATR artırıldı")
    elif stops == 0 and len(trades) > 0:
        new_atr = params.clamp("atr_mult", new_atr - 0.3)
        reasons.append("stop hiç patlamadı -> ATR azaltıldı")

    if grid_trades >= 10:
        new_grid = params.clamp("grid_step_pct", new_grid + 0.5)
        reasons.append(f"grid çok sık al-sat ({grid_trades}) -> aralık genişletildi")
    elif grid_trades <= 2 and len(trades) > 0:
        new_grid = params.clamp("grid_step_pct", new_grid - 0.3)
        reasons.append(f"grid çok az al-sat ({grid_trades}) -> aralık daraltıldı")

    after = {
        "atr_mult": round(new_atr, 2),
        "grid_step_pct": round(new_grid, 2),
        "corr_limit": 0.85,  # SABİT
    }
    params.save(after)
    params.append_history({
        "tarih": time.strftime("%Y-%m-%d %H:%M:%S"),
        "atr_mult": after["atr_mult"], "grid_step_pct": after["grid_step_pct"],
        "corr_limit": after["corr_limit"], "sebep": ", ".join(reasons) or "değişiklik yok",
    })

    changed = []
    if before["atr_mult"] != after["atr_mult"]:
        changed.append(f"ATR {before['atr_mult']} -> {after['atr_mult']}")
    if before["grid_step_pct"] != after["grid_step_pct"]:
        changed.append(f"Grid %{before['grid_step_pct']} -> %{after['grid_step_pct']}")
    if changed:
        msg = "PARAMETRE GÜNCELLENDİ: " + ", ".join(changed)
    else:
        msg = "PARAMETRELER DEĞİŞMEDİ"
    msg += f" · Korelasyon eşiği 0.85 (sabit)"
    autonomous_ops._send("HSC OPTİMİZASYON", msg)
    autonomous_ops._log("OPTİMİZASYON: " + msg)

    return {"before": before, "after": after, "changed": changed, "msg": msg,
            "trades": len(trades), "stops": stops, "grid_trades": grid_trades,
            "at": time.strftime("%Y-%m-%d"), "reasons": reasons}


def due() -> bool:
    """Pazar 23:00 — haftada bir."""
    now = datetime.now()
    if now.weekday() != OPTIMIZE_WEEKDAY or now.hour != OPTIMIZE_HOUR:
        return False
    state_file = Path(t.ROOT) / "users" / "last_optimize.json"
    try:
        last = json.loads(state_file.read_text(encoding="utf-8")).get("at")
    except Exception:
        last = None
    if last == now.strftime("%Y-%m-%d"):
        return False
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"at": now.strftime("%Y-%m-%d")}), encoding="utf-8")
    return True


def next_run() -> str:
    now = datetime.now()
    days = (OPTIMIZE_WEEKDAY - now.weekday()) % 7
    if days == 0 and now.hour >= OPTIMIZE_HOUR:
        days = 7
    d = now + timedelta(days=days)
    return d.replace(hour=OPTIMIZE_HOUR, minute=0, second=0).strftime("%Y-%m-%d %H:%M")


def last_run() -> dict[str, Any]:
    state_file = Path(t.ROOT) / "users" / "last_optimize.json"
    try:
        d = json.loads(state_file.read_text(encoding="utf-8"))
        p = params.load()
        return {"at": d.get("at", "—"), "atr": p["atr_mult"],
                "grid": p["grid_step_pct"], "corr": p["corr_limit"]}
    except Exception:
        p = params.load()
        return {"at": "—", "atr": p["atr_mult"], "grid": p["grid_step_pct"],
                "corr": p["corr_limit"]}
