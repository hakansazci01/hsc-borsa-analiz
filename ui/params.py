"""
Auto-optimization parametreleri — kalıcı dosya: users/trading_params.json

Sadece 2 parametre değiştirilebilir: ATR çarpanı ve Grid kademe aralığı.
Limitler (dinamik %10, günlük %10, trailing %15) ASLA değiştirilemez.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PARAMS_FILE = ROOT / "users" / "trading_params.json"
HISTORY_FILE = ROOT / "params_history.csv"

DEFAULTS = {
    "atr_mult": 1.5,
    "grid_step_pct": 1.0,
    "corr_limit": 0.85,
}
BOUNDS = {
    "atr_mult": (1.2, 2.0),
    "grid_step_pct": (0.5, 2.0),
}


def load() -> dict[str, Any]:
    try:
        d = json.loads(PARAMS_FILE.read_text(encoding="utf-8"))
        return {**DEFAULTS, **{k: d[k] for k in DEFAULTS if k in d}}
    except Exception:
        return dict(DEFAULTS)


def save(params: dict[str, Any]) -> None:
    PARAMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PARAMS_FILE.write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")


def clamp(name: str, value: float) -> float:
    lo, hi = BOUNDS[name]
    return max(lo, min(hi, float(value)))


def append_history(row: dict[str, Any]) -> None:
    import csv

    cols = ["tarih", "atr_mult", "grid_step_pct", "corr_limit", "sebep"]
    exists = HISTORY_FILE.exists()
    with HISTORY_FILE.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        if not exists:
            w.writeheader()
        w.writerow({c: row.get(c, "") for c in cols})
