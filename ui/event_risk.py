"""
Olay riski koruması — makro takvimden gelen yüksek önemli olaylar için
savunma amaçlı pencere. Olaylar asla AL/SAT sinyali üretmez; yalnızca yeni
girişi engelleyen bir risk filtresidir.

Kaynak: borsapy EconomicCalendar (bkz. ui/economic_calendar.py). Saatler
Türkiye saatine (TRT) göre yorumlanır; şüpheli/eksik veride "manuel kontrol"
önerilir, sessizce "olay yok" denmez.
"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import Any

import streamlit as st

from ui.economic_calendar import today_events


WINDOW_MIN = 15
_HIGH = {"high", "3", "yüksek", "yuksek"}
_TR = {"TÜRKİYE", "TURKEY", "TR", "TÜRKIYE"}


@st.cache_data(ttl="30m", show_spinner=False)
def assess() -> dict[str, Any]:
    events = today_events()
    if not events:
        return {
            "level": "unknown",
            "note": "Ekonomik takvime ulaşılamadı; olay riskini manuel kontrol edin.",
            "active": False,
            "high": [],
        }

    now = datetime.now().astimezone()
    high: list[dict[str, Any]] = []
    for event in events:
        importance = str(event.get("Importance", "")).strip().lower()
        country = str(event.get("Country", "")).strip().upper()
        if importance not in _HIGH or (country and country not in _TR):
            continue
        match = re.search(r"(\d{1,2}):(\d{2})", str(event.get("Time", "")))
        if not match:
            high.append({"event": str(event.get("Event", "olay")), "time": "", "exact": False})
            continue
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            continue
        moment = datetime.combine(now.date(), time(hour, minute), tzinfo=now.tzinfo)
        high.append({
            "event": str(event.get("Event", "olay")),
            "time": f"{hour:02d}:{minute:02d}",
            "exact": True,
            "moment": moment,
        })

    active = any(
        item.get("exact") and abs((now - item["moment"]).total_seconds()) <= WINDOW_MIN * 60
        for item in high
    )
    if active:
        note = "Yüksek önemli olay penceresi aktif: yeni kurgusal giriş önerilmez (risk filtresi)."
    elif high:
        note = "Bugün yüksek önemli TR olayı var: " + ", ".join(
            f"{i['event']} {i.get('time') or '(saat belirsiz)'}" for i in high[:3]
        )
    else:
        note = "Bugün yüksek önemli TR olayı görünmüyor; takvim gecikmeli olabilir."
    return {"level": "active" if active else ("upcoming" if high else "none"),
            "note": note, "active": active, "high": high}


def render(flag: dict[str, Any]) -> None:
    level = flag.get("level", "unknown")
    if level == "active":
        st.warning(flag["note"], icon=":material/event:", title="Olay riski aktif")
    elif level == "unknown":
        st.caption("⚠ " + flag["note"])
    elif flag.get("high"):
        st.caption("📅 " + flag["note"])
