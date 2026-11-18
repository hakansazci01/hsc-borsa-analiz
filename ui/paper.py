"""
Kurgusal (paper) pozisyon takibi.

Gerçek emir gönderilmez. Kullanıcı bir sinyale dayanarak "kurgusal alım" açar;
sistem pozisyonu izler ve stop / hedef / sinyal değişimi durumunda SAT önerisi
ve gerekçeler üretir. Tüm veriler kullanıcıya özel JSON dosyasında tutulur.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from ui import auth
from ui.live_data import get_live_snapshot
from ui.stream import live_quote
from ui.trade_engine import build_decision


def load_positions(username: str) -> list[dict[str, Any]]:
    data = auth.read_json(auth.portfolio_path(username), [])
    return data if isinstance(data, list) else []


def save_positions(username: str, positions: list[dict[str, Any]]) -> None:
    auth.write_json(auth.portfolio_path(username), positions)


def open_position(
    username: str,
    symbol: str,
    qty: float,
    price: float,
    stop: float | None,
    target: float | None,
    confidence: int,
    reason: str,
    allow_closed: bool = False,
) -> dict[str, Any]:
    from ui.market_session import status as session_status

    if not allow_closed and not session_status()["in_session"]:
        raise ValueError("Kurgusal pozisyon yalnızca BIST seansı içinde açılabilir.")
    position = {
        "id": f"{symbol}_{int(datetime.now().timestamp())}",
        "symbol": symbol.upper(),
        "qty": float(qty),
        "entry_price": float(price),
        "stop": float(stop) if stop else None,
        "target": float(target) if target else None,
        "confidence": int(confidence),
        "reason": reason,
        "opened_at": auth._now(),
    }
    positions = load_positions(username)
    positions.append(position)
    save_positions(username, positions)
    auth.append_history(username, {
        "time": auth._now(), "type": "PAPER_AL", "symbol": symbol.upper(),
        "price": price, "qty": qty, "confidence": confidence,
    })
    return position


def close_position(
    username: str, position_id: str, exit_price: float, reason: str,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    positions = load_positions(username)
    target = next((p for p in positions if p.get("id") == position_id), None)
    if not target:
        return None
    positions = [p for p in positions if p.get("id") != position_id]
    save_positions(username, positions)
    pnl_pct = (exit_price / target["entry_price"] - 1) * 100
    pnl_amount = (exit_price - target["entry_price"]) * target["qty"]
    record = {
        "time": auth._now(), "type": "PAPER_SAT", "symbol": target["symbol"],
        "entry": target["entry_price"], "exit": round(exit_price, 4),
        "pnl_pct": round(pnl_pct, 2), "pnl_amount": round(pnl_amount, 2),
        "reason": reason,
        "confidence": target.get("confidence", 0),
        "entry_signal": target.get("reason", ""),
    }
    auth.append_history(username, record)

    # Şeffaf performans defteri: kapanan her sinyal R çarpanıyla kaydedilir.
    # Kayıt hatası işlem kapatmayı engellemez.
    try:
        from ui.performance import record_close

        effective = settings or (st.session_state.get("settings", {}) if st.session_state else {})
        record_close(username, target, exit_price, reason, settings=effective)
    except Exception:
        pass
    return record


def evaluate(username: str, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Açık pozisyonları güncel fiyatla değerler ve SAT/TUT önerisi üretir."""
    positions = load_positions(username)
    if not positions:
        return []
    settings = settings or (st.session_state.get("settings", {}) if st.session_state else {})
    risk = settings.get("risk", {})
    results: list[dict[str, Any]] = []

    for p in positions:
        quote = live_quote(p["symbol"])
        price = float(quote.get("price") or p["entry_price"]) if quote else float(p["entry_price"])
        pnl_pct = (price / p["entry_price"] - 1) * 100
        pnl_amount = (price - p["entry_price"]) * p["qty"]
        action = "TUT"
        reasons: list[str] = []

        stop = p.get("stop")
        target = p.get("target")
        if stop and price <= float(stop):
            action = "SAT"
            reasons.append(f"Stop-loss seviyesi ({float(stop):,.2f}) tetiklendi.")
        elif target and price >= float(target):
            action = "SAT"
            reasons.append(f"Hedef fiyata ({float(target):,.2f}) ulaşıldı.")

        if action == "TUT":
            try:
                from ui.risk_engine import adjust_decision_for_regime, detect_regime

                snap = get_live_snapshot(p["symbol"])
                decision = build_decision(snap, "Dengeli", risk, 0.25)
                decision = adjust_decision_for_regime(decision, detect_regime(p["symbol"]))
                if decision["decision"] == "SAT":
                    action = "SAT"
                    reasons.append("Teknik sinyal SAT yönüne döndü.")
                elif decision["decision"] == "BEKLE":
                    reasons.append("Sinyal zayıfladı (BEKLE); pozisyonu yakından izleyin.")
                if decision.get("regime") in ("Düşüş", "Yüksek oynaklık"):
                    reasons.append(f"Rejim riski: {decision['regime']}.")
            except Exception:
                reasons.append("Canlı sinyale ulaşılamadı; fiyat ve KAP'ı manuel kontrol edin.")

        if pnl_pct > 0 and action == "TUT":
            reasons.append(f"Kâr %{pnl_pct:+.2f}; hedefe ulaşıldığında satışı değerlendirin.")
        elif pnl_pct < 0 and action == "TUT":
            reasons.append(f"Zarar %{pnl_pct:+.2f}; stop disiplinini koruyun.")

        results.append({
            **p,
            "current_price": round(price, 4),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_amount": round(pnl_amount, 2),
            "action": action,
            "reasons": reasons,
            "source": quote.get("source", "—") if quote else "—",
            "session": quote.get("session", "—") if quote else "—",
        })
    return results
