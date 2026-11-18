"""
Akıllı Risk & Rejim Motoru.

Kurumsal sistemlerde ortak olan dört bileşeni tek çatıda birleştirir:
1) Piyasa rejimi tespiti (trend + volatilite kümelemesi),
2) Rejime uyarlanmış karar ve pozisyon ayarı,
3) Kesirli Kelly kriteri ile riske dayalı pozisyon boyutu (sert tavanlı),
4) Monte Carlo bootstrap ile olasılıksal risk projeksiyonu (VaR / CVaR / zarar olasılığı),
5) Portföy korelasyonu ve risk katkısı.

Tamamı açıklanabilir (shallow ML / istatistik) ve harici model gerektirmez.
Yatırım tavsiyesi değildir; emir göndermez.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from ui.live_data import normalize_symbol


REGIME_LABELS = {
    "bull": "Yükseliş",
    "bear": "Düşüş",
    "range": "Yatay",
    "volatile": "Yüksek oynaklık",
}
REGIME_COLORS = {
    "Yükseliş": "green", "Düşüş": "red", "Yatay": "gray", "Yüksek oynaklık": "orange",
}
REGIME_ICONS = {
    "Yükseliş": ":material/trending_up:",
    "Düşüş": ":material/trending_down:",
    "Yatay": ":material/straighten:",
    "Yüksek oynaklık": ":material/bolt:",
}
REGIME_FACTORS = {
    "Yükseliş": {
        "confidence": 1.10, "size": 1.15,
        "note": "Trend rejiminde yön sinyalleri daha güvenilir; pozisyon modest artırılabilir.",
    },
    "Düşüş": {
        "confidence": 0.75, "size": 0.50,
        "note": "Düşüş rejiminde AL sinyalleri zayıftır; pozisyon azaltılmalı, SAT sinyalleri öne çıkar.",
    },
    "Yatay": {
        "confidence": 0.90, "size": 0.85,
        "note": "Yatay rejimde trend sinyalleri gürültüye dönüşebilir; aralık (ortalamaya dönüş) stratejisi uygundur.",
    },
    "Yüksek oynaklık": {
        "confidence": 0.70, "size": 0.50,
        "note": "Yüksek oynaklıkta stop mesafeleri genişler; sermaye riski yarıya indirilmelidir.",
    },
}


def _kmeans_1d(values: np.ndarray, seed: int = 7, iters: int = 40) -> tuple[np.ndarray, np.ndarray] | None:
    """Tek boyutlu 2-kümeli k-means (hafif, bağımlılıksız HMM benzeri rejim ayrımı)."""
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 30:
        return None
    centers = np.percentile(x, [25, 75]).astype(float)
    for _ in range(iters):
        labels = np.abs(x[:, None] - centers[None, :]).argmin(axis=1)
        new_centers = np.array([
            x[labels == i].mean() if np.any(labels == i) else centers[i]
            for i in range(2)
        ])
        if np.allclose(new_centers, centers):
            centers = new_centers
            break
        centers = new_centers
    order = np.argsort(centers)
    centers = centers[order]
    labels = np.abs(x[:, None] - centers[None, :]).argmin(axis=1)
    return centers, labels


@st.cache_data(ttl="300s", max_entries=100, show_spinner=False)
def detect_regime(symbol: str) -> dict[str, Any]:
    """Sembol için günlük veriden piyasa rejimini ve güvenini çıkarır."""
    import borsapy as bp

    sym = normalize_symbol(symbol)
    df = bp.Ticker(sym).history(period="1y", interval="1d")
    if df is None or df.empty or "Close" not in df.columns:
        raise ValueError(f"{sym}: rejim tespiti için geçerli fiyat verisi bulunamadı.")
    close = df["Close"].astype(float)
    ret = close.pct_change()
    vol_series = (ret.rolling(21).std() * np.sqrt(252)).dropna()
    if len(vol_series) < 60:
        raise ValueError(f"{sym}: rejim tespiti için yeterli veri yok.")

    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    last_close = float(close.iloc[-1])
    last_sma50 = float(sma50.iloc[-1]) if np.isfinite(sma50.iloc[-1]) else last_close
    last_sma200 = float(sma200.iloc[-1]) if np.isfinite(sma200.iloc[-1]) else last_close
    slope50 = float(sma50.iloc[-1] / sma50.iloc[-21] - 1) if len(sma50) > 21 and np.isfinite(sma50.iloc[-21]) else 0.0
    mom20 = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else 0.0
    vol = float(vol_series.iloc[-1])

    # Trend puanı: sıralama + eğim + momentum (-2..+2)
    structure = 1 if last_close > last_sma50 > last_sma200 else (-1 if last_close < last_sma50 < last_sma200 else 0)
    trend_score = structure + float(np.clip(slope50 * 12, -1, 1)) + float(np.clip(mom20 * 5, -1, 1))

    vol_result = _kmeans_1d(vol_series.tail(252).to_numpy())
    if vol_result:
        centers, labels = vol_result
        high_vol = bool(labels[-1] == 1)
        separation = float(centers[1] - centers[0]) / max(float(vol_series.std()), 1e-9)
        vol_confidence = float(np.clip(separation, 0, 3)) / 3
    else:
        high_vol = vol > float(vol_series.median())
        vol_confidence = 0.3

    if high_vol:
        regime = "volatile"
    elif trend_score > 0.8:
        regime = "bull"
    elif trend_score < -0.8:
        regime = "bear"
    else:
        regime = "range"

    trend_strength = min(1.0, abs(trend_score) / 2.0)
    confidence = int(round(np.clip(50 + trend_strength * 35 + vol_confidence * 15, 50, 98)))

    return {
        "symbol": sym,
        "regime": REGIME_LABELS[regime],
        "regime_key": regime,
        "confidence": confidence,
        "trend_score": round(trend_score, 2),
        "momentum_20d_pct": round(mom20 * 100, 2),
        "slope_50d_pct": round(slope50 * 100, 2),
        "volatility_annual_pct": round(vol * 100, 1),
        "vol_high": high_vol,
        "vol_low_center": round(float(vol_result[0][0] * 100), 1) if vol_result else None,
        "vol_high_center": round(float(vol_result[0][1] * 100), 1) if vol_result else None,
        "history": vol_series.tail(120).to_numpy(),
        "advice": REGIME_FACTORS[REGIME_LABELS[regime]]["note"],
    }


def adjust_decision_for_regime(decision: dict[str, Any], regime: dict[str, Any]) -> dict[str, Any]:
    """Rejim bilgisini canlı AL/BEKLE/SAT kararına uyarlar."""
    name = regime["regime"]
    factor = REGIME_FACTORS[name]
    confidence = int(max(5, min(100, round(decision["confidence"] * factor["confidence"]))))
    position_pct = round(decision["position_pct"] * factor["size"], 1)
    adjusted_decision = decision["decision"]

    if name in ("Düşüş", "Yüksek oynaklık") and adjusted_decision == "AL" and confidence < 60:
        adjusted_decision = "BEKLE"

    return {
        **decision,
        "decision": adjusted_decision,
        "confidence": confidence,
        "position_pct": position_pct,
        "amount": round(decision.get("amount", 0) * factor["size"], 2),
        "regime": name,
        "regime_confidence": regime["confidence"],
        "regime_advice": regime["advice"],
    }


def kelly_sizing(bt: dict[str, Any], risk: dict[str, Any]) -> dict[str, Any]:
    """Backtest işlemlerinden kesirli Kelly ile risk ve pozisyon önerisi hesaplar."""
    exits = [
        t for t in bt.get("trades", [])
        if str(t.get("type", "")).startswith("EXIT") and "pnl_pct" in t
    ]
    wins = [float(t["pnl_pct"]) / 100 for t in exits if float(t.get("pnl_pct", 0)) > 0]
    losses = [float(t["pnl_pct"]) / 100 for t in exits if float(t.get("pnl_pct", 0)) < 0]

    if len(exits) < 3 or not wins or not losses:
        return {"available": False, "reason": "Kelly için en az 3 kapanmış işlem ve hem kazanan hem kaybeden işlem gerekir."}

    win_rate = len(wins) / len(exits)
    avg_win = float(np.mean(wins))
    avg_loss = abs(float(np.mean(losses)))
    payoff = avg_win / avg_loss if avg_loss > 0 else 0.0
    kelly = win_rate - (1 - win_rate) / payoff if payoff > 0 else 0.0
    kelly = float(np.clip(kelly, 0, 0.30))
    half_kelly = kelly / 2
    hard_cap = 0.02  # işlem başına en fazla %2 sermaye riski (kurumsal yaygın uygulama)
    suggested_risk = min(half_kelly, hard_cap)
    stop_dist = max(float(risk.get("stop_loss_pct", 0.05)), 0.01)
    capital = float(risk.get("initial_capital", 100000))
    position_fraction = min(suggested_risk / stop_dist, float(risk.get("position_size_pct", 0.10)) * 1.5)
    max_positions = max(int(risk.get("max_positions", 5)), 1)
    position_fraction = min(position_fraction, 1.0 / max_positions)

    return {
        "available": True,
        "trades": len(exits),
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_win_pct": round(avg_win * 100, 2),
        "avg_loss_pct": round(-avg_loss * 100, 2),
        "payoff_ratio": round(payoff, 2),
        "expectancy_pct": round((win_rate * avg_win - (1 - win_rate) * avg_loss) * 100, 2),
        "kelly_pct": round(kelly * 100, 2),
        "half_kelly_pct": round(half_kelly * 100, 2),
        "hard_cap_pct": hard_cap * 100,
        "suggested_risk_pct": round(suggested_risk * 100, 2),
        "suggested_position_pct": round(position_fraction * 100, 1),
        "suggested_amount": round(capital * position_fraction, 2),
        "current_position_pct": round(float(risk.get("position_size_pct", 0.10)) * 100, 1),
    }


def monte_carlo(
    bt: dict[str, Any],
    risk: dict[str, Any],
    simulations: int = 2000,
    seed: int = 42,
) -> dict[str, Any] | None:
    """İşlem getirilerini bootstrap ile yeniden örnekleyip sermaye dağılımı üretir."""
    pnls = np.array([
        float(t["pnl_pct"]) / 100
        for t in bt.get("trades", [])
        if str(t.get("type", "")).startswith("EXIT") and "pnl_pct" in t
    ])
    if len(pnls) < 3:
        return None

    rng = np.random.default_rng(seed)
    size = float(risk.get("position_size_pct", 0.10))
    finals = np.empty(simulations, dtype=float)
    worst_dds = np.empty(simulations, dtype=float)
    n = len(pnls)

    for i in range(simulations):
        sample = rng.choice(pnls, size=n, replace=True)
        equity = 1.0
        peak = 1.0
        mdd = 0.0
        for p in sample:
            equity *= max(0.01, 1 + p * size)
            peak = max(peak, equity)
            mdd = min(mdd, equity / peak - 1)
        finals[i] = equity
        worst_dds[i] = mdd

    p5 = float(np.percentile(finals, 5))
    return {
        "simulations": simulations,
        "trade_count": n,
        "position_size_pct": round(size * 100, 1),
        "prob_loss_pct": round(float((finals < 1).mean() * 100), 1),
        "median_return_pct": round((float(np.median(finals)) - 1) * 100, 2),
        "mean_return_pct": round((float(np.mean(finals)) - 1) * 100, 2),
        "var95_pct": round((p5 - 1) * 100, 2),
        "cvar95_pct": round((float(finals[finals <= p5].mean()) - 1) * 100, 2),
        "best_pct": round((float(np.max(finals)) - 1) * 100, 2),
        "worst_pct": round((float(np.min(finals)) - 1) * 100, 2),
        "median_max_dd_pct": round(float(np.median(worst_dds)) * 100, 2),
        "worst_max_dd_pct": round(float(np.percentile(worst_dds, 5)) * 100, 2),
        "distribution": finals,
    }


def portfolio_risk(returns: pd.DataFrame) -> dict[str, Any] | None:
    """Getiri matrisinden korelasyon, risk katkısı ve çeşitlendirme skoru üretir."""
    clean = returns.dropna(how="any")
    if clean.shape[1] < 2 or len(clean) < 30:
        return None

    corr = clean.corr()
    cov = clean.cov() * 252
    n = clean.shape[1]
    weights = np.repeat(1.0 / n, n)
    port_var = float(weights @ cov.to_numpy() @ weights)
    port_vol = float(np.sqrt(max(port_var, 0)))
    avg_vol = float(np.mean(np.sqrt(np.diag(cov.to_numpy()))))
    diversification = float(np.clip(1 - port_vol / avg_vol, 0, 1)) if avg_vol > 0 else 0.0

    contributions = weights * (cov.to_numpy() @ weights) / max(port_var, 1e-12)
    hhi = float(np.sum(weights ** 2))
    return {
        "correlation": corr,
        "portfolio_vol_pct": round(port_vol * 100, 2),
        "avg_asset_vol_pct": round(avg_vol * 100, 2),
        "diversification_score": round(diversification * 100, 1),
        "concentration_hhi": round(hhi, 3),
        "risk_contributions": {
            col: round(float(contributions[i] * 100), 1) for i, col in enumerate(clean.columns)
        },
        "avg_correlation": round(float(corr.to_numpy()[np.triu_indices(n, 1)].mean()), 2) if n > 1 else 0.0,
    }
