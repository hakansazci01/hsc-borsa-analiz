"""Zamanlı otonom görevler: 23:00 özet, 00:00 yedek, saatlik sağlık, Pazar strateji."""

from __future__ import annotations

import time
from ui import autonomous_ops as ops

LAST: dict[str, str] = {}


def _due(key: str, when: str) -> bool:
    """'HH:MM' veya 'HH:MM:WEEKDAY' için günde/haftada bir tetiklenir."""
    now = time.strftime("%Y-%m-%d %H:%M")
    parts = when.split("@")
    target_hm = parts[0]
    if parts[-1] == "sun" and time.strftime("%A").lower() != "sunday":
        return False
    if now.endswith(target_hm) and LAST.get(key) != now:
        LAST[key] = now
        return True
    return False


def run_forever(check_every: int = 30) -> None:
    ops._log("ZAMANLAYICI BAŞLADI — 23:00 özet, 00:00 yedek, saatlik sağlık, Pazar 00:00 strateji")
    while True:
        try:
            if time.strftime("%M:%S") <= "00:30" and LAST.get("alive") != time.strftime("%Y-%m-%d %H"):
                LAST["alive"] = time.strftime("%Y-%m-%d %H")
                ops.alive_signal()
            if _due("summary", "23:00"):
                ops.daily_summary()
            if _due("backup", "00:00"):
                ops.backup_files()
            if _due("strategy", "00:00@sun"):
                ops.weekly_strategy_review()
            if time.strftime("%M:%S") <= "00:30" and LAST.get("health") != time.strftime("%Y-%m-%d %H"):
                LAST["health"] = time.strftime("%Y-%m-%d %H")
                ops.health_check()
        except Exception as exc:
            ops._log(f"scheduler hata: {type(exc).__name__}: {str(exc)[:100]}")
        time.sleep(check_every)


if __name__ == "__main__":
    run_forever()
