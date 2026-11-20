"""
Arayüz ile mevcut analiz motoru (borsa_bot) arasındaki köprü.

- Kullanıcı ayarları config.yaml üzerine biner; user_settings.json ile kalıcı olur.
- Pahalı veri indirme / gösterge / backtest işlemleri önbelleğe alınır.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from borsa_bot.backtest import run_backtest
from borsa_bot.config import Config
from borsa_bot.data import fetch
from borsa_bot.indicators import add_cross_flags, compute_indicators
from borsa_bot.signals import generate_signal


ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = ROOT / "user_settings.json"

# Kullanıcıya önerilen hisse havuzu (config dosyasındakiler için '.IS' eki korunur).
SUGGESTED_SYMBOLS = [
    "THYAO.IS", "GARAN.IS", "ISCTR.IS", "SISE.IS", "ASELS.IS", "BIMAS.IS",
    "TUPRS.IS", "EREGL.IS", "KCHOL.IS", "SAHOL.IS", "FROTO.IS", "TOASO.IS",
    "AKBNK.IS", "YKBNK.IS", "PGSUS.IS", "TCELL.IS", "AAPL", "MSFT",
    "TSLA", "NVDA", "GOOGL", "AMZN", "META",
]

PERIOD_OPTIONS = ["3mo", "6mo", "1y", "2y", "5y"]
INTERVAL_OPTIONS = ["1d", "1wk"]


def _freeze(value: Any) -> Any:
    """Önbellek anahtarı için listeleri tuple'a çevirir."""
    if isinstance(value, dict):
        return tuple(sorted((str(k), _freeze(v)) for k, v in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(v) for v in value)
    return value


def default_settings() -> dict[str, Any]:
    """config.yaml değerlerinden başlangıç ayarlarını üretir."""
    cfg = Config()
    return {
        "symbols": cfg.symbols,
        "period": cfg.data.get("period", "2y"),
        "interval": cfg.data.get("interval", "1d"),
        "profile": "Dengeli",
        "indicators": cfg.indicators,
        "signal": cfg.signal_thresholds,
        "signal_weights": cfg.signal_weights,
        "risk": cfg.risk,
        "guards": cfg.get("guards", default={}),
        "alerts": cfg.alerts,
        "live_trading": dict(cfg.get("live_trading", default={})),
        "binance": dict(cfg.get("binance", default={})),
        "binance_tr": dict(cfg.get("binance_tr", default={})),
        "gateio": dict(cfg.get("gateio", default={})),
        "schedule": "Kapalı",
    }


def load_settings(path: str | Path | None = None) -> dict[str, Any]:
    """Kayıtlı ayarları yükler; yoksa config.yaml varsayılanlarını döndürür.

    path verilirse kullanıcıya özel dosya, verilmezse eski genel dosya kullanılır.
    """
    target = Path(path) if path is not None else SETTINGS_PATH
    settings = default_settings()
    if target.exists():
        try:
            saved = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                for key in settings:
                    if key in saved:
                        settings[key] = saved[key]
        except (OSError, ValueError) as exc:
            logging.warning("Kayıtlı ayarlar okunamadı, varsayılanlar kullanılıyor: %s", exc)
    return settings


def save_settings(settings: dict[str, Any], path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else SETTINGS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def reset_settings(path: str | Path | None = None) -> None:
    target = Path(path) if path is not None else SETTINGS_PATH
    if target.exists():
        target.unlink()


def _safe_fetch(symbol: str, cfg: Config, period: str, interval: str):
    """
    Önce istenen aralığı dener; ağ hatası / boş veri durumunda
    önbelleğinde bulunan varsayılan (2y, 1d) kombinasyonuna düşer.
    """
    try:
        return fetch(symbol, cfg, period=period, interval=interval)
    except Exception:
        if (period, interval) == ("2y", "1d"):
            raise
        return fetch(symbol, cfg, period="2y", interval="1d")


def _normalize_index(df: pd.DataFrame) -> pd.DataFrame:
    """Tarih indeksini saat dilimlerinden arındırılmış takvim günlerine çevirir.

    YFinance çıktısı bazı sembollerde farklı UTC ofsetleri içerir; bu da
    pandas'ta 'Mixed timezones' hatasına yol açar. Borsa gününü koruyan
    yerel tarihleri kullanmak her sembol için tutarlı bir indeks sağlar.
    """
    try:
        dates = [pd.Timestamp(str(value)).date() for value in df.index]
        df = df.copy()
        df.index = pd.DatetimeIndex(dates)
    except (TypeError, ValueError):
        pass
    return df


def _restore_backtest_dates(bt: dict[str, Any], df: pd.DataFrame) -> None:
    """
    Motor, backtest sırasında DataFrame'in indeksini sıfırladığı için işlem
    tarihleri sıra numarasına (örn. "58") dönüşüyor. Gerçek takvim tarihleriyle
    değiştirerek grafik ve tabloların doğru çalışmasını sağlar.
    """
    idx = df.index
    if not isinstance(idx, pd.DatetimeIndex):
        try:
            idx = pd.to_datetime(idx, utc=True)
        except (TypeError, ValueError):
            return

    def convert(value: Any) -> Any:
        try:
            position = int(value)
        except (TypeError, ValueError):
            return value
        if 0 <= position < len(idx):
            return str(pd.Timestamp(idx[position]).date())
        return value

    for trade in bt.get("trades", []):
        if "date" in trade:
            trade["date"] = convert(trade["date"])
    if "dates" in bt:
        bt["dates"] = [convert(d) for d in bt["dates"]]


@st.cache_data(ttl="5m", max_entries=300, show_spinner=False)
def analyze_symbol(
    symbol: str,
    period: str,
    interval: str,
    indicators: Any,
    weights: Any,
    thresholds: Any,
    risk: Any,
    backtest_cfg: Any,
    guards: Any = None,
) -> dict[str, Any]:
    """Tek sembol için göstergeleri, sinyali ve backtest sonucunu üretir."""
    cfg = Config()
    cfg._raw.setdefault("data", {})["period"] = period
    cfg._raw["data"]["interval"] = interval

    df = _safe_fetch(symbol, cfg, period, interval)
    df = _normalize_index(df)
    df = compute_indicators(df, dict(indicators))
    df = add_cross_flags(df)

    info = generate_signal(
        df,
        {
            "signal_weights": dict(weights),
            "signal_thresholds": dict(thresholds),
        },
    )
    info["symbol"] = symbol

    bt = run_backtest(
        df,
        {
            "backtest": dict(backtest_cfg),
            "risk": dict(risk),
            "signal_thresholds": dict(thresholds),
            "signal_weights": dict(weights),
            "guards": dict(guards or {}),
        },
    )
    _restore_backtest_dates(bt, df)
    return {"info": info, "backtest": bt, "df": df, "period": period, "interval": interval}


@st.cache_data(ttl="5m", max_entries=50, show_spinner=False)
def scan_market(
    symbols: tuple[str, ...],
    period: str,
    interval: str,
    indicators: Any,
    weights: Any,
    thresholds: Any,
    risk: Any,
    backtest_cfg: Any,
    guards: Any = None,
) -> tuple[dict[str, Any], ...]:
    """Tüm izleme listesini tarar; hatalı sembolleri de hata bilgisiyle döndürür."""
    results: list[dict[str, Any]] = []
    for symbol in symbols:
        try:
            results.append(
                analyze_symbol(
                    symbol, period, interval, indicators, weights,
                    thresholds, risk, backtest_cfg, guards,
                )
            )
        except Exception as exc:  # tek bir sembol tüm taramayı bozmasın
            results.append({"symbol": symbol, "error": str(exc)})
    return tuple(results)


def analysis_args(settings: dict[str, Any]) -> dict[str, Any]:
    """Ayarlardan önbelleğe geçirilebilir (hashable) analiz argümanları üretir."""
    cfg = Config()
    return {
        "period": settings["period"],
        "interval": settings["interval"],
        "indicators": _freeze(settings["indicators"]),
        "weights": _freeze(settings["signal_weights"]),
        "thresholds": _freeze(settings["signal"]),
        "risk": _freeze(settings["risk"]),
        "backtest_cfg": _freeze(cfg.backtest),
        "guards": _freeze(settings.get("guards", cfg.get("guards", default={}))),
    }
