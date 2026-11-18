"""
BIST seans durumu (Europe/Istanbul).

Seans: hafta içi 10:00 - 18:00. Açılış öncesi hazırlık ve seans dışı
uyarıları bu modülden yönetilir; "anlık trade" yalnızca seans içinde anlamlıdır.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import streamlit as st


TZ = ZoneInfo("Europe/Istanbul")
OPEN_TIME = time(10, 0)
CLOSE_TIME = time(18, 0)

# Borsa İstanbul 2026 resmi tatil takvimi (pay piyasası)
# Kaynak: borsaistanbul.com 2026 tatil tablosu
HOLIDAYS_2026 = {
    "2026-01-01", "2026-03-20", "2026-03-21", "2026-03-22",
    "2026-04-23", "2026-05-01", "2026-05-19",
    "2026-05-27", "2026-05-28", "2026-05-29", "2026-05-30",
    "2026-07-15", "2026-10-29",
}
HALF_DAYS_2026 = {"2026-03-19", "2026-05-26", "2026-10-28"}


def now() -> datetime:
    return datetime.now(TZ)


def status() -> dict:
    moment = now()
    weekday = moment.weekday()
    current = moment.time()
    day_iso = moment.strftime("%Y-%m-%d")
    if weekday >= 5:
        return {
            "key": "closed", "label": "Hafta sonu",
            "detail": "BIST hafta sonu kapalı. Sonraki seans pazartesi 10:00.",
            "seconds_to_open": None, "in_session": False,
        }
    if day_iso in HOLIDAYS_2026:
        return {
            "key": "closed", "label": "Resmi tatil",
            "detail": "Borsa İstanbul bugün resmi tatil nedeniyle kapalı.",
            "seconds_to_open": None, "in_session": False,
        }
    close_time = time(13, 0) if day_iso in HALF_DAYS_2026 else CLOSE_TIME
    if current < OPEN_TIME:
        target = datetime.combine(moment.date(), datetime.min.time().replace(hour=10), TZ)
        return {
            "key": "pre_market", "label": "Seans öncesi",
            "detail": f"Piyasa 10:00'da açılıyor. Kalan: {_fmt(target - moment)}",
            "seconds_to_open": max(0, int((target - moment).total_seconds())),
            "in_session": False,
        }
    if current < close_time:
        target = datetime.combine(moment.date(), datetime.min.time().replace(
            hour=close_time.hour, minute=close_time.minute
        ), TZ)
        return {
            "key": "open", "label": "Seans açık",
            "detail": f"Seans {close_time.strftime('%H:%M')}'de kapanıyor. Kalan: {_fmt(target - moment)}",
            "seconds_to_open": 0, "in_session": True,
        }
    # seans kapandı, ertesi iş günü 10:00
    next_day = moment.date() + timedelta(days=1)
    while next_day.weekday() >= 5 or next_day.strftime("%Y-%m-%d") in HOLIDAYS_2026:
        next_day += timedelta(days=1)
    target = datetime.combine(next_day, datetime.min.time().replace(hour=10), TZ)
    return {
        "key": "after_hours", "label": "Seans kapalı",
        "detail": f"Sonraki seans {next_day.strftime('%d.%m')} 10:00. Kalan: {_fmt(target - moment)}",
        "seconds_to_open": max(0, int((target - moment).total_seconds())),
        "in_session": False,
    }


def _fmt(delta: timedelta) -> str:
    total = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def badge() -> None:
    info = status()
    color = {"open": "green", "pre_market": "orange", "after_hours": "gray", "closed": "gray"}[info["key"]]
    st.badge(info["label"], color=color, help=info["detail"])
