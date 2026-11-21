"""
AYLIK BACKTEST — her ayın 1'i 00:00'da son 90 günün gerçek verisiyle test.

Metrikler: Toplam K/Z, Kazanma Oranı (%), Maksimum Drawdown (%).
Uyarı: win rate <%40 VEYA max drawdown >%20 -> ntfy bildirimi.
Sonuç: monthly_backtest.csv + panel.
Limitler değişmez. Sahte veri YOK.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from ui import autonomous_ops, quant_lab, tr_scalper as t

RESULT_FILE = t.ROOT / "monthly_backtest.csv"
STATE = t.ROOT / "users" / "last_backtest.json"
WIN_WARN = 40.0
DD_WARN = 20.0
DAYS = 90


SLIPPAGE = 0.005  # %0,5 — alımda üstten, satımda alttan
POSITION_TRY = 50.63


def _collect(slippage: float, days: int) -> tuple[list[float], int]:
    rets: list[float] = []
    for sym in t.SYMBOLS:
        frame = quant_lab.fetch(sym, "1d", days + 60)
        if frame is None or len(frame) < 60:
            continue
        frame = frame.tail(days)
        trades = quant_lab.backtest(frame, "pullback", (50,), maxhold=90,
                                    slippage=slippage)
        rets.extend(float(x["ret"]) for x in trades)
    return rets, len(rets)


def run(days: int = DAYS) -> dict[str, Any]:
    """Son 90 gün — slippage'siz VE slippage'li sonuç yan yana."""
    rets, n = _collect(0.0, days)
    slip_rets, _ = _collect(SLIPPAGE, days)

    if not rets:
        result = {"at": time.strftime("%Y-%m-%d"), "trades": 0, "net_pnl": 0.0,
                  "net_pnl_slip": 0.0, "slippage_pct": SLIPPAGE * 100,
                  "win_rate": 0.0, "max_dd": 0.0, "warn": False, "msg": "veri yok"}
        _save(result)
        return result

    wins = sum(1 for r in rets if r > 0)
    win_rate = round(wins / len(rets) * 100, 2)
    eq = np.cumprod([1 + r for r in rets])
    max_dd = round(float((eq / np.maximum.accumulate(eq) - 1).min()) * 100, 2)
    net_pnl = round(float(sum(rets)) * POSITION_TRY, 2)
    net_slip = round(float(sum(slip_rets)) * POSITION_TRY, 2)
    warn = bool(win_rate < WIN_WARN or abs(max_dd) > DD_WARN)
    msg = (f"BACKTEST UYARISI: Kazanma oranı %{win_rate}, Drawdown %{max_dd} "
           f"- Strateji gözden geçirilmeli" if warn
           else f"Backtest OK: Kazanma %{win_rate}, Drawdown %{max_dd}")
    result = {"at": time.strftime("%Y-%m-%d"), "trades": n,
              "net_pnl": net_pnl, "net_pnl_slip": net_slip,
              "slippage_pct": SLIPPAGE * 100,
              "win_rate": win_rate, "max_dd": abs(max_dd),
              "warn": warn, "msg": msg}
    _save(result)
    _write_csv(result)
    if warn:
        autonomous_ops._log(msg)
        autonomous_ops._send("HSC BACKTEST UYARISI", msg)
    else:
        autonomous_ops._log(msg)
    return result


def _save(r: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(r: dict[str, Any]) -> None:
    cols = ["tarih", "islem", "net_pnl", "net_pnl_slip", "slippage_pct",
            "win_rate", "max_dd", "uyari"]
    exists = RESULT_FILE.exists()
    with RESULT_FILE.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        if not exists:
            w.writeheader()
        w.writerow({"tarih": r["at"], "islem": r["trades"], "net_pnl": r["net_pnl"],
                    "net_pnl_slip": r.get("net_pnl_slip", 0),
                    "slippage_pct": r.get("slippage_pct", SLIPPAGE * 100),
                    "win_rate": r["win_rate"], "max_dd": r["max_dd"],
                    "uyari": "EVET" if r["warn"] else "HAYIR"})


def due() -> bool:
    """Her ayın 1'i 00:00."""
    now = datetime.now()
    if now.day != 1 or now.hour != 0:
        return False
    key = now.strftime("%Y-%m")
    try:
        last = json.loads(STATE.read_text(encoding="utf-8")).get("month")
    except Exception:
        last = None
    if last == key:
        return False
    r = run()
    r["month"] = key
    _save(r)
    return True


def next_run() -> str:
    now = datetime.now()
    if now.day == 1 and now.hour == 0:
        return now.strftime("%Y-%m-%d %H:%M")
    if now.month == 12:
        return f"{now.year+1}-01-01 00:00"
    return f"{now.year}-{now.month+1:02d}-01 00:00"


def last() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return {"at": d.get("at", "—"), "net_pnl": float(d.get("net_pnl", 0)),
                "net_pnl_slip": float(d.get("net_pnl_slip", 0)),
                "slippage_pct": float(d.get("slippage_pct", SLIPPAGE * 100)),
                "win_rate": float(d.get("win_rate", 0)), "max_dd": float(d.get("max_dd", 0)),
                "warn": bool(d.get("warn", False))}
    except Exception:
        return {"at": "—", "net_pnl": 0.0, "net_pnl_slip": 0.0,
                "slippage_pct": SLIPPAGE * 100,
                "win_rate": 0.0, "max_dd": 0.0, "warn": False}
