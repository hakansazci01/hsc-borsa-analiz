"""Gerçek para kilitleri: varsayılan olarak hiçbir emir gönderilmemeli."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from ui import auth, live_bot, live_guard
from ui.core import default_settings


USER = "live_guard_test"


def _clean() -> None:
    try:
        auth.delete_account(USER)
    except Exception:
        pass


def test_default_locked_no_order() -> None:
    _clean()
    try:
        settings = default_settings()
        ok, reasons, cfg = live_guard.check(
            USER, "THYAO", 1, 100, phrase="", session_armed=False, settings=settings
        )
        assert not ok, "Varsayılan olarak gerçek emir açık olmamalı"
        assert any("enabled" in r for r in reasons)
        assert cfg.get("enabled") is False

        with patch("ui.broker.place_live_order") as send:
            result = live_bot.execute(
                USER, "THYAO", "AL", 1, 100, settings=settings
            )
        assert not result.get("ok")
        send.assert_not_called()
        assert live_bot.recent_orders(USER) == []
    finally:
        _clean()


def test_keys_and_phrase_required() -> None:
    _clean()
    try:
        settings = default_settings()
        settings["live_trading"]["enabled"] = True
        with patch.dict("os.environ", {"HSC_LIVE_ARMED": "YES"}):
            ok, reasons, _ = live_guard.check(
                USER, "THYAO", 1, 100, phrase="YANLIS", session_armed=False,
                settings=settings,
            )
        assert not ok
        assert any("Onay ifadesi" in r for r in reasons)
        assert any("anahtar" in r for r in reasons)
    finally:
        _clean()


def test_binance_default_locked() -> None:
    from ui import binance_bot
    from ui.core import default_settings

    _clean()
    binance_bot.set_local_armed(False)
    try:
        settings = default_settings()
        ok, reasons, config = binance_bot.guard(
            "BTCUSDT", 0.001, 50000, "", False, settings
        )
        assert not ok and config.get("testnet") is True
        assert any("Ortam kilidi" in r for r in reasons)
        assert any("Onay ifadesi" in r for r in reasons)
        assert any("Oturum onayı" in r for r in reasons)
        with patch("ui.binance_bot._request") as send:
            result = binance_bot.execute(
                USER, "BTCUSDT", "buy", 0.001, 50000, settings=settings
            )
        assert not result.get("ok")
        send.assert_not_called()
    finally:
        _clean()


def test_gateio_adapter() -> None:
    from ui import gateio_bot
    from ui.core import default_settings

    _clean()
    gateio_bot.set_local_armed(False)
    try:
        settings = default_settings()
        config = gateio_bot.cfg(settings)
        assert config.get("testnet") is True
        ok, reasons, _ = gateio_bot.guard(
            "BTC_USDT", 0.001, 50000, "", False, settings
        )
        assert not ok and reasons
        with patch("ui.gateio_bot._request") as send:
            result = gateio_bot.execute(
                USER, "BTC_USDT", "buy", 0.001, 50000, settings=settings
            )
        assert not result.get("ok")
        send.assert_not_called()
        signal = gateio_bot.quick_signal("BTC_USDT")
        assert signal.get("decision") in ("AL", "SAT", "BEKLE")
    finally:
        _clean()


def test_binance_tr_adapter_locked() -> None:
    from ui import binance_tr_bot

    _clean()
    binance_tr_bot.set_local_armed(False)
    try:
        settings = default_settings()
        config = binance_tr_bot.cfg(settings)
        assert "binance_tr" in settings
        assert config.get("enabled") is False
        ok, reasons, _ = binance_tr_bot.guard(
            "BTC_USDT", 0.001, 50000, "", False, settings
        )
        assert not ok and reasons
        assert any("Ortam kilidi" in r for r in reasons)
        assert any("Onay ifadesi" in r for r in reasons)
        assert any("HSC_BINANCE_TR_LIVE" in r for r in reasons)
        with patch("ui.binance_tr_bot._request") as send:
            result = binance_tr_bot.execute(
                USER, "BTC_USDT", "buy", 0.001, 50000, settings=settings
            )
        assert not result.get("ok")
        send.assert_not_called()
        assert binance_tr_bot._symbol("BTCUSDT") == "BTC_USDT"
        assert binance_tr_bot._symbol("btc-usdt") == "BTC_USDT"
    finally:
        _clean()


def test_tr_scalper_bounds() -> None:
    """Mikro alsat motorunun saf fonksiyonlari ve risk sinirlari."""
    from ui import tr_scalper as t

    assert t.MAX_ORDER_TRY == 50.0
    assert t.MAX_ORDER_GROW == 100.0
    assert t.MAX_LOSS_TRY == 15.0
    assert t.MAX_TRADES >= 50
    assert t.MAX_HOLD_SEC == 900
    assert t.TAKE_PROFIT > t.STOP_LOSS > 0
    assert t._round_qty(0.2063, 0.1, 0.1) == 0.2
    assert t._round_qty(0.05, 0.1, 0.1) == 0.1
    assert t._round_qty(1.234, 0.0, 0.0) == 1.234
    assert set(t.PAIRS).issubset({"XRP_TRY", "DOGE_TRY", "ADA_TRY",
                                  "TRX_TRY", "LTC_TRY", "LINK_TRY", "FORM_TRY"})


def test_quant_lab_verdict_logic() -> None:
    """Arastirma karari: dogrulanmis strateji yoksa ISLEM YOK demeli."""
    from ui import quant_lab

    assert quant_lab.FEE == 0.001
    assert len(quant_lab.SYMBOLS) >= 5
    assert len(quant_lab.TIMEFRAMES) >= 3
    frame = pd.DataFrame({
        "Open": [1.0] * 120, "High": [1.1] * 120,
        "Low": [0.9] * 120, "Close": [1.0] * 120, "Volume": [1.0] * 120,
    })
    r = quant_lab.regime(frame)
    assert r["name"] in ("YUKARI (bull)", "ASAGI (bear)")
    assert quant_lab.backtest(frame, "ema_cross", (9, 50)) == []


def test_autonomous_selftest_logic() -> None:
    """Öngörü self-test'i gerçek fiyat yönüne göre puanlanmalı."""
    from ui import autonomous

    prev = {"at": "test", "prediction": "up", "btc_price": 100.0}
    up = autonomous._score(prev, 102.0)
    down = autonomous._score(prev, 98.0)
    assert up is not None and up["correct"] is True
    assert down is not None and down["correct"] is False

    prev2 = {"at": "test", "prediction": "down_flat", "btc_price": 100.0}
    assert autonomous._score(prev2, 99.0)["correct"] is True
    assert autonomous._score(prev2, 103.0)["correct"] is False
    assert autonomous._score({}, 100.0) is None
    acc = autonomous.accuracy({"prediction_tests": [up, down]})
    assert acc["n"] == 2 and acc["rate"] == 50.0


def test_step1_daily_engine_and_brakes() -> None:
    """ADIM 1+2: günlük motor aktif, 1dk scalper kapalı, frenler tanımlı."""
    from ui import daily_engine, risk_brakes, tr_runner
    from ui import tr_scalper as t

    # 1dk scalper emri doğrudan reddediyor
    assert t.buy("XRP_TRY").get("ok") is False
    assert "KAPALI" in t.buy("XRP_TRY").get("reason", "")
    # motor günlük engine'i kullanıyor
    assert tr_runner.CYCLE is daily_engine.cycle
    # fren limitleri
    assert risk_brakes.DAILY_LOSS_PCT == 0.03
    assert risk_brakes.MAX_DD_PCT == 0.10
    assert risk_brakes.CRASH_PCT == 0.10
    assert risk_brakes.CRASH_WINDOW_MIN == 5
    # günlük strateji sabitleri
    assert daily_engine.EXIT_BELOW_EMA == 0.97
    assert daily_engine.MAX_HOLD_DAYS == 90


def test_readiness_checklist() -> None:
    from ui.live_readiness import assess

    items = assess()
    assert len(items) >= 10
    assert any(i["Sorumlu"] == "SİZ" for i in items)
    assert any("Lisanslı" in i["Madde"] for i in items)
    assert not any(i["Madde"].startswith("Gerçek emir hazır") for i in items)


def test_idempotency_when_unlocked() -> None:
    _clean()
    try:
        settings = default_settings()
        settings["live_trading"]["enabled"] = True
        settings["live_trading"]["allowed_symbols"] = ["THYAO"]
        with (
            patch.dict("os.environ", {"HSC_LIVE_ARMED": "YES"}),
            patch("ui.broker.live_configured", return_value=True),
            patch("ui.live_guard.check", return_value=(True, [], settings["live_trading"])),
            patch("ui.broker.place_live_order", return_value={"ok": True, "id": "X1"}),
        ):
            first = live_bot.execute(
                USER, "THYAO", "AL", 1, 100, phrase="HSC-LIVE-ARM",
                session_armed=True, settings=settings,
            )
            second = live_bot.execute(
                USER, "THYAO", "AL", 1, 100, phrase="HSC-LIVE-ARM",
                session_armed=True, settings=settings,
            )
        assert first.get("ok") is True
        assert second.get("ok") is False and "zaten kayıtlı" in second.get("reason", "")
        assert len(live_bot.recent_orders(USER)) == 1
    finally:
        _clean()
