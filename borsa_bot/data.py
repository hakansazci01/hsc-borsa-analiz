"""
Veri katmanı: Yahoo Finance'tan OHLCV indirme, temizleme ve önbellekleme.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

from borsa_bot.config import Config


CACHE_DIR = Path(".cache")
NEEDED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _cache_path(symbol: str, period: str, interval: str, auto_adjust: bool) -> Path:
    safe = symbol.replace(".", "_").replace("/", "_")
    name = f"{safe}_{period}_{interval}"
    if not auto_adjust:
        name += "_raw"  # varsayılan (adjust=True) eski dosya adını korur
    return CACHE_DIR / f"{name}.csv"


def _clean(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Hem indirilen hem önbellekten okunan veri için ortak doğrulama."""
    df = df.dropna(subset=["Close"])
    missing = [column for column in NEEDED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"{symbol}: eksik sutunlar: {missing}")
    return df[NEEDED_COLUMNS].sort_index()


def fetch(
    symbol: str,
    cfg: Config,
    period: Optional[str] = None,
    interval: Optional[str] = None,
) -> pd.DataFrame:
    """
    Bir sembol için OHLCV verisini döndürür.

    - Önbellek açıksa ve dosya varsa CSV'den okur; aynı temizleme uygulanır.
    - Önbellek anahtarı auto_adjust seçimini de içerir.
    - Geçersiz kapanış satırları atılır, sütunlar standartlaştırılır.
    """
    data_cfg = cfg.data
    period = period or data_cfg.get("period", "2y")
    interval = interval or data_cfg.get("interval", "1d")
    auto_adjust = bool(data_cfg.get("auto_adjust", True))
    use_cache = bool(data_cfg.get("use_cache", True))

    cache_file = _cache_path(symbol, period, interval, auto_adjust)

    if use_cache and cache_file.exists():
        # Disk önbelleği bayatsa yok say: "anlık yenile" gerçekten yeni veri çeksin.
        import time

        age_minutes = (time.time() - cache_file.stat().st_mtime) / 60
        if age_minutes <= 15:
            cached = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            if not cached.empty:
                return _clean(cached, symbol)

    df = yf.Ticker(symbol).history(
        period=period, interval=interval, auto_adjust=auto_adjust
    )
    if df.empty:
        raise ValueError(f"{symbol}: veri indirilemedi (bos dondu).")

    df = _clean(df, symbol)
    if df.empty:
        raise ValueError(f"{symbol}: gecerli kapanis verisi bulunamadi.")

    if use_cache:
        CACHE_DIR.mkdir(exist_ok=True)
        df.to_csv(cache_file)

    return df
