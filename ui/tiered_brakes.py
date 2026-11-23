"""KADEMELİ FREN — %10'u bekleme, erken yavaşla.

Kademe 1: 3 ardışık zarar VEYA günlük %3 drawdown → boyut %50 (5→2.5).
          1 kazanan işlemden sonra normale dön.
Kademe 2: günlük %6 drawdown → bugün dur.
Kademe 3: günlük %10 → risk_brakes zaten durduruyor.
İşlem başına risk %0.5 (5000 TL'de 25 TL). Kelly sadece TAVAN kontrolü.
"""

from __future__ import annotations

from typing import Any

from ui import auth

STATE = auth.USERS_DIR / "tiered_brakes.json"
TIER1_LOSS_STREAK = 3
TIER1_DD_PCT = 3.0
TIER2_DD_PCT = 6.0
TIER3_DD_PCT = 10.0
RISK_PER_TRADE_PCT = 0.5
KELLY_CAP_PCT = 7.0


def _load() -> dict[str, Any]:
    import json
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    import json
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def record_trade(net: float) -> dict[str, Any]:
    """Her kapanışta seri/zarar sayacını güncelle."""
    st = _load()
    st["loss_streak"] = (int(st.get("loss_streak", 0)) + 1) if float(net) <= 0 else 0
    st["last_net"] = round(float(net), 4)
    _save(st)
    return st


def status(day_dd_pct: float = 0.0) -> dict[str, Any]:
    st = _load()
    streak = int(st.get("loss_streak", 0) or 0)
    dd = abs(float(day_dd_pct))
    if dd >= TIER3_DD_PCT:
        tier, msg = 3, "Kademe 3: %10 — sistem zaten durdu"
    elif dd >= TIER2_DD_PCT:
        tier, msg = 2, f"Kademe 2: günlük %{dd:.1f} — bugün dur"
    elif dd >= TIER1_DD_PCT or streak >= TIER1_LOSS_STREAK:
        reason = (f"%{dd:.1f} drawdown" if dd >= TIER1_DD_PCT
                  else f"{streak} ardışık zarar")
        tier, msg = 1, f"Kademe 1: {reason} — boyut %50"
    else:
        tier, msg = 0, "Normal"
    return {"tier": tier, "msg": msg, "loss_streak": streak,
            "day_dd_pct": round(dd, 2),
            "size_multiplier": 0.5 if tier == 1 else 1.0,
            "trade_allowed": tier < 2}


def position_cap(balance: float, day_dd_pct: float = 0.0,
                 score_pct: float = 0.05) -> float:
    """Skor boyutu × kademe çarpanı, üst limit %7, işlem riski %0.5."""
    s = status(day_dd_pct)
    if not s["trade_allowed"]:
        return 0.0
    bal = max(0.0, float(balance))
    cap = bal * float(score_pct) * s["size_multiplier"]
    cap = min(cap, bal * KELLY_CAP_PCT / 100.0)
    per_trade = bal * RISK_PER_TRADE_PCT / 100.0
    return round(min(cap, max(per_trade * 10.0, 0.0)), 4)
