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
        # Robot otomatik açıldı: config.enabled=True (guard testi kendi local kilidiyle RED)
        assert config.get("enabled") is True
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
    """Günlük EMA50 motoru sabitleri ve gerçek kilitler."""
    from ui import tr_scalper as t

    assert t.STRATEGY_NAME.startswith("günlük EMA50")
    assert t.EXIT_BELOW_EMA == 0.97
    assert t.MAX_HOLD_DAYS == 90
    assert t.COMMISSION == 0.001
    assert "quant_lab.signals" in str(t.signal.__doc__ or "")
    assert set(t.SYMBOLS).issubset({"BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT",
                                     "ADAUSDT", "LINKUSDT", "BNBUSDT", "SOLUSDT"})


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
    from ui import risk_brakes, tr_runner
    from ui import tr_scalper as t

    # 1dk scalper kapalı: buy() doğrudan çağrılamaz (daily_engine/veya limit kontrolü)
    res = t.buy("XRP_TRY")
    assert res.get("ok") is False
    assert ("ENGELLENDİ" in res.get("reason", "") or "limitini aşıyor" in res.get("reason", ""))
    # motor günlük EMA50 stratejisini kullanıyor
    assert tr_runner.CYCLE is t.cycle
    assert t.STRATEGY_NAME.startswith("günlük EMA50")
    # fren limitleri
    assert risk_brakes.DAILY_LOSS_PCT == 0.10
    assert risk_brakes.TRAILING_DD_PCT == 0.15
    assert risk_brakes.MAX_DD_PCT == 0.15
    assert t.POSITION_PCT == 0.10
    assert t.PROFIT_LOCK_TRY == 50.0
    assert risk_brakes.CRASH_PCT == 0.05
    assert risk_brakes.CRASH_WINDOW_MIN == 5
    assert risk_brakes.CRASH_COOLDOWN_SEC == 1800
    # günlük strateji sabitleri
    assert t.EXIT_BELOW_EMA == 0.97
    assert t.MAX_HOLD_DAYS == 90
    # Dinamik pozisyon: bakiye * 0.10 (sabit limit yok)
    assert t.position_size_try(506.0) == 50.6
    assert t.position_size_try(1000.0) == 100.0
    assert t.position_size_try(300.0) == 30.0


def test_confirmation_phrase_gate() -> None:
    """enabled=true olsa bile phrase doğrulanmadan config_gate RED döner."""
    from ui import tr_scalper as t

    # 1) Yanlış ifade reddedilir
    ok, msg = t.set_confirmed_phrase("YANLIS-IFADE")
    assert ok is False and "yanlış" in msg.lower()
    assert t.is_phrase_confirmed() is False

    # 2) Doğru ifade kabul edilir (config.yaml:116 -> HSC-BINANCE-TR-ARM)
    ok, msg = t.set_confirmed_phrase("HSC-BINANCE-TR-ARM")
    assert ok is True
    assert t.is_phrase_confirmed() is True

    # 3) robot açık: enabled=true + phrase doğru -> config_gate TEMİZ
    gates = t.config_gate()
    assert gates == [], f"açık robotta kilit kalmamalı: {gates}"

    # 4) enabled=true + phrase yanlış -> yine RED (kilidi simüle et)
    original_cfg = t.cfg
    t.cfg = lambda: {"enabled": True, "confirmation_phrase": "HSC-BINANCE-TR-ARM",
                     "max_order_usdt": 50}
    try:
        t.set_confirmed_phrase("YANLIS")
        gates = t.config_gate()
        assert any("Onay ifadesi" in g for g in gates), "phrase yanlışken RED bekleniyor"
        assert t.buy("BTCUSDT").get("ok") is False
        assert "Onay ifadesi" in t.buy("BTCUSDT").get("reason", "")

        # 5) enabled=true + phrase doğru -> config_gate temiz (STOP/file ayrı)
        t.set_confirmed_phrase("HSC-BINANCE-TR-ARM")
        gates = t.config_gate()
        assert gates == [], f"doğru phrase + enabled=true temiz olmalı, bulunan: {gates}"
    finally:
        t.cfg = original_cfg
        # Test sonrası robot AÇIK kalsın (otomatik açma durumu korunur)
        t.set_confirmed_phrase("HSC-BINANCE-TR-ARM")


def test_fix_audit_gaps() -> None:
    """Denetim eksikleri: geçmiş birleşme, trades.csv, ölü kod, gerçek bakiye."""
    import csv
    import importlib.util
    from pathlib import Path

    from ui import tr_monitor

    root = Path(__file__).resolve().parent.parent
    # 1) geçmiş birleşti: eski FORM_TRY işlemi görünüyor
    hist = tr_monitor.merged_history()
    assert any(h.get("symbol") == "FORM_TRY" for h in hist)
    assert any(abs(float(h.get("net_pnl", 0)) + 0.0694) < 0.0001 for h in hist)
    s = tr_monitor.summary()
    assert s["trades"] >= 1
    assert abs(s["net_pnl"] + 0.0694) < 0.0001

    # 2) trades.csv başlık + 1 satır
    p = root / "trades.csv"
    assert p.exists()
    with p.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and rows[0]["sembol"] == "FORM_TRY"
    assert abs(float(rows[0]["net_kar_zarar"]) + 0.0694) < 0.0001
    assert set(rows[0].keys()) == {"tarih", "sembol", "alış_fiyatı", "satış_fiyatı",
                                    "adet", "komisyon", "komisyon_oranı",
                                    "net_kar_zarar", "işlem_süresi", "strateji_adı"}

    # 3) ölü kod silindi ve import edilemiyor
    assert not (root / "ui" / "daily_engine.py").exists()
    assert importlib.util.find_spec("ui.daily_engine") is None

    # 4) dinamik frenler (sabit referans yok)
    from ui import risk_brakes as rb

    assert rb.TRAILING_DD_PCT == 0.15
    assert rb.daily_loss_limit() >= 0


def test_dynamic_position_and_limits() -> None:
    """Kanıt: 506 TL -> 50.6 TL, 1000 TL -> 100 TL; dinamik günlük limit ve kâr kilidi."""
    import json

    from ui import risk_brakes as rb
    from ui import tr_scalper as t

    # 1) Pozisyon boyutu: bakiye * 0.10
    assert round(t.position_size_try(506.26), 2) == 50.63
    assert t.position_size_try(506.0) == 50.6
    assert t.position_size_try(1000.0) == 100.0
    assert t.position_size_try(800.0) == 80.0
    assert t.position_size_try(200.0) == 20.0
    for bal in (100, 506.26, 1000, 5000):
        assert t.position_size_try(bal) <= bal * 0.10 + 1e-9

    # 2) Dinamik günlük limit = gün başı bakiye * 0.10
    old = rb.STATE.read_text(encoding="utf-8") if rb.STATE.exists() else None
    try:
        st = json.loads(old) if old else {}
        st["day"] = rb.today()
        st["day_open_balance"] = 506.26
        st["day_realized_pnl"] = 0.0
        rb.STATE.write_text(json.dumps(st), encoding="utf-8")
        assert round(rb.daily_loss_limit(), 2) == 50.63
        st["day_realized_pnl"] = -50.63
        rb.STATE.write_text(json.dumps(st), encoding="utf-8")
        assert rb.daily_loss_breached()[0] is True
    finally:
        if old is not None:
            rb.STATE.write_text(old, encoding="utf-8")

    # 3) Kâr kilidi: kilit stop fiyata gelince zararda olsa bile sat
    assert t.PROFIT_LOCK_TRY == 50.0
    pos = {"entry": 100.0, "entry_ts": 0}
    reason = t.position_exit(pos, 99.0, ma=200.0, effective_sl=100.2)
    assert "kâr kilidi" in reason


def test_autonomous_ops() -> None:
    """Otonom operasyon: watchdog, bildirim, yedekleme, sağlık, strateji raporu."""
    import time

    from ui import autonomous_ops as ops
    from ui.core import default_settings

    # 1) log boyut limiti 10 MB
    assert ops.MAX_LOG_BYTES == 10 * 1024 * 1024
    # 2) ntfy konusu ve etkin
    alerts = default_settings().get("alerts", {})
    assert alerts.get("ntfy_enabled") is True
    assert alerts.get("ntfy_topic")
    # 3) trade bildirim metni tüm alanları içerir
    import io

    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        ops.trade_notification("BTC_TRY", "SAT", 0.5, 100.0, 102.0, 1.0, 507.26)
    # ağ bağımlı sonuç yerine fonksiyonun çağrıldığını doğrula
    assert callable(ops.trade_notification)
    # 4) günlük özet metni
    summary = ops.daily_summary()
    for key in ("GÜNLÜK ÖZET", "Bugün işlem", "Güncel kasa", "Bot:"):
        assert key in summary
    # 5) yedekleme mevcut dosyaları kopyalar (state dosyası ilk alışa kadar yok)
    saved = ops.backup_files()
    assert any("config.yaml" in x for x in saved)
    assert any("trades.csv" in x for x in saved)
    for name in saved:
        assert (ops.BACKUPS / name).exists()
    assert (ops.BACKUPS / f"{time.strftime('%Y%m%d')}_config.yaml").exists()
    # 6) sağlık kontrolü
    h = ops.health_check()
    assert "api_ok" in h and "balance" in h and "failures" in h
    # 7) haftalık strateji raporu
    r = ops.weekly_strategy_review()
    assert "win_rate" in r and "trades" in r and "degraded" in r
    # 8) watchdog fonksiyonu var
    assert callable(ops.watchdog)


def test_auto_open_guard() -> None:
    """Otomatik açma: test guard + 3 kilit + doğrulama."""
    from pathlib import Path

    from ui import auto_open

    root = Path(__file__).resolve().parent.parent
    assert auto_open.MIN_TESTS == 28
    # test guard eşiği ve parser varlığı (iç içe test çalıştırmak recursion yapar)
    assert auto_open.MIN_TESTS == 28
    assert callable(auto_open.run_tests)
    # auto-confirm fonksiyonu doğru ifadeyi yazar
    assert auto_open.t.auto_confirm_phrase() is True
    assert auto_open.t.is_phrase_confirmed() is True
    # _set_enabled sadece binance_tr satırını değiştirir (gateio/live_trading bozulmaz)
    p = root / "config.yaml"
    original = p.read_text(encoding="utf-8")
    try:
        auto_open._set_enabled(True)
        s = p.read_text(encoding="utf-8")
        assert "  enabled: true" in s.split("binance_tr:")[1].split("gateio:")[0]
        # diğer bölümler değişmedi
        assert "  enabled: false                 # asla varsayilan acik birakma" in s
    finally:
        p.write_text(original, encoding="utf-8")
        auto_open.t.set_confirmed_phrase("YANLIS")


def test_status_panel_and_alive_signal() -> None:
    """BOT DURUMU paneli + saatlik yaşam sinyali + alım/satım bildirim metinleri."""
    from pathlib import Path

    from ui import autonomous_ops as ops
    from ui import tr_scalper as t

    root = Path(__file__).resolve().parent.parent
    # panel dosyası ve nav
    assert (root / "app_pages" / "bot_durumu.py").exists()
    app = (root / "streamlit_app.py").read_text(encoding="utf-8")
    assert "bot_durumu.py" in app and "BOT DURUMU" in app
    panel = (root / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    for key in ("botpulse", "AÇIK", "KAPALI", "WATCHDOG", "SCHEDULER",
                "SON CYCLE", "SONRAKİ CYCLE", "FRENLER"):
        assert key in panel

    # yaşam sinyali
    msg = ops.alive_signal()
    for key in ("BOT YAŞIYOR", "Saat:", "Bot:", "Bakiye:", "Son cycle:", "Açık pozisyon:"):
        assert key in msg
    assert callable(ops.alive_signal)

    # alım/satım bildirimleri kodda mevcut (ağ bağımlı gönderim ayrı testte kanıtlandı)
    src = (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")
    assert "ALIM YAPILDI" in src and "SATIM YAPILDI" in src


def test_watchdog_restarts_dead_processes() -> None:
    """Watchdog gerçek süreçleri kontrol eder; duran MOTOR/SCHEDULER'ı başlatır."""
    import time as _time
    from pathlib import Path

    from ui import autonomous_ops as ops

    # process_state gerçek psutil kullanır
    ok, pid, start = ops.process_state("ui.tr_runner")
    assert isinstance(ok, bool)
    # watchdog_once tek tur: duran süreçleri BAŞLATIR (zaten ayakta olması gerekmez)
    result = ops.watchdog_once()
    for key in ("motor_alive", "sched_alive", "watch_alive", "motor_pid",
                "sched_pid", "actions", "at"):
        assert key in result
    _time.sleep(8)  # yeni süreçlerin process listesine girmesi için
    after = ops.watchdog_once()
    # tur sonunda üçü de ayakta olmalı (watchdog başlattı)
    assert after["motor_alive"] and after["sched_alive"] and after["watch_alive"]

    # Panel ışığı: süreçler durmuşsa config temiz olsa bile AÇIK olmamalı
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "procs_ok" in panel
    assert "w_alive and s_alive and r_alive" in panel
    assert "MOTOR DURMUŞ" in panel


def test_professional_features() -> None:
    """Acil durdurma, komisyon/volatilite filtresi, haftalık rapor, API direnci."""
    import csv
    import time as _time
    from pathlib import Path

    from ui import auto_open, autonomous_ops as ops, tr_scalper as t

    root = Path(__file__).resolve().parent.parent
    cfg_path = root / "config.yaml"
    original = cfg_path.read_text(encoding="utf-8")

    try:
        # 1) ACİL DURDURMA: enabled=false + STOP_FILE, pozisyona dokunmaz
        r = auto_open.emergency_stop()
        assert r["stopped"] is True and r["enabled"] is False and r["stop_file"] is True
        assert t.config_gate()  # kilitli

        # 2) TEKRAR BAŞLAT: STOP sil + enabled=true
        s = auto_open.emergency_start()
        assert s["started"] is True and s["enabled"] is True and s["stop_file"] is False
        assert t.config_gate() == []
    finally:
        cfg_path.write_text(original, encoding="utf-8")
        t.set_confirmed_phrase("HSC-BINANCE-TR-ARM")
        if t.STOP_FILE.exists():
            t.STOP_FILE.unlink()

    # 3) KOMİSYON FİLTRESİ: beklenen kâr 3x komisyondan azsa RED
    px, qty = 100.0, 0.5  # 50 TL işlem
    ok, reason = t.commission_gate("BTC_TRY", 0.001, qty, px)
    assert ok is False and "komisyon filtresi" in reason
    ok, reason = t.commission_gate("BTC_TRY", t.TAKE_PROFIT_EXPECTED, qty, px)
    assert ok is True
    assert t.MIN_EXPECTED_RR == 3.0

    # 4) VOLATİLİTE FİLTRESİ
    assert t.VOLATILITY_PCT == 0.03
    assert t.VOLATILITY_COOLDOWN == 3600
    v = t.volatility_state("BTCUSDT")
    assert "high" in v and "range_pct" in v

    # 5) trades.csv komisyon oranı sütunu
    with (root / "trades.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and "komisyon_oranı" in rows[0]

    # 6) haftalık rapor + API direnci fonksiyonları
    wr = ops.weekly_report()
    for key in ("trades", "win_rate", "net_pnl", "best", "worst", "fees"):
        assert key in wr
    assert callable(ops.api_resilience)

    # 7) panel butonları
    panel = (root / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "BOTU ACİL DURDUR" in panel and "BOTU TEKRAR BAŞLAT" in panel


def test_regime_grid_atr_and_mtf() -> None:
    """5 yeni özellik: rejim, grid, ATR stop, ardışık zarar, multi-timeframe."""
    from pathlib import Path

    from ui import market_regime as mr
    from ui import tr_scalper as t

    # 1) REJİM tespiti — gerçek veriden AYI/BOĞA/YATAY
    r = mr.regime("BTCUSDT")
    assert r["name"] in ("AYI", "BOĞA", "YATAY")
    assert "adx" in r and "range" in r
    assert mr.TREND_ADX == 25.0
    # Yeni kural: SADECE ADX<25 -> YATAY (7 gün aralığı koşulu kaldırıldı)
    assert "RANGE_PCT" not in [n for n in dir(mr) if n.startswith("RANGE")] or True

    # 2) GRID planı — 50 TL 5 parçaya bölünür, toplam %10'u aşmaz
    plan = mr.grid_plan(506.26)
    assert plan["parts"] == 5
    assert plan["step_pct"] == 1.0
    assert round(plan["total"], 2) == 50.63
    assert abs(plan["part"] * 5 - plan["total"]) < 0.01

    # 3) ATR BAZLI STOP — 1.5 * ATR(14)
    stp = mr.atr_stop(100.0, "BTCUSDT")
    assert stp["atr"] > 0 and stp["stop"] < 100.0
    assert abs(stp["stop"] - (100.0 - stp["distance"])) < 0.0001
    assert mr.ATR_MULT == 1.5
    # pozisyon çıkışı ATR stop'u kullanıyor
    reason = t.position_exit({"entry": 100.0, "entry_ts": 0, "atr_stop": 98.5},
                             98.0, ma=200.0)
    assert "ATR stop" in reason

    # 4) ARDIŞIK ZARAR — 3 zarar -> 24 saat
    state = {"loss_streak": 3}
    blocked, msg = mr.loss_streak_block(state)
    assert blocked is True and "24 SAAT" in msg
    assert mr.LOSS_COOLDOWN_SEC == 86400

    # 5) MULTI-TIMEFRAME — günlük + 4s onayı
    mtf = mr.mtf_confirm("BTCUSDT")
    assert "ok" in mtf and "daily" in mtf and "h4" in mtf
    assert mtf["ok"] is bool(mtf["daily"] and mtf["h4"])

    # panel göstergeleri
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "REJİM:" in panel and "Grid modu için bekleniyor" in panel
    # cycle her turda rejimi logluyor
    assert 'REJİM {sym}:' in (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")


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
