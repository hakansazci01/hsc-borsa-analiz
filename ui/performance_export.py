"""
PERFORMANS PANOSU DIŞA AKTARMA — her Pazar 23:00, haftalık özeti CSV'ye ekle.

10 sütun: Hafta, Toplam İşlem, Kazanan, Kaybeden, Kazanma Oranı %, Toplam K/Z TL,
En Büyük Kar, En Büyük Zarar, Maksimum Drawdown, Başlangıç Bakiye, Bitiş Bakiye.

Eski haftalar SİLİNMEZ — dosya üzerine eklenerek büyür. Stratejiye dokunmaz.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from ui import autonomous_ops, tr_monitor, tr_scalper as t

CSV_FILE = t.ROOT / "performance_summary.csv"
STATE = t.ROOT / "users" / "last_performance_export.json"
COLUMNS = [
    "Hafta", "Toplam İşlem", "Kazanan İşlem", "Kaybeden İşlem", "Kazanma Oranı %",
    "Toplam Kar/Zarar TL", "En Büyük Kar", "En Büyük Zarar",
    "Maksimum Drawdown", "Başlangıç Bakiye", "Bitiş Bakiye",
]


def _week_rows() -> list[dict[str, Any]]:
    since = datetime.now() - timedelta(days=7)
    out = []
    for h in tr_monitor.merged_history():
        try:
            d = datetime.strptime(str(h.get("exit_time", ""))[:10], "%Y-%m-%d")
        except Exception:
            continue
        if d >= since:
            out.append(h)
    return out


def build() -> dict[str, Any]:
    rows = _week_rows()
    pnls = [float(h.get("net_pnl", h.get("pnl", 0))) for h in rows]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    eq = np.cumprod([1 + p / 100 for p in pnls]) if pnls else np.array([1.0])
    mdd = round(float((eq / np.maximum.accumulate(eq) - 1).min()) * 100, 2)
    bal = t.available_try()
    return {
        "Hafta": datetime.now().strftime("%Y-W%V"),
        "Toplam İşlem": len(rows),
        "Kazanan İşlem": len(wins),
        "Kaybeden İşlem": len(losses),
        "Kazanma Oranı %": round(len(wins) / len(rows) * 100, 2) if rows else 0.0,
        "Toplam Kar/Zarar TL": round(sum(pnls), 2),
        "En Büyük Kar": round(max(wins), 2) if wins else 0.0,
        "En Büyük Zarar": round(min(losses), 2) if losses else 0.0,
        "Maksimum Drawdown": mdd,
        "Başlangıç Bakiye": round(bal - sum(pnls), 2),
        "Bitiş Bakiye": round(bal, 2),
    }


def export() -> dict[str, Any]:
    r = build()
    exists = CSV_FILE.exists()
    with CSV_FILE.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if not exists:
            w.writeheader()
        # aynı hafta varsa tekrar yazma
        existing = set()
        if exists:
            try:
                with CSV_FILE.open(encoding="utf-8-sig") as rf:
                    existing = {row.get("Hafta") for row in csv.DictReader(rf)}
            except Exception:
                pass
        if r["Hafta"] not in existing:
            w.writerow(r)
    STATE.write_text(json.dumps({**r, "exported_at": time.strftime("%Y-%m-%d %H:%M")},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    autonomous_ops._log(f"PERFORMANS DIŞA AKTARMA: {r['Hafta']} → {CSV_FILE.name}")
    return r


def rows() -> list[dict[str, Any]]:
    if not CSV_FILE.exists():
        return []
    with CSV_FILE.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def last() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return {"week": d.get("Hafta", "—"), "at": d.get("exported_at", "—")}
    except Exception:
        return {"week": "—", "at": "—"}
