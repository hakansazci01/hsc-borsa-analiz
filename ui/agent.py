"""
Akıllı İşlem Ajansı.

Dağınık modülleri tek bir karar organında birleştirir:
- rejime göre ağırlıklandırılmış 9 zaman dilimi uyumu (confluence),
- KAP duyarımı ve BIST 100'e göre göreli güç,
- işlem öncesi kalite kontrolleri (seans, tazelik, likidite, limitler),
- tam trade planı (giriş bölgesi, ATR stop, R katları, Kelly+volatilite boyutu, ufuk, geçersizleme),
- gerçekleşen kurgusal işlemlerle güven kalibrasyonu.

Sistem emir göndermez; plan üretir ve kullanıcı onayına sunar.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import auth
from ui.audit import wilson_interval
from ui.bist_universe import load_companies
from ui.market_session import status as session_status
from ui.stream import live_quote


REC_VALUE = {"STRONG_BUY": 2, "BUY": 1, "NEUTRAL": 0, "SELL": -1, "STRONG_SELL": -2}

REGIME_WEIGHTS: dict[str, dict[str, float]] = {
    "Yükseliş": {"1m": 0.5, "5m": 1, "15m": 1, "30m": 1, "1h": 2, "4h": 3, "1d": 3, "1W": 2, "1M": 1},
    "Düşüş": {"1m": 1, "5m": 1, "15m": 2, "30m": 2, "1h": 3, "4h": 2, "1d": 2, "1W": 1, "1M": 0.5},
    "Yatay": {"1m": 2, "5m": 3, "15m": 3, "30m": 2, "1h": 1, "4h": 1, "1d": 1, "1W": 0.5, "1M": 0},
    "Yüksek oynaklık": {"1m": 1, "5m": 2, "15m": 2, "30m": 2, "1h": 2, "4h": 1, "1d": 1, "1W": 0.5, "1M": 0},
}

BULL_WORDS = ("olumlu", "büyüme", "artış", "yükseltme", "kâr", "kar", "ihale", "sözleşme", "anlaşma", "rekor", "temettü", "alım", "yatırım")
BEAR_WORDS = ("zarar", "düşüş", "azalış", "uyarı", "inceleme", "yasağı", "ceza", "dava", "risk", "iptal", "olumsuz", "satım", "sermaye artırımı", "borç")


def _yahoo(symbol: str) -> str:
    if "." in symbol:
        return symbol
    return symbol + ".IS" if symbol in load_companies() else symbol


@st.cache_data(ttl="60s", max_entries=150, show_spinner=False)
def agent_inputs(
    symbol: str,
    indicators: Any,
    weights: Any,
    thresholds: Any,
    risk: Any,
    backtest_cfg: Any,
    guards: Any,
) -> dict[str, Any] | None:
    import borsapy as bp

    from ui.core import analysis_args, analyze_symbol
    from ui.risk_engine import detect_regime

    sym = symbol.strip().upper()
    try:
        quote = live_quote(sym) or {}
        signals = bp.Ticker(sym).ta_signals_all_timeframes() or {}
        regime = detect_regime(sym)
        daily = analyze_symbol(
            _yahoo(sym), "2y", "1d", indicators, weights, thresholds, risk, backtest_cfg, guards
        )
        df = daily["df"]
        atr = float(df["ATR"].iloc[-1]) if "ATR" in df else 0.0

        news_score = 0.0
        try:
            news = bp.Ticker(sym).news or []
            for item in news[:12]:
                title = str((item.get("content") or {}).get("title") or item.get("title") or "").lower()
                news_score += sum(1 for w in BULL_WORDS if w in title) - sum(1 for w in BEAR_WORDS if w in title)
            news_score = max(-1.0, min(1.0, news_score / 6.0))
        except Exception:
            pass

        return {
            "symbol": sym,
            "quote": quote,
            "signals": signals,
            "regime": regime,
            "atr": atr,
            "news_score": news_score,
            "backtest": daily["backtest"],
        }
    except Exception:
        return None


def confluence(data: dict[str, Any]) -> dict[str, Any]:
    signals = data.get("signals", {}) or {}
    regime = data.get("regime", {}) or {}
    weights = REGIME_WEIGHTS.get(regime.get("regime", "Yatay"), REGIME_WEIGHTS["Yatay"])

    contributions: list[dict[str, Any]] = []
    total_weight = 0.0
    weighted = 0.0
    for tf, weight in weights.items():
        block = signals.get(tf) or {}
        summary = block.get("summary", {}) or {}
        rec = str(summary.get("recommendation", "NEUTRAL")).upper()
        value = REC_VALUE.get(rec, 0)
        weighted += weight * value
        total_weight += weight
        if value:
            contributions.append({
                "Zaman": tf, "Sinyal": rec, "Katkı": round(weight * value / 2, 2),
                "AL": int(summary.get("buy", 0) or 0), "SAT": int(summary.get("sell", 0) or 0),
            })

    tf_score = (weighted / total_weight / 2) if total_weight else 0.0

    # Göreli güç: hisse değişimi - BIST100 değişimi
    rel = 0.0
    try:
        from ui.market_ticker import market_snapshot

        bench = next((i for i in market_snapshot() if i["name"] == "BIST 100"), None)
        if bench:
            rel = float(data["quote"].get("change_pct") or 0) - float(bench.get("change") or 0)
    except Exception:
        pass
    rel_score = max(-1.0, min(1.0, rel / 3.0))

    news_score = float(data.get("news_score", 0))
    final = max(-1.0, min(1.0, 0.60 * tf_score + 0.20 * news_score + 0.20 * rel_score))
    decision = "AL" if final >= 0.30 else "SAT" if final <= -0.30 else "BEKLE"

    consensus = 0.5
    if contributions:
        pos = sum(c["AL"] for c in contributions)
        neg = sum(c["SAT"] for c in contributions)
        consensus = max(pos, neg) / max(pos + neg, 1)

    return {
        "score": round(final, 3),
        "tf_score": round(tf_score, 3),
        "news_score": round(news_score, 3),
        "relative_score": round(rel_score, 3),
        "relative_pct": round(rel, 2),
        "decision": decision,
        "consensus": round(consensus, 2),
        "contributions": sorted(contributions, key=lambda c: -abs(c["Katkı"])),
    }


def calibrated_confidence(raw: int, username: str) -> tuple[int, str]:
    """Gerçekleşen kurgusal işlemlerle tahmin güvenini kalibre eder."""
    history = auth.read_history(username, limit=500)
    closed = [
        r for r in history
        if r.get("type") == "PAPER_SAT" and r.get("confidence")
    ]
    if len(closed) < 15:
        return raw, "Yeterli gerçekleşmiş işlem yok (<15); ham güven kullanılıyor."

    near = [r for r in closed if abs(float(r["confidence"]) - raw) <= 20]
    if len(near) < 8:
        return raw, "Bu güven aralığında yeterli örnek yok; ham güven kullanılıyor."

    actual = sum(1 for r in near if float(r.get("pnl_pct", 0)) > 0) / len(near)
    expected = raw / 100.0
    adjustment = int(max(-12, min(12, round((actual - expected) * 40))))
    adjusted = int(max(5, min(95, raw + adjustment)))
    return adjusted, (
        f"Bu güven seviyesindeki {len(near)} geçmiş işlemin %{actual*100:.0f}'i kârlıydı; "
        f"güven {raw} → {adjusted} olarak düzeltilti."
    )


def build_plan(symbol: str, settings: dict[str, Any], username: str) -> dict[str, Any] | None:
    args = _build_args(settings)
    data = agent_inputs(
        symbol, args["indicators"], args["weights"], args["thresholds"],
        args["risk"], args["backtest_cfg"], args["guards"],
    )
    if not data:
        return None
    conf = confluence(data)
    raw_conf = int(min(95, max(10, round(38 + abs(conf["score"]) * 38 + conf["consensus"] * 18))))
    confidence, calib_note = calibrated_confidence(raw_conf, username)

    price = float(data["quote"].get("price") or 0)
    atr = float(data.get("atr") or 0)
    risk = settings["risk"]
    regime = data["regime"].get("regime", "Yatay")
    decision = conf["decision"]
    sign = 1 if decision == "AL" else -1 if decision == "SAT" else 0

    stop_dist = max(atr * 1.5 if atr else 0, price * float(risk.get("stop_loss_pct", 0.05)))
    stop = round(price - sign * stop_dist, 2) if sign else None
    t1 = round(price + sign * stop_dist * 1.5, 2) if sign else None
    t2 = round(price + sign * stop_dist * 2.5, 2) if sign else None
    t3 = round(price + sign * stop_dist * 4.0, 2) if sign else None

    # Kelly yarısı + %2 sert tavan + volatilite ile ölçeklenen risk
    try:
        from ui.risk_engine import kelly_sizing

        kelly = kelly_sizing(data["backtest"], risk)
        suggested_risk = min(float(kelly.get("suggested_risk_pct", 1.0)) / 100, 0.02)
    except Exception:
        suggested_risk = 0.01
    risk_amount = float(risk["initial_capital"]) * suggested_risk if decision != "BEKLE" else 0.0
    qty = round(risk_amount / stop_dist, 2) if (stop_dist > 0 and decision != "BEKLE") else 0.0

    horizon = {"Yükseliş": 10, "Düşüş": 5, "Yatay": 5, "Yüksek oynaklık": 3}.get(regime, 5)
    invalidation = (
        "1 günlük kapanış SMA50 altına inerse plan iptal." if decision == "AL"
        else "1 günlük kapanış SMA50 üstüne çıkarsa plan iptal." if decision == "SAT"
        else "Yön netleşene kadar işlem yok."
    )

    return {
        "symbol": symbol,
        "decision": decision,
        "confidence": confidence,
        "raw_confidence": raw_conf,
        "calibration_note": calib_note,
        "score": conf["score"],
        "confluence": conf,
        "regime": regime,
        "regime_confidence": data["regime"].get("confidence", 0),
        "price": price,
        "atr": round(atr, 3),
        "stop_distance_pct": round(stop_dist / price * 100, 2) if price else 0,
        "stop": stop, "t1": t1, "t2": t2, "t3": t3,
        "qty": qty,
        "risk_pct": round(suggested_risk * 100, 2),
        "risk_amount": round(risk_amount, 2),
        "horizon": horizon,
        "invalidation": invalidation,
        "quote": data["quote"],
        "session": session_status(),
    }


def _build_args(settings: dict[str, Any]) -> dict[str, Any]:
    from ui.core import analysis_args

    return analysis_args(settings)


def pretrade_checks(plan: dict[str, Any], username: str, settings: dict[str, Any]) -> list[dict[str, Any]]:
    from ui import paper

    checks: list[dict[str, Any]] = []
    session = plan["session"]
    quote = plan["quote"]

    checks.append({
        "Kontrol": "Seans açık", "Geçti": session["in_session"],
        "Detay": session["detail"],
    })
    freshness = "Bilinmiyor"
    passed = True
    qt = quote.get("timestamp") or ""
    if qt:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            moment = datetime.strptime(qt, "%d.%m.%Y %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Istanbul"))
            from ui.market_session import now

            age = (now() - moment).total_seconds() / 60
            freshness = f"Kotasyon yaşı {age:.0f} dk"
            passed = age <= 20
        except ValueError:
            freshness = "Kotasyon saati okunamadı"
            passed = False
    checks.append({"Kontrol": "Veri tazeliği", "Geçti": passed, "Detay": freshness})

    volume = float(quote.get("volume") or 0)
    checks.append({
        "Kontrol": "Likidite (hacim > 100k)",
        "Geçti": volume >= 100000,
        "Detay": f"Günlük hacim {volume:,.0f}",
    })

    checks.append({
        "Kontrol": "Yönlü sinyal", "Geçti": plan["decision"] != "BEKLE",
        "Detay": f"Karar: {plan['decision']}",
    })
    checks.append({
        "Kontrol": "Güven eşiği (%55)", "Geçti": plan["confidence"] >= 55,
        "Detay": f"Kalibre güven %{plan['confidence']}",
    })

    open_positions = paper.load_positions(username)
    checks.append({
        "Kontrol": "Azami pozisyon",
        "Geçti": len(open_positions) < int(settings["risk"].get("max_positions", 5)),
        "Detay": f"{len(open_positions)} açık pozisyon",
    })
    checks.append({
        "Kontrol": "Aynı hissede pozisyon yok",
        "Geçti": all(p.get("symbol") != plan["symbol"] for p in open_positions),
        "Detay": "Mevcut pozisyonlarla çakışma kontrolü",
    })

    today_loss = 0.0
    from ui.market_session import now

    day = now().strftime("%d.%m.%Y")
    for row in auth.read_history(username, limit=200):
        if row.get("type") == "PAPER_SAT" and str(row.get("time", "")).startswith(day):
            today_loss += float(row.get("pnl_amount", 0) or 0)
    cap = float(settings["risk"]["initial_capital"]) * float(settings["risk"].get("stop_loss_pct", 0.05))
    checks.append({
        "Kontrol": "Günlük zarar limiti",
        "Geçti": today_loss > -cap,
        "Detay": f"Bugünkü gerçekleşen K/Z {today_loss:,.2f} ₺, limit {-cap:,.0f} ₺",
    })
    return checks
