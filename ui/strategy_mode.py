"""Strateji modu seçimi — EMA50 Pullback (mevcut) / SÜREKLİ KÜÇÜK KAR (yeni).

EMA50 kodu silinmez; yeni mod yanına eklenir. Varsayılan EMA50_PULLBACK.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config.yaml"

EMA50 = "EMA50_PULLBACK"
QUICK = "QUICK_PROFIT"
LABELS = {EMA50: "EMA50 Pullback", QUICK: "SÜREKLİ KÜÇÜK KAR"}
VALID = tuple(LABELS)


def _load() -> dict[str, Any]:
    try:
        data = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get() -> str:
    mode = str(_load().get("strategy", {}).get("mode", EMA50)).upper()
    return mode if mode in VALID else EMA50


def label() -> str:
    return LABELS[get()]


def set(mode: str) -> str:
    """Panelden mod değişimi — kalıcıconfig.yaml yazımı."""
    mode = str(mode).upper()
    if mode not in VALID:
        mode = EMA50
    data = _load()
    data.setdefault("strategy", {})["mode"] = mode
    CFG.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    return mode
