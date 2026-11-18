"""
Sinyal güvenilirlik denetimi.

Gerçek para ile işlem öncesi hata payını ölçmek için:
- backtest istatistiksel anlamlılığı (Wilson güven aralığı, profit factor, beklenti),
- kayma (slippage) duyarlılığı,
- veri tazeliği / seans durumu,
- sinyal onayı (zaman dilimi uzlaşısı),
- gerçek para için hazırlık kontrol listesi.

Bu modül "hazırım" demek için değil, riski görünür kılmak içindir.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Kazanma oranı için %95 Wilson güven aralığı (0-100)."""
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, (center - margin) * 100), min(100.0, (center + margin) * 100))


def backtest_report(bt: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    exits = [
        t for t in bt.get("trades", [])
        if str(t.get("type", "")).startswith("EXIT") and "pnl_pct" in t
    ]
    pnls = [float(t["pnl_pct"]) for t in exits]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    gross_win = sum(p for p in pnls if p > 0)
    gross_loss = abs(sum(p for p in pnls if p < 0))
    pf = (gross_win / gross_loss) if gross_loss else (float("inf") if gross_win else 0.0)
    expectancy = (sum(pnls) / n) if n else 0.0
    low, high = wilson_interval(wins, n)

    if n < 10:
        sample = "Yetersiz (<10 işlem)"
    elif n < 30:
        sample = "Düşük (10-29 işlem)"
    elif n < 100:
        sample = "Orta (30-99 işlem)"
    else:
        sample = "Görece yeterli (100+ işlem)"

    base_slip = float(risk.get("slippage_pct", 0.001))
    sensitivity = []
    for slip in (0.0, 0.001, 0.003, 0.005):
        # giriş ve çıkışta toplam ~2 * kayma
        adjusted = expectancy - 2 * slip * 100
        sensitivity.append(
            {
                "Kayma %": round(slip * 100, 2),
                "Beklenti / işlem %": round(adjusted, 3),
                "Yorum": "pozitif" if adjusted > 0 else "negatif",
            }
        )

    return {
        "trades": n,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wins / n * 100, 1) if n else 0.0,
        "ci_low": round(low, 1),
        "ci_high": round(high, 1),
        "profit_factor": round(pf, 2) if math.isfinite(pf) else None,
        "expectancy_pct": round(expectancy, 3),
        "sample_verdict": sample,
        "sensitivity": sensitivity,
        "base_slippage_pct": round(base_slip * 100, 2),
        "total_return_pct": bt.get("total_return_pct"),
        "max_drawdown_pct": bt.get("max_drawdown_pct"),
        "verdict": (
            "Negatif beklenti — bu strateji bu hisse için işlem önerisi üretmemeli."
            if expectancy <= 0
            else "Pozitif beklenti, ancak örneklem ve veri gecikmesi nedeniyle tek başına yeterli değil."
        ),
    }


def data_quality_report(snap: dict[str, Any]) -> dict[str, Any]:
    info = snap.get("info", {}) or {}
    source = str(snap.get("quote_source", ""))
    session = str(info.get("session") or "unknown")
    quote_time = info.get("quote_time")
    age = None
    if quote_time:
        for fmt in ("%d.%m.%Y %H:%M:%S",):
            try:
                age = (datetime.now() - datetime.strptime(str(quote_time), fmt)).total_seconds() / 60
                break
            except ValueError:
                continue

    if age is None:
        freshness = "Bilinmiyor"
    elif age <= 5:
        freshness = "Taze"
    elif age <= 20:
        freshness = "Gecikmeli"
    else:
        freshness = "Bayat"

    warnings = []
    if session not in ("regular", "open"):
        warnings.append("Seans kapalı: görülen fiyat son kotasyondur, anlık işlem sinyali olarak kullanılamaz.")
    if "WebSocket" not in source:
        warnings.append("Canlı akış yok; yedek fiyat kaynağı kullanılıyor.")
    warnings.append("Ücretsiz BIST akışı ~15 dakika gecikmelidir; gerçek zamanlı değildir.")
    if freshness == "Bayat":
        warnings.append("Kotasyon çok eski; sinyal güncel fiyatı yansıtmıyor.")

    return {
        "source": source or "—",
        "session": session,
        "quote_time": quote_time or "—",
        "age_minutes": round(age, 1) if age is not None else None,
        "freshness": freshness,
        "tradeable_session": session in ("regular", "open"),
        "warnings": warnings,
    }


def signal_quality_report(decision: dict[str, Any], regime: dict[str, Any] | None) -> dict[str, Any]:
    tech = decision.get("technical", {})
    buy = int(tech.get("buy_votes", 0))
    sell = int(tech.get("sell_votes", 0))
    neutral = int(tech.get("neutral_votes", 0))
    total = buy + sell + neutral
    consensus = max(buy, sell) / total if total else 0.0

    news = decision.get("news", {})
    items = news.get("items", [])
    directional = sum(1 for i in items if abs(float(i.get("raw", 0))) > 0)
    news_reliability = (directional / len(items) * 100) if items else 0.0

    score = 0.0
    score += consensus * 45
    score += min(abs(float(decision.get("score", 0))), 1) * 30
    score += min(float(decision.get("confidence", 0)), 100) / 100 * 15
    score += (regime["confidence"] / 100 * 10) if regime else 4
    score = int(max(0, min(100, round(score))))

    warnings = []
    if consensus < 0.6:
        warnings.append("Zaman dilimleri arasında uzlaşı zayıf; sinyal gürültüye açık.")
    if total < 30:
        warnings.append("Teknik oy sayısı düşük; göstergeler çelişkili olabilir.")
    if news_reliability < 20:
        warnings.append("Haber çoğunlukla bilgilendirme içeriyor; duyarım etkisi sınırlı.")
    if regime and regime["regime"] in ("Yüksek oynaklık", "Düşüş"):
        warnings.append("Rejim riski yüksek; sistem pozisyonu azalttı veya BEKLE'ye çevirdi.")

    return {
        "score": score,
        "consensus_pct": round(consensus * 100, 1),
        "buy_votes": buy,
        "sell_votes": sell,
        "neutral_votes": neutral,
        "news_items": len(items),
        "news_directional_pct": round(news_reliability, 1),
        "warnings": warnings,
    }


def readiness_check(
    bt_report: dict[str, Any],
    dq: dict[str, Any],
    sq: dict[str, Any],
) -> dict[str, Any]:
    """Gerçek para kullanımı için kontrol listesi. Varsayılan sonuç: ONAYLANMADI."""
    items = [
        {
            "Kontrol": "Gerçek zamanlı / lisanslı veri",
            "Durum": "BAŞARISIZ",
            "Detay": "Ücretsiz kaynak ~15 dk gecikmeli; BIST resmi gerçek zamanlı veri lisanslı aracı kurum API'si gerektirir.",
        },
        {
            "Kontrol": "Seans açık ve kotasyon taze",
            "Durum": "GEÇİLİ" if dq["tradeable_session"] and dq["freshness"] in ("Taze", "Gecikmeli") else "BAŞARISIZ",
            "Detay": f"Seans: {dq['session']}, kotasyon yaşı: {dq['age_minutes']} dk, tazelik: {dq['freshness']}.",
        },
        {
            "Kontrol": "İstatistiksel örneklem",
            "Durum": "GEÇİLİ" if bt_report["trades"] >= 100 else "BAŞARISIZ",
            "Detay": f"{bt_report['trades']} işlem; değerlendirme: {bt_report['sample_verdict']}. Kazanma oranı %95 CI: %{bt_report['ci_low']}-{bt_report['ci_high']}.",
        },
        {
            "Kontrol": "Pozitif beklenti (maliyetler sonrası)",
            "Durum": "GEÇİLİ" if bt_report["expectancy_pct"] > 0 else "BAŞARISIZ",
            "Detay": f"Beklenti {bt_report['expectancy_pct']:+.3f}% / işlem; önerilen kaymada {bt_report['base_slippage_pct']:.2f}%.",
        },
        {
            "Kontrol": "Kayma/komisyon dayanıklılığı",
            "Durum": "GEÇİLİ" if all(r["Beklenti / işlem %"] > 0 for r in bt_report["sensitivity"]) else "BAŞARISIZ",
            "Detay": "Kayma senaryolarında beklentinin pozitif kalması gerekir.",
        },
        {
            "Kontrol": "Sinyal uzlaşısı",
            "Durum": "GEÇİLİ" if sq["consensus_pct"] >= 60 else "BAŞARISIZ",
            "Detay": f"Zaman dilimi uzlaşısı %{sq['consensus_pct']}.",
        },
        {
            "Kontrol": "Walk-forward / out-of-sample doğrulama",
            "Durum": "BAŞARISIZ",
            "Detay": "Bu sürümde parametreler geçmişe göre optimize edilmedi; ayrı bir doğrulama çalışması gerekir.",
        },
        {
            "Kontrol": "Aracı kurum emir iletimi ve test",
            "Durum": "BAŞARISIZ",
            "Detay": "Uygulama emir göndermez. Gerçek emir için kurum API'si, kimlik bilgileri ve test ortamı gerekir.",
        },
        {
            "Kontrol": "Kağıt üzerinde ilerleme kaydı",
            "Durum": "BAŞARISIZ",
            "Detay": "En az 50-100 kurgusal işlem boyunca canlı sinyallerin kaydedilip karşılaştırılması gerekir.",
        },
    ]
    passed = sum(1 for i in items if i["Durum"] == "GEÇİLİ")
    return {
        "items": items,
        "passed": passed,
        "total": len(items),
        "approved": False,
        "headline": "GERÇEK PARA İÇİN ONAYLANMADI",
        "summary": (
            f"{passed}/{len(items)} kontrol geçti. Eksik kontroller nedeniyle bu sistem tek başına "
            "gerçek para ile işlem kararı için kullanılamaz. Kağıt işlem + lisanslı veri + kurum API'si zorunludur."
        ),
    }
