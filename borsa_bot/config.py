"""
Yapilandirma yukleme ve erisim modulu.

config.yaml + .env dosyasini okur, tum ayarlari tek bir nesne olarak sunar.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
ENV_PATH = BASE_DIR / ".env"


class Config:
    def __init__(self, config_path: str | Path = CONFIG_PATH) -> None:
        load_dotenv(ENV_PATH)
        with open(config_path, "r", encoding="utf-8") as f:
            self._raw: dict[str, Any] = yaml.safe_load(f)

    def get(self, *keys: str, default: Any = None) -> Any:
        cur: Any = self._raw
        for key in keys:
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur

    @property
    def symbols(self) -> list[str]:
        return list(self.get("symbols", default=[]))

    @property
    def data(self) -> dict[str, Any]:
        return dict(self.get("data", default={}))

    @property
    def indicators(self) -> dict[str, Any]:
        return dict(self.get("indicators", default={}))

    @property
    def signal_weights(self) -> dict[str, float]:
        return dict(self.get("signal_weights", default={}))

    @property
    def signal_thresholds(self) -> dict[str, float]:
        # RSI eşikleri config'de 'indicators' altında tutulur; sinyal motoru
        # ise bunları thresholds sözlüğünden okur. Tek noktada birleştiriyoruz.
        thresholds = dict(self.get("signal", default={}))
        indicators = self.get("indicators", default={}) or {}
        thresholds.setdefault("rsi_oversold", indicators.get("rsi_oversold", 30))
        thresholds.setdefault("rsi_overbought", indicators.get("rsi_overbought", 70))
        return thresholds

    @property
    def risk(self) -> dict[str, Any]:
        return dict(self.get("risk", default={}))

    @property
    def backtest(self) -> dict[str, Any]:
        return dict(self.get("backtest", default={}))

    @property
    def alerts(self) -> dict[str, Any]:
        return dict(self.get("alerts", default={}))

    @property
    def visualize(self) -> dict[str, Any]:
        return dict(self.get("visualize", default={}))

    @property
    def telegram_token(self) -> str:
        token = self.alerts.get("telegram_bot_token", "")
        return os.getenv("TELEGRAM_BOT_TOKEN", token)

    @property
    def telegram_chat_id(self) -> str:
        chat_id = self.alerts.get("telegram_chat_id", "")
        return os.getenv("TELEGRAM_CHAT_ID", chat_id)