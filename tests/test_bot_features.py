"""Fiyat alarmı ve takip stop (paper) testleri."""

from __future__ import annotations

from unittest.mock import patch

from ui import auth, paper, price_alerts
from ui.core import default_settings


USER = "bot_feature_test"


def _clean() -> None:
    try:
        auth.delete_account(USER)
    except Exception:
        pass


def test_price_alert_lifecycle() -> None:
    _clean()
    try:
        price_alerts.add(USER, "THYAO", "above", 100.0, "test")
        rules = price_alerts.load(USER)
        assert len(rules) == 1 and not rules[0]["triggered"]
        fired = price_alerts.check(USER, {"THYAO": 101.0})
        assert len(fired) == 1 and fired[0]["symbol"] == "THYAO"
        assert price_alerts.load(USER)[0]["triggered"] is True
        assert price_alerts.check(USER, {"THYAO": 105.0}) == [], "Tek seferlik alarm tekrar tetiklendi"
        price_alerts.remove(USER, rules[0]["id"])
        assert price_alerts.load(USER) == []
    finally:
        _clean()


def test_trailing_stop_simulation() -> None:
    _clean()
    settings = default_settings()
    settings["risk"]["trailing_stop_pct"] = 0.03
    try:
        position = paper.open_position(
            USER, "THYAO", 10, 100.0, 95.0, 150.0, 70, "test", allow_closed=True
        )
        assert position["peak_price"] == 100.0

        with patch("ui.paper.live_quote", return_value={"price": 120.0, "source": "test"}):
            rows = paper.evaluate(USER, settings)
        assert rows[0]["peak_price"] == 120.0
        assert rows[0]["trailing_stop"] == 116.4
        assert rows[0]["action"] == "TUT"

        with patch("ui.paper.live_quote", return_value={"price": 110.0, "source": "test"}):
            rows = paper.evaluate(USER, settings)
        assert rows[0]["action"] == "SAT"
        assert any("Takip stop" in r for r in rows[0]["reasons"])
    finally:
        _clean()
