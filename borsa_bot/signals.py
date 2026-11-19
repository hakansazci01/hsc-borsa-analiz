"""
Sinyal uretilme katmani.

Gostergelerden agirlikli puanlama yapar ve AL/SAT/NÜTRAL sinyali uretir.
Puan araligi: -5 (guclu sat) ile +5 (guclu al).
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _score(
    last: pd.Series,
    prev: pd.Series,
    weights: dict[str, float],
    thresholds: dict[str, float],
    has_prev: bool = True,
) -> tuple[float, dict[str, str]]:
    score = 0.0
    details: dict[str, str] = {}

    rsi_os = float(thresholds.get("rsi_oversold", 30))
    rsi_ob = float(thresholds.get("rsi_overbought", 70))

    # ---- RSI ----
    rsi = float(last["RSI"]) if pd.notna(last.get("RSI")) else 50.0
    w = float(weights.get("rsi", 1.5))
    if rsi < rsi_os:
        score += w
        details["RSI"] = f"AŞIRI DÜŞÜK ({rsi:.1f}) → AL"
    elif rsi > rsi_ob:
        score -= w
        details["RSI"] = f"AŞIRI YÜKSEK ({rsi:.1f}) → SAT"
    else:
        details["RSI"] = f"Nötr ({rsi:.1f})"

    # ---- MACD ----
    macd = float(last.get("MACD", 0)) if pd.notna(last.get("MACD")) else 0.0
    macd_sig = float(last.get("MACD_Signal", 0)) if pd.notna(last.get("MACD_Signal")) else 0.0
    macd_hist = float(last.get("MACD_Hist", 0)) if pd.notna(last.get("MACD_Hist")) else 0.0
    w = float(weights.get("macd", 1.5))
    if bool(last.get("MACD_Cross_Up", False)):
        score += w
        details["MACD"] = "MACD çizgisi yukarı kesti → AL"
    elif bool(last.get("MACD_Cross_Down", False)):
        score -= w
        details["MACD"] = "MACD çizgisi aşağı kesti → SAT"
    elif macd_hist > 0:
        score += w * 0.33
        details["MACD"] = f"Histogram pozitif ({macd_hist:.4f}) → AL yönü"
    elif macd_hist < 0:
        score -= w * 0.33
        details["MACD"] = f"Histogram negatif ({macd_hist:.4f}) → SAT yönü"
    else:
        details["MACD"] = "Nötr"

    # ---- Trend (SMA duzeni) ----
    close = float(last["Close"])
    sma50 = float(last.get("SMA_50", close)) if pd.notna(last.get("SMA_50")) else close
    sma200 = float(last.get("SMA_200", close)) if pd.notna(last.get("SMA_200")) else close
    w = float(weights.get("trend", 1.0))
    if bool(last.get("Trend_Bullish", False)):
        score += w
        details["Trend"] = "Fiyat > SMA50 > SMA200 -> Yükseliş"
    elif bool(last.get("Trend_Bearish", False)):
        score -= w
        details["Trend"] = "Fiyat < SMA50 < SMA200 -> Düşüş"
    else:
        details["Trend"] = "Karışık / Nötr"

    # ---- Bollinger (ortalama donus) ----
    bb_pctb = float(last.get("BB_PercentB", 0.5)) if pd.notna(last.get("BB_PercentB")) else 0.5
    w = float(weights.get("bollinger", 1.0))
    if bb_pctb < 0:
        score += w
        details["Bollinger"] = f"Alt banda (%B={bb_pctb:.2f}) → AL (donus)"
    elif bb_pctb > 1:
        score -= w
        details["Bollinger"] = f"Üst banda (%B={bb_pctb:.2f}) → SAT (donus)"
    else:
        details["Bollinger"] = f"Bantlar içinde (%B={bb_pctb:.2f})"
    # ---- Stokastik ----
    stoch_k = float(last.get("Stoch_K", 50)) if pd.notna(last.get("Stoch_K")) else 50.0
    w = float(weights.get("stochastic", 1.0))
    if bool(last.get("Stoch_Cross_Up", False)) and stoch_k < 20:
        score += w
        details["Stochastic"] = f"AŞIRI DÜŞÜK & yukarı kesiş ({stoch_k:.1f}) → AL"
    elif bool(last.get("Stoch_Cross_Down", False)) and stoch_k > 80:
        score -= w
        details["Stochastic"] = f"AŞIRI YÜKSEK & aşağı kesiş ({stoch_k:.1f}) → SAT"
    elif stoch_k < 20:
        score += w * 0.5
        details["Stochastic"] = f"Aşırı düşük ({stoch_k:.1f}) → AL yönü"
    elif stoch_k > 80:
        score -= w * 0.5
        details["Stochastic"] = f"Aşırı yüksek ({stoch_k:.1f}) → SAT yönü"
    else:
        details["Stochastic"] = f"Nötr ({stoch_k:.1f})"

    # ---- OBV (hacim onay) ----
    obv_rising = bool(last.get("OBV_Rising", False))
    price_up = (
        close > float(prev["Close"])
        if has_prev and prev is not None and pd.notna(prev.get("Close"))
        else False
    )
    w = float(weights.get("obv", 0.5))
    if obv_rising and price_up:
        score += w
        details["OBV"] = "Hacim artisli yelis -> Onay"
    elif (not obv_rising) and (not price_up):
        score -= w
        details["OBV"] = "Hacim azalisli dusus -> Onay"
    else:
        details["OBV"] = "Hacim onayi yetersiz"

    # ---- VWAP (kaydirilmali 20 gun; kumulatif VWAP cok yavas oldugu icin) ----
    vwap_key = "VWAP_Rolling" if "VWAP_Rolling" in last.index else "VWAP"
    if vwap_key in last.index and pd.notna(last.get(vwap_key)):
        vwap = float(last[vwap_key])
        w = float(weights.get("vwap", 0.5))
        if close > vwap:
            score += w * 0.5
            details["VWAP"] = f"Fiyat > VWAP ({vwap:.2f}) → AL yönü"
        elif close < vwap:
            score -= w * 0.5
            details["VWAP"] = f"Fiyat < VWAP ({vwap:.2f}) → SAT yönü"
        else:
            details["VWAP"] = "VWAP üzerinde / altında nötr"
    else:
        details["VWAP"] = "Veri yok"

    return score, details


def score_to_signal(
    raw_score: float,
    weights: dict[str, float],
    thresholds: dict[str, float],
) -> tuple[str, float]:
    """Ham puanı canlı motorla aynı şekilde normalize edip sınıflandırır.

    Backtest ve canlı sinyal üretimi bu tek fonksiyonu kullanır; böylece
    iki katman arasında eşik farkı oluşmaz.
    """
    max_possible = sum(float(v) for v in weights.values())
    score = raw_score
    if max_possible > 0:
        score = max(-5.0, min(5.0, (raw_score / max_possible) * 5.0))
    return classify(score, thresholds), score


def classify(score: float, thresholds: dict[str, float]) -> str:
    if score >= float(thresholds.get("strong_buy", 4.0)):
        return "STRONG_BUY"
    if score >= float(thresholds.get("buy", 2.0)):
        return "BUY"
    if score <= float(thresholds.get("strong_sell", -4.0)):
        return "STRONG_SELL"
    if score <= float(thresholds.get("sell", -2.0)):
        return "SELL"
    return "NEUTRAL"


def generate_signal(df: pd.DataFrame, cfg: dict) -> dict[str, Any]:
    """
    En son gün için sinyal üretir.

    Dondurur: dict (symbol, score, signal, details, last_close, rsi, macd, ...)
    """
    if df is None or df.empty:
        raise ValueError("generate_signal için boş veri çerçevesi.")

    weights = cfg.get("signal_weights", {})
    thresholds = cfg.get("signal_thresholds", {})

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last

    raw, details = _score(last, prev, weights, thresholds, has_prev=len(df) > 1)
    signal, score = score_to_signal(raw, weights, thresholds)

    def num(key: str, digits: int, default: float = 0.0) -> float:
        value = last.get(key, default)
        if value is None or not pd.notna(value):
            return default
        return round(float(value), digits)

    vwap_key = "VWAP_Rolling" if "VWAP_Rolling" in last.index else "VWAP"

    return {
        "score": round(score, 2),
        "signal": signal,
        "details": details,
        "last_close": num("Close", 4),
        "rsi": num("RSI", 2, 50.0),
        "macd": num("MACD", 4),
        "macd_signal": num("MACD_Signal", 4),
        "macd_hist": num("MACD_Hist", 4),
        "bb_pctb": num("BB_PercentB", 3, 0.5),
        "stoch_k": num("Stoch_K", 2, 50.0),
        "atr": num("ATR", 4),
        "vwap": num(vwap_key, 4),
    }
