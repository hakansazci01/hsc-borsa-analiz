"""
Basit zamanlayıcı: ayarlanan aralıkta otomatik piyasa taraması yapar.

Not: Streamlit tarayıcıda açıkken çalışır; sunucu arka plan servisi değildir.
Cron ifadeleri croniter ile hesaplanır. Son çalışma zamanı kullanıcıya özel
JSON dosyasında tutulur.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st
from croniter import croniter

from ui import auth
from ui.core import analysis_args, scan_market
from ui.help_texts import h
from ui.market_session import now as istanbul_now


def _now_naive() -> datetime:
    """Cron hesapları için İstanbul duvar saatini (tz'siz) döndürür."""
    return istanbul_now().replace(tzinfo=None)


PRESETS: dict[str, str | None] = {
    "Kapalı": None,
    "Seans öncesi hazırlık (09:50)": "50 9 * * 1-5",
    "Her 15 dakika": "*/15 * * * *",
    "Her saat": "0 * * * *",
    "Seans başı (10:00)": "0 10 * * 1-5",
    "Seans sonu (18:00)": "0 18 * * 1-5",
    "Her gün 09:00": "0 9 * * *",
}


def _state_path(username: str):
    return auth.user_dir(username) / "scheduler.json"


def _load_state(username: str) -> dict[str, Any]:
    return auth.read_json(_state_path(username), {})


def _save_state(username: str, state: dict[str, Any]) -> None:
    auth.write_json(_state_path(username), state)


def next_run(expr: str | None, now: datetime | None = None) -> datetime | None:
    if not expr:
        return None
    now = now or _now_naive()
    try:
        return croniter(expr, now).get_next(datetime)
    except Exception:
        return None


def is_due(expr: str | None, last_run: datetime | None, now: datetime | None = None) -> bool:
    if not expr:
        return False
    now = now or _now_naive()
    if last_run is None:
        return False
    try:
        scheduled = croniter(expr, last_run).get_next(datetime)
        return scheduled <= now
    except Exception:
        return False


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def run_scan(username: str, settings: dict[str, Any], reason: str) -> dict[str, Any]:
    """İzleme listesini tarar ve özeti kullanıcı geçmişine yazar."""
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
    record = {
        "time": auth._now(), "type": "OTOMATIK_TARAMA", "reason": reason,
        "scanned": len(results), "buys": buys, "sells": sells,
    }
    auth.append_history(username, record)

    try:
        from ui.pnl_tracker import record_mark

        marks = [
            {"decision": r["info"]["signal"]} for r in results if "info" in r
        ]
        record_mark(username, settings, marks)
    except Exception:
        pass

    try:
        from ui.notify import send_notification, trade_alert

        send_notification(trade_alert(reason, results, settings, username), settings)
    except Exception:
        pass

    state = _load_state(username)
    state["last_run"] = _now_naive().isoformat()
    _save_state(username, state)
    return record


def auto_check_fragment(username: str, settings: dict[str, Any]) -> None:
    """Arayüz açıkken zamanı kontrol eder; seans öncesi hazırlığı ve taramayı yapar."""
    from ui.market_session import status as session_status
    from ui.premarket import (
        done_today, market_open_refresh, open_refresh_done_today,
        refresh as premarket_refresh,
    )

    session = session_status()

    # Seans açılmadan önce tüm analizleri bir kez tazele (zamanlayıcı kapalı olsa da)
    if session["key"] == "pre_market" and not done_today(username):
        report = premarket_refresh(username)
        st.toast(
            f"Seans öncesi hazırlık tamamlandı: {report['scanned']} hisse, "
            f"{len(report['buys'])} AL adayı",
            icon=":material/alarm:",
        )
        st.rerun()

    # 10:00 açılışında cache temizlenir ve ilk gerçek zamanlı analiz yapılır
    if session["key"] == "open" and not open_refresh_done_today(username):
        report = market_open_refresh(username)
        st.toast(
            f"Seans açıldı - ilk canlı analiz hazır: {report['scanned']} hisse",
            icon=":material/alarm:",
        )
        st.rerun()

    preset = settings.get("schedule", "Kapalı")
    expr = PRESETS.get(preset)
    if not expr:
        return
    state = _load_state(username)
    last = _parse(state.get("last_run"))
    if last is None:
        state["last_run"] = _now_naive().isoformat()
        _save_state(username, state)
        return
    if is_due(expr, last):
        if preset.startswith("Seans öncesi"):
            record = premarket_refresh(username)
            st.toast("Seans öncesi hazırlık tamamlandı.", icon=":material/alarm:")
            st.rerun()
            return
        record = run_scan(username, settings, f"Zamanlı tarama: {preset}")
        st.toast(
            f"Otomatik tarama tamamlandı: {record['scanned']} hisse, "
            f"{len(record['buys'])} AL, {len(record['sells'])} SAT",
            icon=":material/alarm:",
        )
        st.rerun()


def render_scheduler(username: str, settings: dict[str, Any]) -> None:
    """Hesabım sayfasında zamanlayıcı ayarlarını gösterir."""
    preset = st.selectbox(
        "Otomatik tarama aralığı", list(PRESETS),
        index=list(PRESETS).index(settings.get("schedule", "Kapalı")),
        key="schedule_select",
        help=h("schedule"),
    )
    if preset != settings.get("schedule", "Kapalı"):
        settings = {**settings, "schedule": preset}
        from ui.core import save_settings

        save_settings(settings, auth.settings_path(username))
        st.session_state.settings = settings
        st.toast(f"Zamanlayıcı: {preset}", icon=":material/check:")

    expr = PRESETS.get(preset)
    nxt = next_run(expr)
    state = _load_state(username)
    last = _parse(state.get("last_run"))
    c1, c2 = st.columns(2)
    c1.metric("Son tarama", last.strftime("%d.%m %H:%M") if last else "—", icon=":material/history:")
    c2.metric("Sonraki tarama", nxt.strftime("%d.%m %H:%M") if nxt else "Kapalı", icon=":material/alarm:")
    st.caption(
        "Zamanlayıcı yalnızca uygulama tarayıcıda açıkken çalışır. "
        "Sunucu arka plan servisi değildir."
    )
    if st.button("Şimdi tara", icon=":material/play_arrow:", key="schedule_run_now"):
        record = run_scan(username, settings, "Manuel tetikleme")
        st.toast(f"Tarama tamamlandı: {record['scanned']} hisse", icon=":material/check:")
