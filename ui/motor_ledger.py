"""MOTOR BAZLI KÂR DEFTERİ — mikro ve fırsat sermayesini ayrı izler.

Bir motor diğerinin sermayesini yemesin: kendi net K/Z'si takip edilir,
günlük rapor ve panelde ayrı gösterilir. Limit değiştirmez, sadece ölçer.
"""

from __future__ import annotations

from typing import Any

from ui import tr_scalper as t

MOTORS = ("MICRO", "FIRSAT", "CRASH_BID", "OBI_VWAP", "—")


def snapshot() -> dict[str, dict[str, float]]:
    st = t._load()
    out: dict[str, dict[str, float]] = {
        m: {"trades": 0, "net": 0.0} for m in MOTORS
    }
    for h in st.get("history") or []:
        if not isinstance(h, dict):
            continue
        motor = str(h.get("motor", "—"))
        if motor not in out:
            out[motor] = {"trades": 0, "net": 0.0}
        out[motor]["trades"] += 1
        out[motor]["net"] += float(h.get("net_pnl", 0) or 0)
    for m in out:
        out[m]["net"] = round(out[m]["net"], 2)
    return out


def summary_text() -> str:
    s = snapshot()
    return " · ".join(
        f"{m}: {v['trades']} işlem / {v['net']:+.2f} TL"
        for m, v in s.items() if v["trades"] > 0
    ) or "henüz kapamış işlem yok"
