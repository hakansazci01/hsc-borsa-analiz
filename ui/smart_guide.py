"""
Akıllı rehber: piyasa rejimini sade dille yorumlar ve hangi yöntemin
kullanılacağını önerir. Mevcut karar motorlarının yerine geçmez;
kullanıcıyı doğru araca yönlendirir ve teknik veriyi sadeleştirir.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


REGIME_GUIDE: dict[str, dict[str, str]] = {
    "Yükseliş": {
        "tone": "buy",
        "chip": "🟢",
        "headline": "Piyasa yükseliş eğiliminde",
        "method": "Ana trend yönünde planlı alım",
        "page": "app_pages/ajans.py",
        "page_label": "İşlem ajansını aç",
        "why": "Fiyat ana ortalamaların üzerinde ve momentum pozitif. Trendle aynı yöndeki planlı alımlar daha anlamlıdır.",
        "risk": "Normal pozisyon büyüklüğü; hedef 2.5R, stop ATR tabanlı.",
    },
    "Düşüş": {
        "tone": "sell",
        "chip": "🔴",
        "headline": "Piyasa düşüş eğiliminde",
        "method": "Yeni alım yok, mevcut riski gözden geçir",
        "page": "app_pages/risk.py",
        "page_label": "Risk merkezini aç",
        "why": "Fiyat ana ortalamaların altında ve momentum negatif. Dipsizde alım denemek yerine risk yönetimi öne çıkar.",
        "risk": "Kurgusal pozisyonların stop seviyelerini kontrol edin; boyutu küçültün.",
    },
    "Yatay": {
        "tone": "wait",
        "chip": "🟡",
        "headline": "Piyasa yatay / yönsüz",
        "method": "Kısa vadeli tetikleyici ara",
        "page": "app_pages/anlik.py",
        "page_label": "Anlık sinyali aç",
        "why": "Net bir yön yok; günlük sinyaller sık değişir. Anlık tetikleyicilerle küçük ve hızlı işlemler daha uygun olabilir.",
        "risk": "Küçük pozisyon, sıkı stop; sinyal zayıfsa BEKLE.",
    },
    "Yüksek oynaklık": {
        "tone": "volatile",
        "chip": "🟠",
        "headline": "Piyasa hareketli / oynak",
        "method": "Pozisyonu küçült, kısa vadeli yaklaş",
        "page": "app_pages/anlik.py",
        "page_label": "Anlık sinyali aç",
        "why": "Fiyat sert ve hızlı hareket ediyor. Stop mesafeleri genişler, aynı sermaye daha fazla riske girer.",
        "risk": "Yarım boyut kullanın; ATR tabanlı stop ve 1.5R hedef daha gerçekçidir.",
    },
}

_FALLBACK: dict[str, Any] = {
    "regime": "Yatay",
    "regime_key": "range",
    "confidence": 0,
    "trend_score": 0.0,
    "advice": "Piyasa verisine ulaşılamadı; temkinli olun.",
}


@st.cache_data(ttl="30m", show_spinner=False)
def market_regime() -> dict[str, Any]:
    """BIST 100 üzerinden piyasa rejimini döndürür (30 dk önbellekli)."""
    try:
        from ui.risk_engine import detect_regime

        return detect_regime("XU100")
    except Exception:
        return dict(_FALLBACK)


def guide_for(regime: dict[str, Any]) -> dict[str, Any]:
    """Rejime uygun yöntem önerisini döndürür."""
    name = str(regime.get("regime", "Yatay"))
    return dict(REGIME_GUIDE.get(name, REGIME_GUIDE["Yatay"]))


def plain_summary(rec: dict[str, Any], info: dict[str, Any], regime: dict[str, Any]) -> str:
    """Teknik öneriyi kullanıcının anlayacağı 2 cümleye indirger."""
    from ui.insights import signal_label

    action = str(rec.get("action", "İZLE"))
    confidence = int(rec.get("confidence", 0) or 0)
    signal = signal_label(str(info.get("signal", "NEUTRAL")))
    regime_name = str(regime.get("regime", "Yatay"))

    if action == "AL":
        first = f"Göstergeler çoğunlukla **{signal}** yönünde ve güven skoru **%{confidence}** ile eşiği geçti."
        second = f"Piyasa **{regime_name}**; bu ortamda planlı bir alım denemek mantıklı."
    elif action.startswith("SAT"):
        first = f"Göstergeler **{signal}** yönünde; güven skoru **%{confidence}**."
        second = "Bu, yeni alım için uygun bir zaman değil; varsa kurgusal pozisyonun riskini gözden geçirin."
    elif action == "BEKLE":
        first = f"Sinyal olumlu olsa da güven skoru **%{confidence}** eşiğin altında veya risk limiti aşıldı."
        second = "Şimdi girmek yerine teyit beklemek daha güvenli; acele edilmez."
    else:
        first = f"Göstergeler birbirini onaylamıyor; sinyal **{signal}**, güven **%{confidence}**."
        second = "Net bir yön oluşana kadar kurgusal pozisyon açmak için acele edilmez."

    return f"{first} {second}"


def top_pick(settings: dict[str, Any], regime: dict[str, Any]) -> dict[str, Any] | None:
    """İzleme listesinden 'Bugün ne yapmalı?' sorusuna tek bir öneri üretir."""
    from ui.core import analysis_args, scan_market
    from ui.insights import market_summary, recommendation

    symbols = tuple((settings.get("symbols") or [])[:8])
    if not symbols:
        return {
            "status": "empty",
            "plain": "İzleme listeniz boş. Ayarlar sayfasından birkaç BIST hissesi ekleyin.",
        }
    args = analysis_args(settings)
    try:
        results = list(
            scan_market(
                symbols, args["period"], args["interval"], args["indicators"],
                args["weights"], args["thresholds"], args["risk"],
                args["backtest_cfg"], args["guards"],
            )
        )
    except Exception:
        return None

    valid = [r for r in results if "info" in r and "backtest" in r]
    if not valid:
        return None
    summary = market_summary(valid, str(settings.get("profile", "Dengeli")))
    pick = summary.get("pick")
    if not pick:
        return {
            "status": "none",
            "plain": (
                "İzleme listenizde bugün güven eşiğini geçen net bir alım adayı yok. "
                "Böyle günlerde **BEKLE** en mantıklı karardır; sinyaller zayıflaşırken "
                "yeni pozisyon açmak yerine mevcut planı korumak daha iyidir."
            ),
        }
    selected = next(
        (r for r in valid if r["info"].get("symbol") == pick.get("symbol")), None
    )
    if not selected:
        return {
            "status": "none",
            "plain": "İzleme listenizde bugün güven eşiğini geçen net bir alım adayı yok; **BEKLE** uygun.",
        }
    rec = recommendation(
        selected["info"], selected["backtest"],
        str(settings.get("profile", "Dengeli")), settings.get("risk", {}),
    )
    return {
        "status": "ok",
        "symbol": pick["symbol"],
        "info": selected["info"],
        "backtest": selected["backtest"],
        "recommendation": rec,
        "plain": plain_summary(rec, selected["info"], regime),
    }
