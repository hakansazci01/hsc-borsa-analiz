"""
Anlık (Intraday) işlem sinyali motoru.

Günlük sinyallerin yerine geçmez; seans içinde 1 dakikalık canlı mumlarla
"şu an giriş var mı?" sorusunu yanıtlar.

Kurallar (profesyonel intraday yaklaşım):
- 5m EMA9/20 kesişimi tetikleyici,
- fiyat VWAP üstünde/altında (kurumsal adil fiyat),
- RSI7 momentum onayı,
- hacim patlaması (son bar / son 20 bar ortalaması),
- üst zaman dilimi (15m + günlük) yön onayı,
- seans filtresi (ilk 5 / son 10 dakika yok),
- KAP acil duyuru durdurma (halt) kontrolü.

Tüm koşullar tek tek gösterilir; karar "şeffaf tetikleyici"dir.
"""

from __future__ import annotations

import threading
import warnings
from typing import Any

import pandas as pd
import streamlit as st

from ui.market_session import now, status as session_status


_CANDLE_LOCK = threading.Lock()


@st.cache_resource(show_spinner=False)
def get_candle_stream():
    import borsapy as bp

    stream = bp.TradingViewStream()
    try:
        stream.connect(timeout=10)
    except Exception:
        pass
    return stream


def _with_candle_stream(symbol: str, count: int) -> list[dict[str, Any]]:
    stream = get_candle_stream()
    with _CANDLE_LOCK:
        if not stream.is_connected:
            try:
                stream.disconnect()
            except Exception:
                pass
            try:
                stream.connect(timeout=10)
            except Exception:
                return []
        try:
            stream.subscribe_chart(symbol, interval="1m")
        except Exception:
            pass
        try:
            candles = stream.get_candles(symbol, "1m", count=count) or []
            if not candles:
                try:
                    stream.wait_for_candle(symbol, "1m", timeout=4)
                except Exception:
                    pass
                candles = stream.get_candles(symbol, "1m", count=count) or []
            return candles
        except Exception:
            return []


@st.cache_data(ttl="20s", max_entries=100, show_spinner=False)
def fetch_candles(symbol: str, count: int = 220) -> pd.DataFrame | None:
    raw = _with_candle_stream(symbol, count)
    if not raw or len(raw) < 30:
        return None
    df = pd.DataFrame(raw)
    rename = {"time": "Tarih", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}
    df = df.rename(columns=rename)
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Tarih"] = pd.to_datetime(df["Tarih"], unit="s")
    return df.dropna(subset=["Close"]).set_index("Tarih").sort_index()


def resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    rule = f"{minutes}min"
    return df.resample(rule).agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna(subset=["Close"])


def fast_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    for span in (9, 20):
        d[f"EMA{span}"] = d["Close"].ewm(span=span, adjust=False).mean()
    delta = d["Close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 7, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 7, adjust=False).mean()
    d["RSI7"] = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    typical = (d["High"] + d["Low"] + d["Close"]) / 3
    d["VWAP"] = (typical * d["Volume"]).cumsum() / d["Volume"].cumsum().replace(0, float("nan"))
    d["VolAvg20"] = d["Volume"].rolling(20, min_periods=5).mean()
    d["VolRatio"] = d["Volume"] / d["VolAvg20"].replace(0, float("nan"))
    d["ATR14"] = (d["High"] - d["Low"]).ewm(alpha=1 / 14, adjust=False).mean()
    d["CrossUp"] = (d["EMA9"] > d["EMA20"]) & (d["EMA9"].shift(1) <= d["EMA20"].shift(1))
    d["CrossDown"] = (d["EMA9"] < d["EMA20"]) & (d["EMA9"].shift(1) >= d["EMA20"].shift(1))
    return d


def news_halt(symbol: str) -> tuple[bool, str]:
    try:
        import borsapy as bp

        from ui.market_session import now

        news = bp.Ticker(symbol).news or []
        for item in news[:10]:
            content = item.get("content") or {}
            title = str(content.get("title") or "")
            pub = str(content.get("pubDate") or "")
            if not pub:
                continue
            from datetime import datetime, timedelta

            try:
                moment = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                age = (now() - moment.astimezone(now().tzinfo)).total_seconds() / 60
            except (ValueError, TypeError):
                continue
            if 0 <= age <= 60 and any(w in title.lower() for w in ("spk", "inceleme", "yasağı", "dava", "ceza", "soruşturma")):
                return True, f"Son 60 dk: {title[:80]}"
    except Exception:
        pass
    return False, "Acil duyuru yok"


@st.cache_data(ttl="60s", max_entries=100, show_spinner=False)
def daily_bias(symbol: str) -> str:
    try:
        import borsapy as bp

        rec = bp.Ticker(symbol).ta_signals(interval="1d").get("summary", {}).get("recommendation", "NEUTRAL")
        return str(rec)
    except Exception:
        return "NEUTRAL"


def intraday_signal(symbol: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    candles = fetch_candles(symbol.upper())
    if candles is None:
        return None
    m5 = fast_indicators(resample(candles, 5))
    m15 = fast_indicators(resample(candles, 15))
    if len(m5) < 25:
        return None

    last = m5.iloc[-1]
    last15 = m15.iloc[-1]
    price = float(last["Close"])
    session = session_status()
    moment = now()
    minute_of_day = moment.hour * 60 + moment.minute
    open_min, close_min = 10 * 60, 18 * 60
    in_window = open_min + 5 <= minute_of_day <= close_min - 10

    halted, halt_note = news_halt(symbol.upper())
    bias = daily_bias(symbol.upper())
    bias_bull = bias in ("BUY", "STRONG_BUY")
    bias_bear = bias in ("SELL", "STRONG_SELL")

    checks: list[dict[str, Any]] = [
        {"Kontrol": "Seans açık", "Geçti": session["in_session"], "Detay": session["label"]},
        {"Kontrol": "Zaman penceresi (10:05–17:50)", "Geçti": in_window, "Detay": moment.strftime("%H:%M")},
        {"Kontrol": "KAP acil duyuru yok", "Geçti": not halted, "Detay": halt_note},
        {"Kontrol": "EMA9 > EMA20 (5m)", "Geçti": bool(last["EMA9"] > last["EMA20"]), "Detay": f"EMA9 {last['EMA9']:.2f} / EMA20 {last['EMA20']:.2f}"},
        {"Kontrol": "Fiyat > VWAP", "Geçti": bool(price > last["VWAP"]), "Detay": f"Fiyat {price:.2f} / VWAP {last['VWAP']:.2f}"},
        {"Kontrol": "RSI7 > 50", "Geçti": bool(last["RSI7"] > 50), "Detay": f"RSI7 {last['RSI7']:.1f}"},
        {"Kontrol": "Hacim patlaması (>1.3x)", "Geçti": bool(last["VolRatio"] > 1.3), "Detay": f"{last['VolRatio']:.2f}x"},
        {"Kontrol": "15m EMA9 > EMA20", "Geçti": bool(last15["EMA9"] > last15["EMA20"]), "Detay": f"EMA9 {last15['EMA9']:.2f} / EMA20 {last15['EMA20']:.2f}"},
        {"Kontrol": "Günlük yön onayı", "Geçti": bias_bull, "Detay": f"Günlük teknik öneri: {bias}"},
    ]

    bull_score = sum(1 for c in checks[3:] if c["Geçti"])
    bear_ok = (
        not bool(last["EMA9"] > last["EMA20"]) and price < float(last["VWAP"])
        and last["RSI7"] < 50 and (last["VolRatio"] > 1.3)
        and not bool(last15["EMA9"] > last15["EMA20"]) and bias_bear
    )
    gates_ok = checks[0]["Geçti"] and checks[1]["Geçti"] and checks[2]["Geçti"]

    if gates_ok and bull_score >= 6:
        decision = "AL"
    elif gates_ok and bear_ok:
        decision = "SAT"
    else:
        decision = "BEKLE"

    risk = settings["risk"]
    stop_pct = float(risk.get("stop_loss_pct", 0.05))
    target_pct = float(risk.get("take_profit_pct", 0.10))
    sign = 1 if decision == "AL" else -1 if decision == "SAT" else 0
    atr_value = float(last["ATR14"]) if pd.notna(last["ATR14"]) else price * 0.01
    stop = round(price - sign * max(atr_value, price * stop_pct), 2) if sign else None
    target = round(price + sign * max(atr_value, price * stop_pct) * 2, 2) if sign else None

    # --- Zaman tahmini: mesafe / dakikalık oynaklık ---
    # Bu bir garanti değil; yalnızca "koşulların yaklaşık ne kadar sürede
    # oluşabileceği"ni gösteren oynaklık tabanlı bir tahmindir.
    per_minute = max(atr_value / 5.0, price * 0.0002)
    gaps: list[tuple[float, str]] = []

    def _gap(distance: float, label: str) -> None:
        if distance > 0 and pd.notna(distance):
            gaps.append((float(distance), label))

    ema9, ema20 = float(last["EMA9"]), float(last["EMA20"])
    vwap = float(last["VWAP"]) if pd.notna(last["VWAP"]) else price
    rsi = float(last["RSI7"]) if pd.notna(last["RSI7"]) else 50.0

    if decision == "BEKLE":
        if ema9 <= ema20:
            _gap(ema20 - ema9, "5m EMA9/20 yukarı kesişimi")
        if price <= vwap:
            _gap(vwap - price, "fiyatın VWAP üzerine geçmesi")
        if rsi <= 50:
            _gap((50 - rsi) / 8.0 * atr_value, "RSI7'nin 50 üzerine çıkması")
        ema9_15, ema20_15 = float(last15["EMA9"]), float(last15["EMA20"])
        if ema9_15 <= ema20_15:
            _gap(ema20_15 - ema9_15, "15m EMA9/20 onayı")
    else:
        if target:
            _gap(abs(float(target) - price), "hedef fiyat")

    wait_minutes: int | None = None
    wait_low: int | None = None
    wait_high: int | None = None
    hold_minutes: int | None = None
    closest_trigger = ""
    # Seans dışında, pencere dışında veya KAP durdurması varsa süre tahmini üretme.
    if not session["in_session"] or not in_window or halted:
        gaps = []
    if gaps:
        nearest = min(gaps, key=lambda g: g[0])
        closest_trigger = nearest[1]
        estimated = nearest[0] / per_minute
        if decision == "BEKLE":
            wait_minutes = int(min(240, max(1, round(estimated))))
            # Kesin süre iddia etme yerine oynaklık temelli bir aralık ver.
            wait_low = max(1, int(wait_minutes * 0.6))
            wait_high = min(240, int(wait_minutes * 1.6))
        else:
            hold_minutes = int(min(240, max(1, round(estimated))))

    remaining_minutes = max(0, close_min - minute_of_day)

    return {
        "symbol": symbol.upper(),
        "decision": decision,
        "price": price,
        "confidence": int(min(95, 30 + bull_score * 10)) if decision == "AL" else (70 if decision == "SAT" else 20),
        "checks": checks,
        "m5": m5,
        "m15": m15,
        "candles": candles,
        "stop": stop,
        "target": target,
        "atr": atr_value,
        "wait_minutes": wait_minutes,
        "wait_low": wait_low,
        "wait_high": wait_high,
        "remaining_minutes": remaining_minutes,
        "hold_minutes": hold_minutes,
        "closest_trigger": closest_trigger,
        "per_minute_move": round(per_minute, 4),
        "bias": bias,
        "session": session["label"],
        "time": moment.strftime("%H:%M:%S"),
        "reason": (
            "Tetikleyici koşulların çoğu birleşti." if decision == "AL"
            else "Satış yönlü koşullar birleşti." if decision == "SAT"
            else "Koşullar tam uymuyor; işlem yok."
        ),
    }
