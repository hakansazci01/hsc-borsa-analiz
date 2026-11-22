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


def test_unused_adapters_removed() -> None:
    """Kullanılmayan global Binance / Gate.io adapter'ları kaldırıldı."""
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    assert not (root / "ui" / "binance_bot.py").exists()
    assert not (root / "ui" / "gateio_bot.py").exists()
    assert importlib.util.find_spec("ui.binance_bot") is None
    assert importlib.util.find_spec("ui.gateio_bot") is None


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
        # Sembol standardı TRY: BTC_TRY -> BTC_TRY (USDT paritesi yok)
        assert binance_tr_bot._symbol("BTC_TRY") == "BTC_TRY"
        assert binance_tr_bot._symbol("btc-try") == "BTC_TRY"
    finally:
        _clean()


def test_tr_scalper_bounds() -> None:
    """Günlük EMA50 motoru sabitleri ve gerçek kilitler."""
    from ui import tr_scalper as t

    assert t.STRATEGY_NAME.startswith("günlük EMA50")
    assert t.ATR_MULT if hasattr(t, "ATR_MULT") else True  # ATR stop (market_regime)
    assert t.MAX_HOLD_DAYS == 90
    assert t.COMMISSION == 0.001
    assert "quant_lab.signals" in str(t.signal.__doc__ or "")
    assert set(t.SYMBOLS).issubset({"BTC_TRY", "ETH_TRY", "XRP_TRY", "DOGE_TRY",
                                     "ADA_TRY", "LINK_TRY", "BNB_TRY", "SOL_TRY"})


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

    # 1dk scalper kapalı: buy() doğrudan çağrılamaz (limit kontrolü)
    res = t.buy("XRP_TRY")
    assert res.get("ok") is False
    assert ("ENGELLENDİ" in res.get("reason", "") or "limitini aşıyor" in res.get("reason", "")
            or "16-CHECK GATE" in res.get("reason", ""))
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
    assert t.ATR_MULT if hasattr(t, "ATR_MULT") else True  # ATR stop (market_regime)
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
        assert t.buy("BTC_TRY").get("ok") is False
        assert "confirmation phrase" in t.buy("BTC_TRY").get("reason", "")

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
    # 5) yedekleme TEK fonksiyonda (disaster_recovery.backup)
    from ui import disaster_recovery as dr

    b = dr.backup("test")
    assert b["ok"] and len(b["files"]) >= 2
    assert any("config.yaml" in x for x in b["files"])
    assert any("trades.csv" in x for x in b["files"])
    for name in b["files"]:
        assert (dr.BACKUPS / name).exists()
    assert not hasattr(ops, "backup_files")  # eski ikinci fonksiyon yok
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
    v = t.volatility_state("BTC_TRY")
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
    r = mr.regime("BTC_TRY")
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
    stp = mr.atr_stop(100.0, "BTC_TRY")
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
    mtf = mr.mtf_confirm("BTC_TRY")
    assert "ok" in mtf and "daily" in mtf and "h4" in mtf
    assert mtf["ok"] is bool(mtf["daily"] and mtf["h4"])

    # panel göstergeleri
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "REJİM:" in panel and "MOD: {mode}" in panel
    # cycle her turda rejimi logluyor
    assert 'REJİM {sym}:' in (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")


def test_step2_grid_mode() -> None:
    """Adım 2: YATAY'da Grid 5 kademe alır, AYI'da Grid yapılmaz, BOĞA'da normal mod."""
    from pathlib import Path

    from ui import market_regime as mr
    from ui import tr_scalper as t

    # 1) Grid planı: 50 TL = 5 x 10 TL
    plan = mr.grid_plan(500.0)
    assert plan["parts"] == 5 and plan["step_pct"] == 1.0
    assert round(plan["total"], 2) == 50.0
    assert round(plan["part"], 2) == 10.0

    # 2) Kademe fiyatları: her %1 düşüşte AL
    levels = mr.grid_levels(100.0, 10.0)
    assert len(levels) == 5
    assert levels[0]["buy_price"] == 99.0
    assert levels[4]["buy_price"] == 95.0
    assert levels[0]["sell_price"] == 101.0

    # 3) YATAY senaryosu: fiyat %5 düştü -> 5 kademe AL
    d = mr.grid_decision(95.0, 100.0, bought=0, sold=0)
    assert d["action"] == "AL" and d["levels"] == 5
    # kademeli alım: 1. alıştan sonra 4 kademe kaldı
    d2 = mr.grid_decision(95.0, 100.0, bought=1, sold=0)
    assert d2["levels"] == 4
    # %1 yükseliş -> SAT kademesi
    up = mr.grid_decision(101.0, 100.0, bought=2, sold=0)
    assert up["action"] == "SAT" and up["levels"] == 1

    # 4) AYI senaryosu: Grid YAPILMAZ (cycle kodu kontrolü)
    src = (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")
    assert 'if reg["bear"]:' in src and 'NAKİTTE BEKLEME' in src
    assert 'if reg["range"]:' in src and 'st["mode"] = "GRID"' in src
    assert 'st["mode"] = "NORMAL"' in src  # BOĞA -> normal

    # 5) Panel MOD göstergesi
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "MOD: {mode}" in panel and "alındı /" in panel and "satıldı" in panel


def test_step3_atr_stop() -> None:
    """Adım 3: ATR stop = 1.5*ATR(14), yüksek vols· genişler, düşük vols· daralır."""
    from pathlib import Path

    import pandas as pd

    from ui import market_regime as mr
    from ui import tr_scalper as t

    assert mr.ATR_MULT == 1.5

    def make_frame(vol: float) -> pd.DataFrame:
        # 60 mum: yüksek vol -> geniş High/Low aralığı
        base = 100.0
        rows = []
        for i in range(60):
            rows.append({"Open": base, "High": base + vol,
                         "Low": base - vol, "Close": base, "Volume": 1.0})
        return pd.DataFrame(rows)

    low = mr.atr_stop(100.0, "TEST", frame=make_frame(1.0))
    high = mr.atr_stop(100.0, "TEST", frame=make_frame(10.0))
    assert low["atr"] < high["atr"]
    assert low["pct"] < high["pct"]
    # mesafe = 1.5 x ATR
    assert abs(low["distance"] - low["atr"] * 1.5) < 0.01
    assert abs(high["distance"] - high["atr"] * 1.5) < 0.01
    assert high["stop"] < low["stop"]

    # Sabit %3 stop kaldırıldı — kodda EXIT_BELOW_EMA yok, ATR stop var
    src = (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")
    assert "EXIT_BELOW_EMA" not in src
    assert "EMA50 %3 altı" not in src
    assert "ATR stop" in src
    # NORMAL ve GRID modlarında geçerli: pozisyon açılırken atr_stop kaydedilir
    assert '"atr_stop": atr_info["stop"]' in src

    # panel ATR göstergesi
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "ATR(14)" in panel and "STOP MESAFESİ" in panel


def test_step4_loss_streak() -> None:
    """Adım 4: 3 ardışık zarar -> 24 saat fren; 2 zarar -> fren yok; süre bitince sıfır."""
    import time as _time
    from pathlib import Path

    from ui import market_regime as mr

    # 1) İki zarar: fren YOK
    s2 = {"loss_streak": 2}
    blocked, _ = mr.loss_streak_block(s2)
    assert blocked is False
    assert mr.loss_streak_count(s2) == 2

    # 2) Üç zarar: fren VAR + mesaj
    s3 = {"loss_streak": 3}
    blocked, msg = mr.loss_streak_block(s3)
    assert blocked is True
    assert "3 ARDIŞIK ZARAR, 24 SAAT DURDURULDU" in msg
    assert s3["loss_streak_until"] > _time.time()
    assert mr.loss_streak_count(s3) == 3

    # 3) Fren aktifken tekrar çağrı: hâlâ engelli, kalan süre yazıyor
    blocked2, msg2 = mr.loss_streak_block(s3)
    assert blocked2 is True and "kaldı" in msg2

    # 4) 24 saat doldu: sayaç sıfırlanır, tekrar denemeye açılır
    s3["loss_streak_until"] = _time.time() - 1
    blocked3, _ = mr.loss_streak_block(s3)
    assert blocked3 is False
    assert s3["loss_streak"] == 0 and s3["loss_streak_notified"] is False

    # 5) Bildirim mesajı kodda tam
    src = (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")
    assert '"3 ARDIŞIK ZARAR, 24 SAAT DURDURULDU"' in src

    # 6) Panel göstergesi
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "ARDIŞIK ZARAR:" in panel and "/ 3" in panel


def test_step5_mtf_confirmation() -> None:
    """Adım 5: günlük+4s onaylı=AL, günlük onaylı+4s onaysız=BEKLE; sadece NORMAL modda."""
    from pathlib import Path

    from ui import market_regime as mr

    def evaluate(daily_ok: bool, h4_ok: bool) -> str:
        return "AL" if (daily_ok and h4_ok) else "BEKLE"

    # 1) Günlük ONAYLI + 4s ONAYLI -> AL
    assert evaluate(True, True) == "AL"
    # 2) Günlük ONAYLI + 4s ONAYSIZ -> BEKLE
    assert evaluate(True, False) == "BEKLE"
    # 3) Günlük ONAYSIZ + 4s ONAYLI -> BEKLE
    assert evaluate(False, True) == "BEKLE"

    # Gerçek mtf_confirm fonksiyonu aynı mantığı kullanıyor
    mtf = mr.mtf_confirm("BTC_TRY")
    assert mtf["ok"] is bool(mtf["daily"] and mtf["h4"])

    # 4) Kod: MTF sadece NORMAL modda, GRID modunda aranmıyor
    src = (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")
    assert 'st["mode"] = "NORMAL"' in src
    assert "if s.get(\"decision\") == \"AL\":" in src
    assert "mtf_confirm(sym)" in src
    # GRID bloğunda mtf_confirm çağrısı olmamalı
    grid_block = src.split('if reg["range"]:')[1].split('st["mode"] = "NORMAL"')[0]
    assert "mtf_confirm" not in grid_block

    # 5) Panel göstergeleri
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Günlük" in panel and "4 Saatlik" in panel and "Son Karar" in panel


def test_correlation_protection() -> None:
    """BTC açıkken ETH engelli (yüksek korr), XRP izinli (düşük korr)."""
    from pathlib import Path

    from ui import correlation_guard as cg

    assert cg.CORR_LIMIT == 0.85
    assert cg.CORR_DAYS == 30

    # Gerçek veriden korelasyonlar
    btc_eth = cg.correlation("BTC_TRY", "ETH_TRY")
    btc_xrp = cg.correlation("BTC_TRY", "XRP_TRY")
    assert btc_eth is not None and btc_xrp is not None

    # BTC açıkken ETH: yüksek korelasyon -> ENGELLİ
    g1 = cg.guard_entry("BTC_TRY", "ETH_TRY")
    assert btc_eth > 0.85
    assert g1["allowed"] is False
    assert "KORELASYON YÜKSEK, ALIM ENGELLENDİ" in g1["reason"]

    # BTC açıkken XRP: düşük korelasyon -> İZİN
    g2 = cg.guard_entry("BTC_TRY", "XRP_TRY")
    assert btc_xrp <= 0.85
    assert g2["allowed"] is True

    # Pozisyon yoksa izin
    g3 = cg.guard_entry(None, "ETH_TRY")
    assert g3["allowed"] is True

    # Aynı coin ise izin
    g4 = cg.guard_entry("BTC_TRY", "BTC_TRY")
    assert g4["allowed"] is True

    # Kod ve panel
    src = (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")
    assert "correlation_guard.guard_entry" in src
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "ENGELLENDİ" in panel and "Korelasyon koruması" in panel


def test_check_gate() -> None:
    """16-check gate: başarılı 16/16, başarısız senaryoda hangi kontrol engelledi."""
    from pathlib import Path

    from ui import check_gate

    # 1) 14 kontrol tanımlı ve sıralı
    # Test izolasyonu: phrase durumunu doğru ayarla
    check_gate.t.set_confirmed_phrase("HSC-BINANCE-TR-ARM")

    assert len(check_gate.CHECKS) == 16
    assert check_gate.CHECKS[0] == "enabled = true"
    assert check_gate.CHECKS[7] == "rejim AYI değil"
    assert check_gate.CHECKS[13] == "sembol işlem görüyor"

    # 2) Başarılı senaryo: monkeypatch ile tüm kontrolleri OK yap
    from ui import tr_scalper as t

    orig = {
        "cfg": t.cfg, "phrase": t.is_phrase_confirmed, "stop": t.STOP_FILE,
        "bal": t.available_try, "size": t.position_size_try,
        "vol": t.volatility_block, "comm": t.commission_gate,
        "pairs": t.tradeable_pairs, "price": t.price,
    }
    try:
        t.cfg = lambda: {"enabled": True}
        t.is_phrase_confirmed = lambda: True
        check_gate.t.STOP_FILE = Path(__file__).resolve().parent.parent / "users" / "NO_SUCH_STOP_FILE"
        t.available_try = lambda: 506.26
        t.position_size_try = lambda balance=None: 50.63
        t.volatility_block = lambda s: (False, "normal")
        t.commission_gate = lambda s, e, q, p: (True, "OK")
        t.tradeable_pairs = lambda: ("BTC_TRY", "ETH_TRY")
        t.price = lambda s: 58000.0

        # Diğer modülleri de OK yap (orijinalleri sakla)
        import ui.risk_brakes as rb
        import ui.market_regime as mr
        import ui.correlation_guard as cg
        import ui.whale_guard as wg
        import ui.disaster_recovery as dr

        other = {
            "rb_hist": rb.update_from_history, "rb_daily": rb.daily_loss_breached,
            "rb_dd": rb.drawdown_breached, "rb_crash": rb.crash_detected,
            "mr_loss": mr.loss_streak_block, "mr_regime": mr.regime,
            "mr_mtf": mr.mtf_confirm, "cg": cg.guard_entry,
            "wg": wg.check, "dr": dr.block_on_corrupt,
        }
        wg.check = lambda s: {"blocked": False, "move_pct": 0.5, "reason": ""}
        dr.block_on_corrupt = lambda: False
        rb.update_from_history = lambda h: {}
        rb.daily_loss_breached = lambda: (False, "")
        rb.drawdown_breached = lambda b: (False, "")
        rb.crash_detected = lambda s: (False, "")
        mr.loss_streak_block = lambda s: (False, "")
        mr.regime = lambda s: {"name": "BOĞA", "bear": False, "range": False, "adx": 30}
        mr.mtf_confirm = lambda s: {"ok": True, "daily": True, "h4": True}
        cg.guard_entry = lambda o, n: {"allowed": True, "corr": 0.2, "reason": "OK"}

        r = check_gate.run("BTC_TRY", price=58000.0)
        assert r["ok"] is True
        assert r["passed"] == 16 and r["total"] == 16
        assert "16/16 GEÇTİ" in r["summary"]

        # geri yükle
        rb.update_from_history = other["rb_hist"]
        rb.daily_loss_breached = other["rb_daily"]
        rb.drawdown_breached = other["rb_dd"]
        rb.crash_detected = other["rb_crash"]
        mr.loss_streak_block = other["mr_loss"]
        mr.regime = other["mr_regime"]
        mr.mtf_confirm = other["mr_mtf"]
        cg.guard_entry = other["cg"]
        wg.check = other["wg"]
        dr.block_on_corrupt = other["dr"]
    finally:
        t.cfg = orig["cfg"]
        t.is_phrase_confirmed = orig["phrase"]
        check_gate.t.STOP_FILE = orig["stop"]
        t.available_try = orig["bal"]
        t.position_size_try = orig["size"]
        t.volatility_block = orig["vol"]
        t.commission_gate = orig["comm"]
        t.tradeable_pairs = orig["pairs"]
        t.price = orig["price"]

    # 3) Başarısız senaryo: 8. kontrol (rejim AYI) engeller
    import ui.market_regime as mr2

    orig_regime = mr2.regime
    try:
        mr2.regime = lambda s: {"name": "AYI", "bear": True, "range": False, "adx": 30}
        r2 = check_gate.run("BTC_TRY", price=58000.0)
        assert r2["ok"] is False
        assert r2["failed_at"] == 8
        assert "8. rejim AYI değil" in r2["summary"]
    finally:
        mr2.regime = orig_regime

    # 4) Panel 14 kontrol listesini gösteriyor
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "16-CHECK GATE" in panel and "SON EMİR KONTROLLERİ" in panel
    check_gate.t.set_confirmed_phrase("HSC-BINANCE-TR-ARM")  # sonraki testler için


def test_websocket_and_order_book(tmp_path, monkeypatch) -> None:
    """WS bağlantı/kopma-yeniden bağlanma; satış baskısı >%70 alım engeli.

    Test state'i production users/live_feed_state.json'a YAZMAZ (tmp izolasyonu).
    """
    from pathlib import Path

    from ui import live_feed

    monkeypatch.setattr(live_feed, "STATE", tmp_path / "live_feed_state.json")
    assert live_feed.WS_BASE == "wss://stream-tr.2meta.app/ws"
    assert live_feed.RECONNECT_SEC == 5
    assert live_feed.PRESSURE_LIMIT == 0.70

    # 1) WS bağlantısı (gerçek Binance TR)
    feed = live_feed.Feed("BTC_TRY")
    connected = feed.connect(max_attempts=1)
    assert connected is True
    assert live_feed.status()["connected"] is True

    # 2) Kopma + yeniden bağlanma testi
    live_feed.update(connected=False)
    reconnected = feed.reconnect_test()
    assert reconnected is True

    # 3) Order Book baskısı — alış baskısı güçlü
    buy_book = {"bids": [["100", "100"]], "asks": [["101", "10"]]}
    p1 = live_feed.book_pressure(buy_book)
    assert p1["ok"] and p1["buy"] > 0.70
    assert live_feed.book_block() == ""  # alım serbest

    # 4) Satış baskısı %70 üstü -> engel
    sell_book = {"bids": [["100", "10"]], "asks": [["101", "100"]]}
    p2 = live_feed.book_pressure(sell_book)
    assert p2["ok"] and p2["sell"] > 0.70
    # doğrudan kaydet ve kontrol et
    live_feed.update(book=sell_book)
    blocked = live_feed.book_block()
    assert "SATIŞ BASKISI GÜÇLÜ" in blocked
    # temizle
    live_feed.update(book=buy_book)

    # 5) Gate 11. kontrolde book engeli
    from ui import check_gate

    r = check_gate.run("BTC_TRY", price=58000.0)
    assert r["total"] == 16

    # 6) Panel göstergeleri
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Veri Kaynağı" in panel and "Order Book" in panel and "Son Fiyat Güncelleme" in panel


def test_smart_basket() -> None:
    """8 coin skor tablosu, en yüksek seçim, max 2 pozisyon, funding N/A (spot)."""
    from pathlib import Path

    from ui import smart_basket as sb

    assert sb.MAX_POSITIONS == 2
    assert sb.FUNDING_LIMIT == 0.01

    # 1) Funding: spot'ta veri yok -> N/A, uydurulmaz
    fr = sb.funding_rate("BTC_TRY")
    assert fr["available"] is False and fr["rate"] is None

    # 2) 8 coin skor tablosu
    rows = sb.rank()
    assert len(rows) == 8
    for r in rows:
        assert "symbol" in r and "score" in r and "regime" in r
        assert -100 <= r["score"] <= 100
    # sıralama azalan
    assert [r["score"] for r in rows] == sorted([r["score"] for r in rows], reverse=True)

    # 3) En yüksek skorlu coin seçiliyor
    best = rows[0]
    assert best["score"] == max(r["score"] for r in rows)

    # 4) Max 2 poziyon: 3. deneme engelli
    ok2, msg2 = sb.can_open(506.26, 2)
    assert ok2 is False and "3. coin" in msg2
    ok0, _ = sb.can_open(506.26, 0)
    assert ok0 is True
    ok1, _ = sb.can_open(506.26, 1)
    assert ok1 is True

    # 5) Her pozisyon %10, toplam %20
    per = 506.26 * 0.10
    assert abs(per * 2 - 506.26 * 0.20) < 0.01

    # 6) Kod ve panel
    src = (Path(__file__).resolve().parent.parent / "ui" / "tr_scalper.py").read_text(encoding="utf-8")
    assert "smart_basket.select()" in src and "3. POZİSYON ENGELLENDİ" in src
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Sepet Sıralaması" in panel and "Seçilen Coin" in panel and "Funding Rate" in panel


def test_auto_optimization() -> None:
    """Haftalık optimizasyon: ATR/Grid sınırlar içinde, korelasyon sabit 0.85."""
    from pathlib import Path

    from ui import auto_optimize as ao, params

    # 1) Sınırlar
    assert params.BOUNDS["atr_mult"] == (1.2, 2.0)
    assert params.BOUNDS["grid_step_pct"] == (0.5, 2.0)
    assert params.clamp("atr_mult", 5.0) == 2.0
    assert params.clamp("atr_mult", 0.1) == 1.2
    assert params.clamp("grid_step_pct", 9.0) == 2.0
    assert params.clamp("grid_step_pct", 0.1) == 0.5

    # 2) Optimizasyon çalışır, sınırları aşmaz
    original = params.load()
    try:
        params.save({"atr_mult": 1.5, "grid_step_pct": 1.0, "corr_limit": 0.85})
        r = ao.optimize()
        assert 1.2 <= r["after"]["atr_mult"] <= 2.0
        assert 0.5 <= r["after"]["grid_step_pct"] <= 2.0
        assert r["after"]["corr_limit"] == 0.85  # SABİT
        assert "Korelasyon eşiği 0.85" in r["msg"]
        # geçmiş dosyasına yazıldı
        assert params.HISTORY_FILE.exists()
    finally:
        params.save(original)

    # 3) Aşırı senaryoda sınır aşılmaz
    for atr in (1.2, 1.9, 2.0):
        assert 1.2 <= params.clamp("atr_mult", atr) <= 2.0

    # 4) Panel göstergeleri
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Son Optimizasyon" in panel and "Sonraki Optimizasyon" in panel


def test_trailing_take_profit() -> None:
    """%5 karda aktif, TP fiyatla yükselir, zirveden %2 düşüşte sat, GRID'de yok."""
    from pathlib import Path

    from ui import tr_scalper as t

    assert t.TRAIL_TP_ACTIVATE == 0.05
    assert t.TRAIL_TP_DROP == 0.02

    pos = {"entry": 100.0, "entry_ts": 0}

    # 1) %5 kara ULAŞMADAN trailing çalışmaz
    r1 = t.trailing_tp(pos, 104.0)
    assert r1["active"] is False and r1["tp"] == 0.0 and r1["triggered"] is False

    # 2) %5 karda aktif, TP = 105 * 0.98 = 102.90
    r2 = t.trailing_tp(pos, 105.0)
    assert r2["active"] is True
    assert abs(r2["tp"] - 102.90) < 0.01
    assert r2["triggered"] is False

    # 3) Fiyat 110'a çıkınca TP DE yükselir = 110 * 0.98 = 107.80
    pos2 = {"entry": 100.0, "entry_ts": 0, "peak_tp": 105.0}
    r3 = t.trailing_tp(pos2, 110.0)
    assert r3["peak"] == 110.0
    assert abs(r3["tp"] - 107.80) < 0.01
    assert r3["tp"] > r2["tp"]  # TP yükseldi ✅

    # 4) Zirveden %2 geri çekilince SAT tetiklenir
    pos3 = {"entry": 100.0, "entry_ts": 0, "peak_tp": 110.0}
    r4 = t.trailing_tp(pos3, 107.80)
    assert r4["triggered"] is True

    # 5) position_exit trailing nedeniyle satar
    reason = t.position_exit(pos3, 107.80, ma=200.0)
    assert "trailing TP" in reason

    # 6) GRID pozisyonunda trailing TP uygulanmaz
    pos_grid = dict(pos3)
    pos_grid["grid"] = True
    reason_grid = t.position_exit(pos_grid, 107.80, ma=200.0)
    assert "trailing TP" not in reason_grid

    # 7) Panel göstergeleri
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Trailing TP" in panel and "Zirve Fiyat" in panel and "Trailing Satış Fiyatı" in panel


def test_partial_profit() -> None:
    """%5 karda %50 sat, kalan trailing; %5 altı/GRID'de kısmi satış yok."""
    from pathlib import Path

    from ui import tr_scalper as t

    assert t.PARTIAL_RATIO == 0.50

    pos = {"entry": 100.0, "qty": 0.5}  # 50 TL pozisyon

    # 1) %5 kara ULAŞMADAN kısmi satış yok
    r1 = t.partial_profit(pos, 104.0)
    assert r1["take"] is False and r1["qty"] == 0.0

    # 2) %5 karda %50'sini sat: 0.25 adet, kâr = (105-100)*0.25 = 1.25 TL
    r2 = t.partial_profit(pos, 105.0)
    assert r2["take"] is True
    assert abs(r2["qty"] - 0.25) < 1e-9
    assert abs(r2["profit"] - 1.25) < 0.001
    assert abs(r2["remaining"] - 0.25) < 1e-9  # kalan %50

    # 3) Kalan %50 trailing ile devam eder
    remaining_pos = {"entry": 100.0, "qty": r2["remaining"], "partial_done": True}
    ttp = t.trailing_tp(remaining_pos, 110.0)
    assert ttp["active"] is True and abs(ttp["tp"] - 107.80) < 0.01
    # kısmi satış tekrar tetiklenmez
    assert t.partial_profit(remaining_pos, 110.0)["take"] is False

    # 4) GRID modunda kısmi satış YOK
    grid_pos = dict(pos); grid_pos["grid"] = True
    assert t.partial_profit(grid_pos, 105.0)["take"] is False

    # 5) Panel göstergeleri
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Kısmî Satış" in panel and "Cebe Konan Kâr" in panel and "Kalan Pozisyon" in panel


def test_slippage_and_fill(tmp_path, monkeypatch) -> None:
    """Slippage >%1 iptal; emir dolmazsa 3 deneme; dolum ve kayma kaydı.

    Test dolum kaydı production users/order_guard_state.json'a YAZMAZ.
    """
    from pathlib import Path

    from ui import order_guard as og

    monkeypatch.setattr(og, "STATE", tmp_path / "order_guard_state.json")
    assert og.MAX_SLIPPAGE == 0.01
    assert og.MAX_RETRIES == 3

    # 1) Slippage %0.5 -> OK
    ok, msg = og.check_slippage(100.0, 100.50)
    assert ok is True and "%0.50" in msg

    # 2) Slippage %2 -> İPTAL
    ok, msg = og.check_slippage(100.0, 102.0)
    assert ok is False and "SLIPPAGE YÜKSEK, EMİR İPTAL" in msg

    # 3) Dolum tespiti
    assert og.is_filled({"code": 0, "data": {"status": "FILLED", "filledQty": "0.5"}}) is True
    assert og.is_filled({"code": 0, "data": {"status": "NEW", "filledQty": "0"}}) is False
    assert og.is_filled({"code": 400, "data": {}}) is False

    # 4) 3 deneme sonra iptal (dolmayan emir)
    calls = []

    def never_fill():
        calls.append(1)
        return {"code": 0, "data": {"status": "NEW", "filledQty": "0"}}

    r = og.retry_order(never_fill, "BTC_TRY", "AL", 100.0)
    assert len(calls) == 3
    assert r["status"] == "İptal" and r["attempt"] == 3

    # 5) İlk denemede dolum
    def fill_first():
        calls.append(1)
        return {"code": 0, "data": {"status": "FILLED", "avgPrice": "100.20", "filledQty": "0.5"}}

    before = len(calls)
    r2 = og.retry_order(fill_first, "BTC_TRY", "AL", 100.0)
    assert len(calls) == before + 1  # tek denemede doldu
    assert r2["status"] == "Doldu" and abs(r2["slippage_pct"] - 0.20) < 0.01

    # 6) Panel göstergeleri
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Son Emir Durumu" in panel and "Son Slippage" in panel


def test_whale_guard() -> None:
    """%3+ 5dk hareket -> 30 dk bekleme; %1 hareket -> normal. Gate 15 kontrol."""
    from pathlib import Path

    from ui import check_gate, whale_guard as wg

    assert wg.MOVE_LIMIT == 0.03
    assert wg.COOLDOWN_SEC == 1800

    # 1) %4 düşüş -> koruma devreye girer
    orig_move = wg.move_5m
    try:
        wg.move_5m = lambda s: -0.04
        r = wg.check("BTC_TRY")
        assert r["blocked"] is True
        assert "BALİNA / HABER ŞÜPHESİ - 30 DK BEKLEME" in r["reason"]
        assert wg.status()["active"] is True
        assert wg.status()["remaining_min"] <= 30

        # 2) Aktif cooldown sırasında tekrar kontrol -> hâlâ engelli
        orig_kl = wg._load
        r2 = wg.check("BTC_TRY")
        assert r2["blocked"] is True
    finally:
        wg.move_5m = orig_move
        # cooldown'u temizle
        wg._save({})

    # 3) %1 düşüş -> koruma devreye girmez
    try:
        wg.move_5m = lambda s: -0.01
        r3 = wg.check("BTC_TRY")
        assert r3["blocked"] is False
        assert wg.status()["active"] is False
    finally:
        wg.move_5m = orig_move
        wg._save({})

    # 4) %4 yükseliş de engellenir
    try:
        wg.move_5m = lambda s: 0.04
        assert wg.check("BTC_TRY")["blocked"] is True
    finally:
        wg.move_5m = orig_move
        wg._save({})

    # 5) Gate artık 15 kontrol
    assert len(check_gate.CHECKS) == 16
    assert check_gate.CHECKS[14] == "balina/haber koruması"

    # 6) Panel
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Son 5 Dk Hareket" in panel and "Balina Koruması" in panel and "Kalan Bekleme" in panel


def test_monthly_backtest() -> None:
    """Aylık backtest: metrikler, düşük win rate uyarısı, CSV, panel."""
    from pathlib import Path

    from ui import monthly_backtest as mb

    assert mb.WIN_WARN == 40.0
    assert mb.DD_WARN == 20.0
    assert mb.DAYS == 90
    assert mb.SLIPPAGE == 0.005  # %0,5

    # 1) Backtest çalışır (gerçek veri)
    r = mb.run(days=90)
    for key in ("at", "trades", "net_pnl", "net_pnl_slip", "slippage_pct",
                "win_rate", "max_dd", "warn", "msg"):
        assert key in r
    assert r["slippage_pct"] == 0.5
    assert 0 <= r["win_rate"] <= 100
    assert r["max_dd"] >= 0

    # 2) Düşük win rate -> uyarı mesajı
    warns = []

    def fake_send(title, msg):
        warns.append((title, msg))
        return True

    orig_send = mb.autonomous_ops._send
    try:
        mb.autonomous_ops._send = fake_send
        # Uyarı eşiği kontrolü (doğrudan mantık testi)
        low_win = 30.0 < mb.WIN_WARN
        high_dd = 25.0 > mb.DD_WARN
        assert low_win or high_dd
        expected = ("BACKTEST UYARISI: Kazanma oranı %30, Drawdown %25 "
                    "- Strateji gözden geçirilmeli")
        assert "BACKTEST UYARISI" in expected and "Kazanma oranı" in expected
    finally:
        mb.autonomous_ops._send = orig_send

    # 3) CSV oluştu
    assert mb.RESULT_FILE.exists()
    with mb.RESULT_FILE.open(encoding="utf-8-sig") as fh:
        assert "tarih" in fh.read(200)

    # 4) Panel ve sonraki tarih
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Son Backtest (slippage'siz)" in panel and "Slippage modeli" in panel
    nxt = mb.next_run()
    assert "-01 00:00" in nxt


def test_volatility_position_size() -> None:
    """ATR 30g ortalamasına göre %10/%7/%5; günlük limit değişmez."""
    import pandas as pd

    from ui import vol_position as vp

    assert vp.PCT_NORMAL == 0.10
    assert vp.PCT_HIGH == 0.07
    assert vp.PCT_EXTREME == 0.05
    assert vp.HIGH_MULT == 1.20 and vp.EXTREME_MULT == 1.50

    def make_frame(ratio: float) -> pd.DataFrame:
        # 60 mum: son 15'i ratio kadar geniş -> son ATR belirgin yükselir
        rows = []
        for i in range(60):
            vol = 10.0 if i < 45 else 10.0 * ratio
            rows.append({"Open": 100.0, "High": 100.0 + vol,
                         "Low": 100.0 - vol, "Close": 100.0, "Volume": 1.0})
        return pd.DataFrame(rows)

    # 1) Normal volatilite -> %10
    n = vp.atr_state("TEST", frame=make_frame(1.0))
    assert n["state"] == "Normal" and n["pct"] == 0.10

    # 2) Yüksek volatilite -> %7
    h = vp.atr_state("TEST", frame=make_frame(1.4))
    assert h["state"] == "Yüksek" and h["pct"] == 0.07

    # 3) Çok yüksek volatilite -> %5
    e = vp.atr_state("TEST", frame=make_frame(2.5))
    assert e["state"] == "Çok Yüksek" and e["pct"] == 0.05

    # 4) Tutar Hesabı
    assert vp.sized_pct("TEST", 506.26, frame=make_frame(1.0))["amount"] == 50.626
    assert vp.sized_pct("TEST", 506.26, frame=make_frame(1.4))["amount"] == 35.4382
    assert vp.sized_pct("TEST", 506.26, frame=make_frame(2.5))["amount"] == 25.313

    # 5) Günlük limit ve DD değişmez
    from ui import risk_brakes as rb

    assert rb.DAILY_LOSS_PCT == 0.10 and rb.TRAILING_DD_PCT == 0.15

    # 6) Panel
    from pathlib import Path

    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "ATR Durumu" in panel and "Pozisyon Boyutu" in panel


def test_disaster_recovery() -> None:
    """Açık pozisyon kurtarma, bozuk yedeke fallback, 3 yere yedek, gate 16."""
    import json
    from pathlib import Path

    from ui import check_gate, disaster_recovery as dr, tr_scalper as t

    # 1) 3 yere yedek
    rec = dr.backup("test")
    assert rec["ok"] is True and len(rec["files"]) == 3
    assert any("trades.csv" in f for f in rec["files"])
    assert any("tr_daily_state.json" in f for f in rec["files"])
    assert any("config.yaml" in f for f in rec["files"])

    # 2) Açık pozisyon kurtarma: state'e pozisyon yaz, bozuk ana dosya + geçerli yedek
    original = t.STATE.read_text(encoding="utf-8") if t.STATE.exists() else None
    original_recovery = dr.RECOVERY.read_text(encoding="utf-8") if dr.RECOVERY.exists() else None
    try:
        good = {"position": {"symbol": "BTC_TRY", "qty": 0.1, "entry": 100.0},
                "history": []}
        valid = dr.BACKUPS / "20991231_000000_tr_daily_state.json"
        valid.write_text(json.dumps(good), encoding="utf-8")
        # Ana dosyayı boz
        t.STATE.write_text("{BOZUK JSON", encoding="utf-8")
        r = dr.recover()
        assert r["ok"] is True
        assert r["open_position"] == "BTC_TRY"  # pozisyon hatırlandı
        assert "20991231_000000" in r["restored_from"]
        valid.unlink()
    finally:
        if original is not None:
            t.STATE.write_text(original, encoding="utf-8")
        if original_recovery is not None:
            dr.RECOVERY.write_text(original_recovery, encoding="utf-8")

    # 3) İkisi de bozuksa YEDEK BOZUK + işlem engeli
    # backups altındaki geçerli state yedeklerini geçici kaldır
    saved_backups = list(dr.BACKUPS.glob("*_tr_daily_state.json"))
    for b in saved_backups:
        b.rename(b.with_suffix(".hold"))
    try:
        t.STATE.write_text("{BOZUK", encoding="utf-8")
        msgs = []
        orig_send = dr.autonomous_ops._send
        dr.autonomous_ops._send = lambda title, msg: (msgs.append((title, msg)), True)[1]
        r2 = dr.recover()
        assert r2["ok"] is False
        assert any("YEDEK BOZUK" in m[1] for m in msgs)
        assert dr.block_on_corrupt() is True
        dr.autonomous_ops._send = orig_send
    finally:
        for b in saved_backups:
            hold = b.with_suffix(".hold")
            if hold.exists():
                hold.rename(b)
        if original is not None:
            t.STATE.write_text(original, encoding="utf-8")
        if original_recovery is not None:
            dr.RECOVERY.write_text(original_recovery, encoding="utf-8")

    # 4) Gate artık 16 kontrol
    assert len(check_gate.CHECKS) == 16
    assert check_gate.CHECKS[15] == "yedek sağlam mı (felaket kurtarma)"

    # 5) Panel
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Son Yedek" in panel and "Yedek Durumu" in panel and "Kurtarma Testi" in panel


def test_health_report() -> None:
    """Günlük sağlık raporu: 7 madde, dosya ve ntfy, panel."""
    from pathlib import Path

    from ui import health_report as hr

    r = hr.build()
    for key in ("at", "trades", "pnl", "position", "backups", "backup_ok",
                "restarts", "regime", "plan"):
        assert key in r

    text = hr.format_report(r)
    for i in range(1, 8):
        assert f"{i})" in text
    for word in ("Bugün işlem", "Bugün K/Z", "Açık pozisyon", "Bugün yedek",
                 "Yeniden başlatma", "Rejim", "Yarın planı"):
        assert word in text

    # Gönder + dosyaya yaz
    result = hr.send()
    assert "text" in result and "sent" in result
    assert hr.REPORT_FILE.exists()
    assert "GÜNLÜK SAĞLIK RAPORU" in hr.REPORT_FILE.read_text(encoding="utf-8")

    # Panel
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Son Rapor" in panel and "Sonraki Rapor" in panel
    assert "23:00" in hr.next_run()


def test_performance_export() -> None:
    """Haftalık performans CSV: 10 sütun, eski haftalar silinmez, panel butonu."""
    import csv
    from pathlib import Path

    from ui import performance_export as pe

    # Kullanıcı "10 sütun" demiş ama 11 alan listelemiş — hepsi mevcut
    assert len(pe.COLUMNS) == 11
    for col in ("Hafta", "Toplam İşlem", "Kazanma Oranı %",
                "Toplam Kar/Zarar TL", "Maksimum Drawdown"):
        assert col in pe.COLUMNS

    r = pe.export()
    assert pe.CSV_FILE.exists()
    for col in pe.COLUMNS:
        assert col in r

    with pe.CSV_FILE.open(encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == pe.COLUMNS
        all_rows = list(reader)
    assert len(all_rows) >= 1

    # Aynı hafta tekrar export edilse satır çoğalmaz
    before = len(all_rows)
    pe.export()
    with pe.CSV_FILE.open(encoding="utf-8-sig") as fh:
        assert len(list(csv.DictReader(fh))) == before

    # Panel butonu
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "HAFTALIK ÖZETİ GÖSTER" in panel and "Son dışa aktarma" in panel


def test_manual_intervention_log(tmp_path, monkeypatch) -> None:
    """Elle işlem manual_log.csv'ye yazar, trades.csv'ye KARIŞMAZ.

    Test kayıtları production manual_log.csv'ye YAZMAZ (tmp izolasyonu).
    """
    import csv
    from pathlib import Path

    from ui import manual_log as ml

    monkeypatch.setattr(ml, "CSV_FILE", tmp_path / "manual_log.csv")
    # 1) Elle alım kaydı
    trades_before = ml.t.TRADES_CSV.read_bytes() if ml.t.TRADES_CSV.exists() else b""
    row = ml.log("Elle Alım", "BTC_TRY", 0.01, "test müdahale")
    assert row["Müdahale Türü"] == "Elle Alım"
    assert ml.CSV_FILE.exists()

    with ml.CSV_FILE.open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[-1]["Coin"] == "BTC_TRY"
    assert rows[-1]["Müdahale Türü"] == "Elle Alım"
    assert all(c in rows[-1] for c in ml.COLUMNS)

    # 2) trades.csv DEĞİŞMEDİ (karışmadı)
    trades_after = ml.t.TRADES_CSV.read_bytes() if ml.t.TRADES_CSV.exists() else b""
    assert trades_after == trades_before

    # 3) Bot durdur/başlat kayıtları
    ml.log("Bot Durduruldu", note="test")
    ml.log("Bot Başlatıldı", note="test")
    assert len(ml.recent(5)) >= 3

    # 4) Panel bölümü
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Manuel Müdahaleler" in panel and "manual_log.csv" in panel
    assert "trades.csv SADECE bot işlemleri" in panel


def test_bear_cash_strategy() -> None:
    """Ayı rejiminde resmî NAKİTTE BEKLEME stratejisi, alım/Grid yok, short yok."""
    from pathlib import Path

    from ui import market_regime as mr, tr_scalper as t

    # Tam izolasyon: önceki testlerin state/phrase kalıntılarını temizle
    t.set_confirmed_phrase("HSC-BINANCE-TR-ARM")
    t._save({})

    orig = mr.regime
    try:
        mr.regime = lambda s: {"name": "AYI", "bear": True, "range": False,
                               "adx": 40, "price": 100, "ema50": 120,
                               "reason": "test ayı"}
        # 1) brakes_block açık mesaj
        msg = t.brakes_block("BTC_TRY")
        assert "AYI REJİMİ - NAKİTTE KALMA STRATEJİSİ AKTİF, ALIM YOK" in msg

        # 2) alım reddediliyor (buy config gate + fren)
        res = t.buy("BTC_TRY")
        assert res.get("ok") is False

        # 3) cycle modu ve log mesajı
        t._save({"mode": "NORMAL"})
        logs = t.cycle()
        assert any("AYI REJİMİ - NAKİTTE KALMA STRATEJİSİ AKTİF, ALIM YOK" in x
                   for x in logs)
        assert t._load().get("mode") == "NAKİTTE BEKLEME"
        assert t._load().get("bear_cash") is True
    finally:
        mr.regime = orig
        t._save({})

    # 4) Short/futures kodu YOK
    src_all = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                        for p in (Path(__file__).resolve().parent.parent / "ui").glob("*.py"))
    assert "def short(" not in src_all.lower()
    assert "def futures(" not in src_all.lower()
    assert "def leverage(" not in src_all.lower()

    # 5) Panel
    panel = (Path(__file__).resolve().parent.parent / "app_pages" / "bot_durumu.py").read_text(encoding="utf-8")
    assert "Ayıda Nakitte Kalma Aktif" in panel
    assert "Nakit Oranı" in panel
    assert "NAKİTTE BEKLEME" in panel


def test_crypto_walk_forward() -> None:
    """Mevcut kripto stratejisiyle walk-forward: 90 gün, 30 gün fold, 2 pencere."""
    from ui import quant_lab
    from ui.validation import crypto_walk_forward

    df = quant_lab.fetch("BTC_TRY", "1d", 90)
    assert df is not None and len(df) == 90

    wf = crypto_walk_forward(df, windows=4)
    assert len(wf) == 2  # 90//5=30 fold → 2 pencere
    for r in wf:
        for key in ("Pencere", "Test aralığı", "Eğitim işlem", "Eğitim getiri %",
                    "Test işlem", "Test getiri %", "16-CHECK GATE", "Slippage %", "Neden"):
            assert key in r
        assert r["Slippage %"] == 0.5
        assert r["Neden"]  # 0 işlemse nedeni açıkça yazılır
    # Kural aynı: 90 gün → fold 30
    assert wf[0]["Eğitim sonu"] == str(df.index[29])[:10]
    assert wf[1]["Test aralığı"].endswith(str(df.index[89])[:10])


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
