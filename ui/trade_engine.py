"""
AL / BEKLE / SAT karar motoru.

Girdiler:
- borsapy teknik sinyalleri (9 zaman dilimi),
- KAP / şirket haberleri,
- anlık fiyat ve risk ayarları.

Çıktı: yön, güven skoru, gerekçeler, stop/hedef ve pozisyon önerisi.
Not: Bu bir karar destek aracıdır; aracı kuruma emir göndermez.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from ui.live_data import STRATEGIES


REC_VALUE = {
    "STRONG_BUY": 2, "BUY": 1, "NEUTRAL": 0, "SELL": -1, "STRONG_SELL": -2,
    "GÜÇLÜ AL": 2, "AL": 1, "NÖTR": 0, "SAT": -1, "GÜÇLÜ SAT": -2,
}
REC_LABEL = {
    2: "Güçlü AL", 1: "AL", 0: "Nötr", -1: "SAT", -2: "Güçlü SAT",
}
DECISION_COLOR = {"AL": "green", "SAT": "red", "BEKLE": "orange"}
DECISION_ICON = {
    "AL": ":material/trending_up:",
    "SAT": ":material/trending_down:",
    "BEKLE": ":material/pause_circle:",
}

# KAP bildirim başlıklarında geçen ifadelerin yön ağırlıkları
BULLISH_WORDS = {
    "pay alım": 3, "alım": 2, "geri alım": 2, "olumsuz değil": 1, "olumlu": 3,
    "kâr": 2, "kar": 2, "büyüme": 2, "artış": 2, "yükseltme": 3, "yükseliş": 2,
    "ihale": 2, "sözleşme": 2, "anlaşma": 2, "yatırım": 2, "rekor": 3,
    "temettü": 2, "kâr payı": 2, "kar payı": 2, "satın alma": 2, "birleşme": 2,
    "onay": 1, "izin": 1, "finansman": 1, "hedef fiyat": 2, "tavsiye": 1,
    "verim": 1, "başarı": 2, "genişleme": 2,
}
BEARISH_WORDS = {
    "pay satım": -3, "satım": -2, "zarar": -3, "düşüş": -2, "azalış": -2,
    "uyarı": -3, "inceleme": -2, "yasağı": -3, "ceza": -3, "dava": -2,
    "risk": -1, "iptal": -2, "askı": -2, "sermaye artırımı": -2, "arz": -2,
    "iflas": -4, "borç": -1, "kötü": -2, "olumsuz": -3, "yavaşlama": -2,
    "daralma": -2, "kar realizasyonu": -1, "satkı": -1, "düşük": -1,
    "tehdit": -2, "engel": -2, "red": -2,
}


def _headline_score(title: str) -> float:
    """Başlıktaki olumlu/olumsuz ifadelerden -4..+4 arası ham puan."""
    text = f" {title.lower()} "
    score = 0.0
    for word, weight in BULLISH_WORDS.items():
        if word in text:
            score += weight
    for word, weight in BEARISH_WORDS.items():
        if word in text:
            score += weight
    # "Pay Alım Satım Bildirimi" yön belirtmediği için nötr kabul edilir
    if "pay alım satım" in text or "alım satım bildirimi" in text:
        return 0.0
    return max(-4.0, min(4.0, score))


def _parse_news_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def analyze_news(news: pd.DataFrame | None) -> dict[str, Any]:
    """Haberleri skorlar; güncellik etkisiyle toplam duyarım puanı üretir."""
    if news is None or getattr(news, "empty", True):
        return {"score": 0.0, "items": []}

    now = datetime.now()
    items: list[dict[str, Any]] = []
    for _, row in news.iterrows():
        title = str(row.get("Title", "")).strip()
        if not title:
            continue
        raw = _headline_score(title)
        when = _parse_news_date(row.get("Date"))
        age_days = max(0.0, (now - when).days) if when else 15.0
        recency = max(0.15, 1.0 - age_days / 30.0)
        contribution = raw * recency
        items.append(
            {
                "title": title,
                "date": str(row.get("Date", "")),
                "url": str(row.get("URL", "")),
                "raw": round(raw, 2),
                "impact": round(contribution, 2),
                "tone": "positive" if raw > 0 else "negative" if raw < 0 else "neutral",
            }
        )

    raw_total = sum(i["impact"] for i in items)
    score = max(-1.0, min(1.0, raw_total / 6.0))
    return {"score": round(score, 3), "items": items}


def analyze_technical(signals: dict[str, Any], strategy: str) -> dict[str, Any]:
    """Zaman dilimlerini strateji ağırlığıyla birleştirir."""
    weights = STRATEGIES.get(strategy, STRATEGIES["Dengeli"])
    technical: list[dict[str, Any]] = []
    weighted = 0.0
    total_weight = 0.0
    buy_votes = sell_votes = neutral_votes = 0

    for tf, weight in weights.items():
        block = (signals or {}).get(tf) or {}
        summary = block.get("summary", {})
        rec = str(summary.get("recommendation", "NEUTRAL")).upper()
        value = REC_VALUE.get(rec, 0)
        buy = int(summary.get("buy", 0) or 0)
        sell = int(summary.get("sell", 0) or 0)
        neutral = int(summary.get("neutral", 0) or 0)
        weighted += weight * value
        total_weight += weight
        buy_votes += buy
        sell_votes += sell
        neutral_votes += neutral
        technical.append(
            {
                "timeframe": tf,
                "recommendation": REC_LABEL.get(value, rec),
                "value": value,
                "buy": buy,
                "sell": sell,
                "neutral": neutral,
                "weight": weight,
            }
        )

    score = (weighted / total_weight / 2.0) if total_weight else 0.0
    total_votes = buy_votes + sell_votes + neutral_votes
    consensus = max(buy_votes, sell_votes) / total_votes if total_votes else 0.0
    return {
        "score": round(score, 3),
        "timeframes": technical,
        "consensus": round(consensus, 3),
        "buy_votes": buy_votes,
        "sell_votes": sell_votes,
        "neutral_votes": neutral_votes,
        "oscillators": (((signals or {}).get("1d") or {}).get("oscillators", {}).get("values", {}) or {}),
    }


def build_decision(
    snap: dict[str, Any],
    strategy: str,
    risk: dict[str, Any],
    news_weight: float = 0.25,
) -> dict[str, Any]:
    """Anlık görüntüden kullanıcıya gösterilecek kararı üretir."""
    info = snap.get("info", {}) or {}
    price = float(info.get("price") or 0)
    tech = analyze_technical(snap.get("signals", {}), strategy)
    news = analyze_news(snap.get("news"))

    final = 0.75 * tech["score"] + float(news_weight) * news["score"]
    final = max(-1.0, min(1.0, final))
    decision = "AL" if final >= 0.35 else "SAT" if final <= -0.35 else "BEKLE"

    confidence = int(max(5, min(100, round(abs(final) * 70 + tech["consensus"] * 30))))

    stop_pct = float(risk.get("stop_loss_pct", 0.05))
    target_pct = float(risk.get("take_profit_pct", 0.10))
    size_pct = float(risk.get("position_size_pct", 0.10))
    capital = float(risk.get("initial_capital", 100000))

    direction = 1 if decision == "AL" else -1 if decision == "SAT" else 0
    stop = round(price * (1 - direction * stop_pct), 2) if direction else None
    target = round(price * (1 + direction * target_pct), 2) if direction else None

    intraday = snap.get("intraday")
    volatility = None
    if intraday is not None and not getattr(intraday, "empty", True) and price:
        tail = intraday.tail(20)
        if {"High", "Low"}.issubset(tail.columns):
            volatility = round(float((tail["High"] - tail["Low"]).mean()) / price * 100, 2)

    reasons: list[dict[str, str]] = []
    for item in tech["timeframes"]:
        if item["value"]:
            reasons.append(
                {
                    "source": f"Teknik {item['timeframe']}",
                    "text": f"{REC_LABEL[item['value']]} · al {item['buy']} / sat {item['sell']}",
                    "tone": "positive" if item["value"] > 0 else "negative",
                }
            )
    for item in news["items"]:
        if item["raw"]:
            reasons.append(
                {
                    "source": "KAP haberi",
                    "text": f"{item['title'][:80]} → {'olumlu' if item['raw'] > 0 else 'olumsuz'}",
                    "tone": item["tone"],
                }
            )

    return {
        "decision": decision,
        "confidence": confidence,
        "score": round(final, 3),
        "technical": tech,
        "news": news,
        "reasons": reasons,
        "price": price,
        "change_pct": round(float(info.get("change_pct") or 0), 2),
        "volume": info.get("volume"),
        "volatility_pct": volatility,
        "stop": stop,
        "target": target,
        "position_pct": round(size_pct * 100, 1),
        "amount": round(capital * size_pct, 2),
        "symbol": snap.get("symbol"),
        "name": snap.get("name"),
        "fetched_at": snap.get("fetched_at"),
        "errors": snap.get("errors", []),
        "strategy": strategy,
    }
