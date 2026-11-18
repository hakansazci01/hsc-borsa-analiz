"""
Açılış öncesi hazırlık: 10:00'dan önce tüm veri ve analizleri tazeler.

Yapılanlar:
- ilgili tüm cache'leri temizler
- izleme listesini baştan tarar (fiyat, KAP, teknik sinyal, rejim)
- günün ekonomik takvimini yükler
- sonucu kullanıcı geçmişine yazar ve aktif bildirim kanallarına gönderir
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import auth
from ui.core import analysis_args, load_settings, scan_market
from ui.market_session import now
from ui.notify import send_notification


def _state_path(username: str):
    return auth.user_dir(username) / "premarket.json"


def done_today(username: str) -> bool:
    state = auth.read_json(_state_path(username), {})
    return str(state.get("date", "")) == now().strftime("%Y-%m-%d")


def _mark_done(username: str, report: dict[str, Any]) -> None:
    auth.write_json(_state_path(username), {
        "date": now().strftime("%Y-%m-%d"),
        "time": auth._now(),
        "scanned": report.get("scanned", 0),
        "buys": report.get("buys", []),
        "sells": report.get("sells", []),
    })


def open_refresh_done_today(username: str) -> bool:
    state = auth.read_json(_state_path(username), {})
    return str(state.get("open_done_date", "")) == now().strftime("%Y-%m-%d")


def _mark_open_done(username: str) -> None:
    state = auth.read_json(_state_path(username), {})
    state["open_done_date"] = now().strftime("%Y-%m-%d")
    state["open_done_time"] = auth._now()
    auth.write_json(_state_path(username), state)


def market_open_refresh(username: str, notify: bool = True) -> dict[str, Any]:
    """10:00 açılışında tüm cache'leri temizler ve ilk gerçek zamanlı analizi yapar."""
    clear_caches()
    settings = load_settings(auth.settings_path(username))
    args = analysis_args(settings)
    results = scan_market(
        tuple(settings["symbols"]),
        args["period"], args["interval"], args["indicators"], args["weights"],
        args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
    )
    buys = [
        r["info"]["symbol"] for r in results
        if "info" in r and r["info"]["signal"] in ("STRONG_BUY", "BUY")
    ]
    sells = [
        r["info"]["symbol"] for r in results
        if "info" in r and r["info"]["signal"] in ("STRONG_SELL", "SELL")
    ]
    report = {
        "time": auth._now(), "type": "SEANS_ACILIS_GUNCELLEME",
        "scanned": len(results), "buys": buys, "sells": sells,
    }
    auth.append_history(username, report)
    _mark_open_done(username)
    try:
        from ui.pnl_tracker import record_mark

        record_mark(
            username, settings,
            [{"decision": r["info"]["signal"]} for r in results if "info" in r],
        )
    except Exception:
        pass
    if notify:
        lines = [
            "BIST seansı açıldı - ilk gerçek zamanlı analiz hazır",
            f"Taranan hisse: {len(results)}",
            f"AL: {', '.join(buys) if buys else 'yok'}",
            f"SAT: {', '.join(sells) if sells else 'yok'}",
        ]
        try:
            send_notification("\n".join(lines), settings)
        except Exception:
            pass
    return report


def clear_caches() -> None:
    # Disk üzerindeki yfinance CSV önbelleği de bayat olabilir; silinmeden
    # "yenile" yalnızca Streamlit cache'ini temizlemiş olur.
    from borsa_bot.data import CACHE_DIR

    if CACHE_DIR.exists():
        for csv_file in CACHE_DIR.glob("*.csv"):
            try:
                csv_file.unlink()
            except OSError:
                pass

    from ui.benchmark import bist100_benchmark
    from ui.economic_calendar import today_events
    from ui.finnhub import us_news, us_quote
    from ui.live_data import get_live_snapshot, scan_bist
    from ui.market_ticker import market_snapshot
    from ui.risk_engine import detect_regime
    from ui.validation import parameter_sensitivity, walk_forward
    from ui.core import analyze_symbol, scan_market as scan

    for fn in (
        get_live_snapshot, scan_bist, detect_regime, market_snapshot,
        us_quote, us_news, today_events, bist100_benchmark,
        walk_forward, parameter_sensitivity, analyze_symbol, scan,
    ):
        try:
            fn.clear()
        except Exception:
            pass


def refresh(username: str, notify: bool = True) -> dict[str, Any]:
    clear_caches()
    settings = load_settings(auth.settings_path(username))
    args = analysis_args(settings)
    results = scan_market(
        tuple(settings["symbols"]),
        args["period"], args["interval"], args["indicators"], args["weights"],
        args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
    )
    buys = [
        r["info"]["symbol"] for r in results
        if "info" in r and r["info"]["signal"] in ("STRONG_BUY", "BUY")
    ]
    sells = [
        r["info"]["symbol"] for r in results
        if "info" in r and r["info"]["signal"] in ("STRONG_SELL", "SELL")
    ]
    report = {
        "time": auth._now(), "type": "SEANS_ONCESI_HAZIRLIK",
        "scanned": len(results), "buys": buys, "sells": sells,
    }
    auth.append_history(username, report)
    _mark_done(username, report)
    try:
        from ui.pnl_tracker import record_mark

        record_mark(
            username, settings,
            [{"decision": r["info"]["signal"]} for r in results if "info" in r],
        )
    except Exception:
        pass

    if notify:
        lines = [
            "BIST seans öncesi analiz hazır (10:00)",
            f"Taranan hisse: {len(results)}",
            f"AL adayları: {', '.join(buys) if buys else 'yok'}",
            f"SAT adayları: {', '.join(sells) if sells else 'yok'}",
            "Sinyaller 10:00 sonrası güncel fiyatla tekrar doğrulanmalı.",
        ]
        try:
            send_notification("\n".join(lines), settings)
        except Exception:
            pass
    return report
