"""
Canlı sinyal akışı ve değişim tabanlı bildirim.

- İzlenen hisseler 30 saniyede bir değerlendirilir (hafif sinyal yolu).
- Karar değiştiğinde (örn. NÖTR -> AL, AL -> SAT) tek seferlik olay kaydedilir
  ve aktif kanallara bağlamlı bildirim gönderilir.
- Aynı karar tekrar tekrar görülürse bildirim gidmez (alarm yorgunluğu önlenir).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import auth
from ui.batch_analysis import quick_decision
from ui.market_session import status as session_status


def _path(username: str):
    return auth.user_dir(username) / "signal_state.json"


def _load(username: str) -> dict[str, Any]:
    data = auth.read_json(_path(username), {})
    if not isinstance(data, dict):
        return {}
    data.setdefault("last", {})
    data.setdefault("events", [])
    return data


@st.cache_data(ttl="30s", max_entries=200, show_spinner=False)
def terminal_decision(symbol: str, risk_items: Any) -> dict[str, Any] | None:
    """30 sn TTL ile hafif karar (quick_decision'ın mantığını kullanır)."""
    return quick_decision.__wrapped__(symbol, risk_items)


def evaluate_watchlist(symbols: list[str], settings: dict[str, Any]) -> list[dict[str, Any]]:
    risk_items = tuple(sorted(settings.get("risk", {}).items()))
    rows = []
    for symbol in symbols[:8]:
        row = terminal_decision(symbol.strip().upper(), risk_items)
        if row:
            rows.append(row)
    return rows


def detect_and_record(
    username: str,
    results: list[dict[str, Any]],
    settings: dict[str, Any],
    notify_wait: bool = False,
    notify_offhours: bool = False,
) -> list[dict[str, Any]]:
    state = _load(username)
    last: dict[str, str] = state["last"]
    events: list[dict[str, Any]] = state["events"]
    session = session_status()
    new_events: list[dict[str, Any]] = []

    for row in results:
        symbol = row["Sembol"]
        current = row["Karar"]
        previous = last.get(symbol)
        last[symbol] = current
        if previous is None or previous == current:
            continue
        if current == "BEKLE" and not notify_wait:
            continue
        if not session["in_session"] and not notify_offhours:
            continue
        event = {
            "time": auth._now(),
            "symbol": symbol,
            "from": previous,
            "to": current,
            "price": row["Fiyat"],
            "change": row["Değişim %"],
            "confidence": row["Güven"],
            "reason": row["Gerekçe"],
            "session": row["Seans"],
        }
        new_events.append(event)
        events.append(event)

    state["events"] = events[-100:]
    auth.write_json(_path(username), state)

    if new_events:
        _notify(new_events)
    return new_events


def _notify(events: list[dict[str, Any]]) -> None:
    try:
        from ui.notify import send_notification

        lines = ["BIST SİNYAL DEĞİŞİMİ", ""]
        for e in events[:6]:
            lines += [
                f"• {e['symbol']}: {e['from']} → {e['to']}",
                f"  Fiyat {e['price']:,.2f} ({e['change']:+.2f}%) · güven %{e['confidence']}",
                f"  {e['reason']}",
                f"  Saat: {e['time']} · seans: {e['session']}",
            ]
        lines += ["", "Tek başına işlem sebebi değildir; fiyatı teyit edin."]
        send_notification("\n".join(lines))
    except Exception:
        pass


def read_events(username: str, limit: int = 30) -> list[dict[str, Any]]:
    return list(reversed(_load(username)["events"][-limit:]))
