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
    day_map = {"sun": "sunday", "mon": "monday"}
    tag = parts[-1]
    if tag in day_map and time.strftime("%A").lower() != day_map[tag]:
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
            try:
                from ui import health_report

                if _due("health_report", "23:00"):
                    health_report.send()
            except Exception:
                pass
            if _due("backup", "00:00"):
                from ui import disaster_recovery

                disaster_recovery.backup("günlük 00:00")
            if _due("strategy", "00:00@sun"):
                ops.weekly_strategy_review()
            if _due("perf_export", "23:00@sun"):
                try:
                    from ui import performance_export

                    performance_export.export()
                except Exception:
                    pass
            if _due("weekly_report", "09:00@mon"):
                ops.weekly_report()
            try:
                from ui import auto_optimize

                if auto_optimize.due():
                    auto_optimize.optimize()
            except Exception:
                pass
            try:
                from ui import monthly_backtest

                if monthly_backtest.due():
                    monthly_backtest.run()
            except Exception:
                pass
            if time.strftime("%M:%S") <= "00:30" and LAST.get("health") != time.strftime("%Y-%m-%d %H"):
                LAST["health"] = time.strftime("%Y-%m-%d %H")
                ops.health_check()
        except Exception as exc:
            ops._log(f"scheduler hata: {type(exc).__name__}: {str(exc)[:100]}")
        time.sleep(check_every)


if __name__ == "__main__":
    run_forever()
