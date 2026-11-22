"""GÜVENLİK KATMANLARI — strateji değil, sadece fren ve izleme.

1) Stale-data: son tick yaşı >60 sn → ALIM YOK; >120 sn → SATIM da bekletilir.
2) Slippage CUSUM: beklenen %0,05 sapma biriktirilir; >%0,30 uyarı, >%0,50 alım durur.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth

STALE_BUY_SEC = 60
STALE_SELL_SEC = 120
EXPECTED_SLIPPAGE_PCT = 0.05
CUSUM_ALERT = 0.30
CUSUM_HALT = 0.50
STATE = auth.USERS_DIR / "safety_guards.json"


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------- 1) STALE DATA
def tick_age() -> int:
    """WS ve REST kaynaklarından EN TAZE olanın yaşı (saniye)."""
    from ui import live_feed, ws_feed

    ages: list[int] = []
    try:
        ws = ws_feed.status()
        if ws.get("connected") and ws.get("age") is not None:
            ages.append(int(ws["age"]))
    except Exception:
        pass
    try:
        fs = live_feed.status()
        if fs.get("price_age") is not None:
            ages.append(int(fs["price_age"]))
    except Exception:
        pass
    return min(ages) if ages else 9999


def stale_check(sell: bool = False) -> tuple[bool, str]:
    """(izin var mı, mesaj). sell=True ise satım eşiği (%120 sn) uygulanır."""
    age = tick_age()
    limit = STALE_SELL_SEC if sell else STALE_BUY_SEC
    if age > limit:
        if sell:
            return False, f"STALE: fiyat {age} sn bayat, satış bekletildi"
        return False, f"STALE: fiyat {age} sn bayat, alım atlandı"
    return True, f"Taze ({age} sn)"


# ------------------------------------------------------- 2) SLIPPAGE CUSUM
def record_slippage(actual_pct: float) -> dict[str, Any]:
    """Gerçek slippage yüzdesini kaydet, CUSUM'u güncelle."""
    st = _load()
    history = [float(x) for x in st.get("history", [])][-9:]
    history.append(float(actual_pct))
    deviation = float(actual_pct) - EXPECTED_SLIPPAGE_PCT
    cusum = max(0.0, float(st.get("cusum", 0.0) or 0) + deviation)
    st.update(history=history, cusum=round(cusum, 4),
              last_dev=round(deviation, 4),
              at=time.strftime("%Y-%m-%d %H:%M:%S"))
    _save(st)
    return status()


def status() -> dict[str, Any]:
    st = _load()
    cusum = float(st.get("cusum", 0.0) or 0)
    hist = [float(x) for x in st.get("history", [])]
    recent5 = round(sum(hist[-5:]) / len(hist[-5:]), 3) if hist else 0.0
    state = "Normal"
    msg = ""
    if cusum > CUSUM_HALT:
        state = "ALARM"
        msg = (f"SLIPPAGE ALARM: CUSUM %{cusum:.2f}, alım durduruldu "
               f"— son 5 işlem ort. %{recent5:.2f}")
    elif cusum > CUSUM_ALERT:
        state = "UYARI"
        msg = (f"SLIPPAGE UYARISI: Modelden sapma %{cusum:.2f}, "
               f"son 5 işlem ort. %{recent5:.2f}")
    return {
        "cusum_pct": round(cusum, 3),
        "state": state,
        "msg": msg,
        "recent5_avg_pct": recent5,
        "halt": cusum > CUSUM_HALT,
        "expected_pct": EXPECTED_SLIPPAGE_PCT,
        "at": st.get("at", "—"),
    }


def buy_allowed() -> tuple[bool, str]:
    s = status()
    return (not s["halt"]), s["msg"]
