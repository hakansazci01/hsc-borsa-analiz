"""
"Akıllı analist" katmanı.

Ham gösterge/skor ve backtest değerlerini yorumlayıp kullanıcıya anlaşılır
gerekçeler, güven skoru, risk profiline göre öneri ve portföy dağılımı üretir.
Harici bir LLM gerektirmez; motorun çıkardığı sinyalleri şeffaf biçimde yorumlar.
"""

from __future__ import annotations

from typing import Any


SIGNAL_LABELS = {
    "STRONG_BUY": "Güçlü AL",
    "BUY": "AL",
    "NEUTRAL": "NÖTR",
    "SELL": "SAT",
    "STRONG_SELL": "Güçlü SAT",
}

SIGNAL_COLORS = {
    "STRONG_BUY": "green",
    "BUY": "green",
    "NEUTRAL": "gray",
    "SELL": "red",
    "STRONG_SELL": "red",
}

SIGNAL_ORDER = {"STRONG_BUY": 0, "BUY": 1, "NEUTRAL": 2, "SELL": 3, "STRONG_SELL": 4}

INDICATOR_LABELS = {
    "RSI": "RSI",
    "MACD": "MACD",
    "Trend": "Trend",
    "Bollinger": "Bollinger",
    "Stochastic": "Stokastik",
    "OBV": "OBV (hacim)",
    "VWAP": "VWAP",
}

PROFILES: dict[str, dict[str, Any]] = {
    "Temkinli": {
        "min_confidence": 75,
        "max_drawdown": 5.0,
        "size_factor": 0.5,
        "description": "Düşük risk, yüksek onay eşiği. Sermayenin küçük bir bölümüyle işlem.",
    },
    "Dengeli": {
        "min_confidence": 60,
        "max_drawdown": 12.0,
        "size_factor": 1.0,
        "description": "Risk ve getiri dengesi. Standart pozisyon büyüklüğü.",
    },
    "Atak": {
        "min_confidence": 45,
        "max_drawdown": 25.0,
        "size_factor": 1.5,
        "description": "Yüksek risk, erken giriş. Pozisyon büyüklüğü artırılır.",
    },
}


def signal_label(signal: str) -> str:
    return SIGNAL_LABELS.get(signal, signal or "—")


def confidence(info: dict[str, Any], bt: dict[str, Any]) -> int:
    """
    0-100 arası 'sinyal güveni'.

    Bileşenler: sinyal pütünün gücü (%45), göstergelerin birbirini
    onaylaması (%25), backtest kazanma oranı (%15), backtest getirisi (%15).
    """
    score = abs(float(info.get("score", 0))) / 5.0 * 45.0

    details = list(info.get("details", {}).values())
    bull = sum("-> AL" in str(v) for v in details)
    bear = sum("-> SAT" in str(v) for v in details)
    total = bull + bear
    agreement = (max(bull, bear) / total * 25.0) if total else 0.0

    win_rate = min(float(bt.get("win_rate_pct", 0) or 0), 70.0)
    quality = win_rate / 70.0 * 15.0

    ret = float(bt.get("total_return_pct", 0) or 0)
    quality += 15.0 if ret > 0 else (7.0 if ret > -5 else 0.0)

    return int(max(0, min(100, round(score + agreement + quality))))


def _clean_detail(text: str) -> str:
    return str(text).replace("->", "→").strip()


def _factors(info: dict[str, Any]) -> tuple[list[str], list[str]]:
    pros: list[str] = []
    cons: list[str] = []
    for key, value in info.get("details", {}).items():
        text = _clean_detail(value)
        label = INDICATOR_LABELS.get(key, key)
        if "→ AL" in text:
            pros.append(f"**{label}:** {text}")
        elif "→ SAT" in text:
            cons.append(f"**{label}:** {text}")
    return pros, cons


def recommendation(
    info: dict[str, Any],
    bt: dict[str, Any],
    profile: str,
    risk: dict[str, Any],
) -> dict[str, Any]:
    """Risk profiline göre eyleme dönük öneri, gerekçe ve işlem parametreleri."""
    conf = confidence(info, bt)
    prof = PROFILES.get(profile, PROFILES["Dengeli"])
    signal = info.get("signal", "NEUTRAL")
    symbol = info.get("symbol", "—")
    drawdown = abs(float(bt.get("max_drawdown_pct", 0) or 0))

    bullish = signal in ("STRONG_BUY", "BUY")
    bearish = signal in ("STRONG_SELL", "SELL")
    conf_ok = conf >= int(prof["min_confidence"])
    risk_ok = drawdown <= float(prof["max_drawdown"])

    if bullish and conf_ok and risk_ok:
        action = "AL"
        tone = "success"
        headline = f"{symbol} için alım sinyali güven eşiğini geçti."
        rationale = (
            f"Güven skoru %{conf} ve geçmiş testteki maksimum düşüş %{drawdown:.1f}, "
            f"{profile.lower()} profilinin limitleriyle uyumlu."
        )
    elif bullish:
        action = "BEKLE"
        tone = "warning"
        reason = (
            f"güven skoru %{prof['min_confidence']} eşiğinin altında"
            if not conf_ok
            else f"maksimum düşüş %{drawdown:.1f}, profil limiti %{prof['max_drawdown']:.0f}'i aşıyor"
        )
        headline = f"{symbol} AL sinyali veriyor ancak şimdilik temkinli."
        rationale = f"Sinyal yönü olumlu; fakat {reason}. Onay için takip etmek daha uygun."
    elif bearish:
        action = "SAT / UZAK DUR"
        tone = "error" if conf_ok else "warning"
        headline = f"{symbol} için satış baskısı öne çıkıyor."
        rationale = (
            f"Göstergeler satış yönünde ve güven skoru %{conf}. "
            + ("Mevcut pozisyon için risk yönetimi önerilir." if conf_ok else "Güven eşiği düşük olduğundan doğrulama bekleyin.")
        )
    else:
        action = "İZLE"
        tone = "info"
        headline = f"{symbol} için net bir yön oluşmadı."
        rationale = (
            f"Güven skoru %{conf}. Göstergeler birbirini onaylamıyor; "
            "yeni bir sinyal gelene kadar pozisyon almak için acele edilmez."
        )

    entry = float(info.get("last_close", 0) or 0)
    stop_pct = float(risk.get("stop_loss_pct", 0.05))
    target_pct = float(risk.get("take_profit_pct", 0.10))
    size_pct = min(float(risk.get("position_size_pct", 0.10)) * float(prof["size_factor"]), 0.5)
    capital = float(risk.get("initial_capital", 100000))

    pros, cons = _factors(info)
    return {
        "action": action,
        "tone": tone,
        "headline": headline,
        "rationale": rationale,
        "confidence": conf,
        "pros": pros,
        "cons": cons,
        "entry": entry,
        "stop": round(entry * (1 - stop_pct), 2),
        "target": round(entry * (1 + target_pct), 2),
        "size_pct": round(size_pct * 100, 1),
        "amount": round(capital * size_pct, 2),
        "drawdown": round(drawdown, 2),
        "profile": profile,
    }


def market_summary(results: list[dict[str, Any]], profile: str) -> dict[str, Any]:
    """Taranan hisseler için üst düzey özet ve öne çıkan öneri."""
    valid = [r for r in results if "info" in r]
    buys = [r for r in valid if r["info"]["signal"] in ("STRONG_BUY", "BUY")]
    sells = [r for r in valid if r["info"]["signal"] in ("STRONG_SELL", "SELL")]
    neutrals = [r for r in valid if r["info"]["signal"] == "NEUTRAL"]
    errors = [r for r in results if "error" in r]

    ranked: list[tuple[int, dict[str, Any]]] = []
    for r in valid:
        ranked.append((confidence(r["info"], r["backtest"]), r))
    ranked.sort(key=lambda x: x[0], reverse=True)
    avg_conf = round(sum(c for c, _ in ranked) / len(ranked)) if ranked else 0

    pick = None
    for conf, r in ranked:
        if r["info"]["signal"] in ("STRONG_BUY", "BUY"):
            rec = recommendation(r["info"], r["backtest"], profile, {})
            if rec["action"] == "AL":
                pick = {"symbol": r["info"]["symbol"], "confidence": conf, "info": r["info"]}
                break

    return {
        "total": len(valid),
        "buy_count": len(buys),
        "sell_count": len(sells),
        "neutral_count": len(neutrals),
        "error_count": len(errors),
        "avg_confidence": avg_conf,
        "ranked": ranked,
        "pick": pick,
    }


def allocation_plan(
    results: list[dict[str, Any]], profile: str, risk: dict[str, Any]
) -> list[dict[str, Any]]:
    """Profile uygun AL sinyallerinden kurgusal (paper) dağılım planı oluşturur."""
    prof = PROFILES.get(profile, PROFILES["Dengeli"])
    candidates: list[dict[str, Any]] = []
    for r in results:
        if "info" not in r:
            continue
        info, bt = r["info"], r["backtest"]
        rec = recommendation(info, bt, profile, risk)
        if rec["action"] == "AL":
            candidates.append(
                {
                    "symbol": info["symbol"],
                    "signal": signal_label(info["signal"]),
                    "confidence": rec["confidence"],
                    "amount": rec["amount"],
                    "stop": rec["stop"],
                    "target": rec["target"],
                }
            )

    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    max_positions = int(risk.get("max_positions", 5))
    candidates = candidates[:max_positions]
    if not candidates:
        return []

    total_conf = sum(c["confidence"] for c in candidates) or 1
    capital = float(risk.get("initial_capital", 100000))
    for c in candidates:
        weight = c["confidence"] / total_conf
        c["weight_pct"] = round(weight * 100, 1)
        c["allocated"] = round(capital * weight, 2)
    return candidates
