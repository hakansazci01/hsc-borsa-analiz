"""
Teknik analiz gostergeleri modulu.

Tum hesaplamalar pandas/numpy ile yapilir; ta-lib gerekmez.
Girdi DataFrame'in 'Open','High','Low','Close','Volume' sutunlarini icermesi gerekir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_indicators(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    Tum teknik gostergeleri hesaplar ve df'e ekler.

    Dondurur: kopyalanmis, gostergeler eklenmis DataFrame.
    """
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    volume = df["Volume"]

    # ---- SMA ----
    for p in cfg.get("sma_periods", [20, 50, 200]):
        # min_periods=window: erken barlarda 2 veriyle "SMA200" üretmek yanıltıcı sinyal yaratır
        df[f"SMA_{p}"] = close.rolling(window=p, min_periods=p).mean()

    # ---- EMA ----
    df["EMA_12"] = close.ewm(span=cfg.get("ema_fast", 12), adjust=False).mean()
    df["EMA_26"] = close.ewm(span=cfg.get("ema_slow", 26), adjust=False).mean()

    # ---- RSI ----
    df["RSI"] = _wilder_rsi(close, cfg.get("rsi_period", 14))

    # ---- MACD ----
    ema_fast = close.ewm(span=cfg.get("macd_fast", 12), adjust=False).mean()
    ema_slow = close.ewm(span=cfg.get("macd_slow", 26), adjust=False).mean()
    df["MACD"] = ema_fast - ema_slow
    df["MACD_Signal"] = df["MACD"].ewm(
        span=cfg.get("macd_signal", 9), adjust=False
    ).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    # ---- Bollinger Bantlari ----
    bb_p = cfg.get("bb_period", 20)
    bb_std = cfg.get("bb_std", 2.0)
    df["BB_Middle"] = close.rolling(window=bb_p, min_periods=bb_p).mean()
    bb_roll_std = close.rolling(window=bb_p, min_periods=bb_p).std()
    df["BB_Upper"] = df["BB_Middle"] + bb_roll_std * bb_std
    df["BB_Lower"] = df["BB_Middle"] - bb_roll_std * bb_std
    rng = df["BB_Upper"] - df["BB_Lower"]
    df["BB_Width"] = rng / df["BB_Middle"].replace(0, np.nan)
    df["BB_PercentB"] = (close - df["BB_Lower"]) / rng.replace(0, np.nan)

    # ---- Stokastik Oscillator ----
    k_p = cfg.get("stoch_k", 14)
    d_p = cfg.get("stoch_d", 3)
    lowest_low = low.rolling(window=k_p, min_periods=k_p).min()
    highest_high = high.rolling(window=k_p, min_periods=k_p).max()
    df["Stoch_K"] = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    df["Stoch_D"] = df["Stoch_K"].rolling(window=d_p, min_periods=d_p).mean()

    # ---- OBV ----
    df["OBV"] = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    df["OBV_EMA"] = df["OBV"].ewm(span=20, adjust=False).mean()

    # ---- ATR (Wilder) ----
    atr_p = cfg.get("atr_period", 14)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["ATR"] = tr.ewm(alpha=1 / atr_p, adjust=False, min_periods=1).mean()

    # ---- VWAP ----
    if cfg.get("vwap_enabled", True):
        typical = (high + low + close) / 3.0
        # Kumulatif VWAP tüm geçmişi kapsar ve sinyal için fazla yavaştır;
        # koruyoruz ama karar için kaydirilmali (20 gun) VWAP kullanilacak.
        df["VWAP"] = (typical * volume).cumsum() / volume.cumsum().replace(0, np.nan)
        vwap_window = 20
        num = (typical * volume).rolling(window=vwap_window, min_periods=1).sum()
        den = volume.rolling(window=vwap_window, min_periods=1).sum().replace(0, np.nan)
        df["VWAP_Rolling"] = num / den

    return df


def add_cross_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cepre gunde crossover / undercross bayraklarini ekler.
    """
    df = df.copy()

    # MACD kesisimleri
    df["MACD_Cross_Up"] = (df["MACD"] > df["MACD_Signal"]) & (
        df["MACD"].shift(1) <= df["MACD_Signal"].shift(1)
    )
    df["MACD_Cross_Down"] = (df["MACD"] < df["MACD_Signal"]) & (
        df["MACD"].shift(1) >= df["MACD_Signal"].shift(1)
    )

    # Stokastik kesisimleri
    df["Stoch_Cross_Up"] = (df["Stoch_K"] > df["Stoch_D"]) & (
        df["Stoch_K"].shift(1) <= df["Stoch_D"].shift(1)
    )
    df["Stoch_Cross_Down"] = (df["Stoch_K"] < df["Stoch_D"]) & (
        df["Stoch_K"].shift(1) >= df["Stoch_D"].shift(1)
    )

    # Trend duzeni — SMA50/SMA200 yoksa (config değişmiş olabilir) nötr bayrak
    if {"SMA_50", "SMA_200"}.issubset(df.columns):
        bullish = (df["Close"] > df["SMA_50"]) & (df["SMA_50"] > df["SMA_200"])
        bearish = (df["Close"] < df["SMA_50"]) & (df["SMA_50"] < df["SMA_200"])
    else:
        bullish = pd.Series(False, index=df.index)
        bearish = pd.Series(False, index=df.index)
    df["Trend_Bullish"] = bullish.fillna(False)
    df["Trend_Bearish"] = bearish.fillna(False)

    # OBV yonu
    df["OBV_Rising"] = df["OBV"] > df["OBV"].shift(1)
    df["OBV_Falling"] = df["OBV"] < df["OBV"].shift(1)

    # Fiyat vs VWAP — karar icin kaydirilmali VWAP daha anlamlidir
    vwap_col = "VWAP_Rolling" if "VWAP_Rolling" in df.columns else "VWAP"
    if vwap_col in df.columns:
        df["Price_Above_VWAP"] = df["Close"] > df[vwap_col]
        df["Price_Below_VWAP"] = df["Close"] < df[vwap_col]

    return df