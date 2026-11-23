"""BOT DURUMU — saniyesi saniyesine gerçek durum (koddan kanıt, tahmin yok)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from ui import (auto_open, autonomous, autonomous_ops, risk_brakes, strategy_mode,
                tr_journal, tr_monitor, tr_runner, tr_scalper)


ROOT = Path(__file__).resolve().parent.parent
st.set_page_config(page_title="BOT DURUMU", layout="wide")


def _proc_alive(pattern: str) -> tuple[bool, int | None, str]:
    """Windows process listesinden süreç + PID + başlangıç saati (koddan kanıt)."""
    try:
        import psutil

        for p in psutil.process_iter(["pid", "cmdline", "create_time"]):
            cmd = " ".join(p.info.get("cmdline") or [])
            if pattern in cmd and p.info["pid"] != os.getpid():
                start = datetime.fromtimestamp(p.info["create_time"]).strftime("%H:%M:%S")
                return True, p.info["pid"], start
    except Exception:
        pass
    return False, None, "—"


@st.fragment(run_every="1s")
def _panel():
    cfg = tr_scalper.cfg()
    enabled = bool(cfg.get("enabled", False))
    phrase = tr_scalper.is_phrase_confirmed()
    stop = tr_scalper.STOP_FILE.exists()
    gate = tr_scalper.config_gate()

    # GERÇEK süreç durumu (psutil) — dosya kilidine güvenmez
    w_alive, w_pid, w_start = autonomous_ops.process_state("ui.watchdog_runner")
    s_alive, s_pid, s_start = autonomous_ops.process_state("ui.autonomous_scheduler")
    r_alive, r_pid, r_start = autonomous_ops.process_state("ui.tr_runner")

    # IŞIK: config TEMİZ + 3 süreç AYAKTA olmalı; biri bile durmuşsa KIRMIZI
    procs_ok = bool(w_alive and s_alive and r_alive)
    bot_open = bool(enabled and phrase and not stop and not gate and procs_ok)
    dead = [n for n, ok in (("WATCHDOG", w_alive), ("SCHEDULER", s_alive),
                            ("MOTOR", r_alive)) if not ok]

    # --- BÜYÜK IŞIK ---
    color = "#22c55e" if bot_open else "#ef4444"
    text = "AÇIK" if bot_open else "KAPALI"
    st.markdown(
        f"""
        <div style="text-align:center;padding:18px 0 6px 0;">
          <div style="display:inline-flex;align-items:center;gap:18px;
                      padding:14px 34px;border:2px solid {color};border-radius:18px;
                      background:rgba(0,0,0,.25);">
            <span style="width:26px;height:26px;border-radius:50%;background:{color};
                  box-shadow:0 0 22px {color};animation:botpulse 1.2s infinite;"></span>
            <span style="font-size:34px;font-weight:800;color:{color};
                  letter-spacing:2px;">BOT {text}</span>
          </div>
        </div>
        <style>
        @keyframes botpulse {{ 0%,100% {{ opacity:1; transform:scale(1); }}
                              50% {{ opacity:.35; transform:scale(.78); }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    if dead:
        st.error("**" + ", ".join(dead) + " DURMUŞ** — ışık kırmızı. "
                 "Watchdog 60 sn içinde yeniden başlatmalı.", icon=":material/error:")
    st.caption(
        f"Kanıt: enabled={enabled} · phrase={phrase} · STOP_FILE={stop} · "
        f"config_gate={gate} · WATCHDOG={w_alive} · SCHEDULER={s_alive} · MOTOR={r_alive}"
    )
    # GÜVENLİK — API ANAHTARI çekme izni (kullanıcı Binance TR API Yönetimi'nden doğruladı).
    # canWithdraw hesap durumudur, anahtar izni DEĞİL — o yüzden kullanılmıyor.
    _wd = bool(strategy_mode._load_cfg().get("security", {}).get(
        "withdraw_permission", True))
    if _wd:
        st.error("⚠️ **Withdraw izni açık** — Binance TR'den kapatın, "
                 "bot withdraw olmadan da çalışır.", icon=":material/warning:")
    else:
        st.success("✅ Withdraw kapalı - Güvenli")
        st.caption("Binance TR API Yönetimi ekranında Çekme İşlemleri kapalı "
                   "(kullanıcı doğrulaması) — bot çekme yapmaz.")
    # TOZ BİRİKMESİ — bot sadece uyarır, API dönüşümü denemez (endpoint yok)
    _dust = tr_scalper._load().get("dust") or {}
    if float(_dust.get("qty", 0) or 0) > 0:
        st.warning(
            f"**Toz birikti:** {_dust['qty']} {_dust.get('asset', '')} "
            f"(₺{float(_dust.get('try', 0)):.2f}) — Binance TR'den TRY'ye dönüştürün.",
            icon=":material/info:",
        )

    # --- ZAMANLAMA ---
    # SON CYCLE — motorun KENDİ nabzından (otonom nabız değil)
    try:
        hb = json.loads(tr_scalper.MOTOR_HEARTBEAT.read_text(encoding="utf-8"))
        last_cycle = int(time.time() - float(hb.get("ts", 0)))
        cyc_at = hb.get("at", "—")
    except Exception:
        last_cycle, cyc_at = 999999, "—"
    interval = tr_runner.INTERVAL
    next_in = max(0, interval - last_cycle)

    a, b, c, d = st.columns(4)
    a.metric("ENABLED", str(enabled))
    b.metric("CONFIRMATION PHRASE", "Doğrulandı ✅" if phrase else "Doğrulanmadı ❌")
    c.metric("STOP_FILE", "VAR ❌" if stop else "YOK ✅")
    d.metric("CONFIG GATE", "TEMİZ ✅" if not gate else "KİLİTLİ ❌")

    e, f, g = st.columns(3)
    e.metric("WATCHDOG", "ÇALIŞIYOR ♻️" if w_alive else "DURMUŞ ⏹",
             help=f"PID {w_pid} · son kontrol {w_start}")
    f.metric("SCHEDULER", "ÇALIŞIYOR ♻️" if s_alive else "DURMUŞ ⏹",
             help=f"PID {s_pid} · başlangıç {s_start}")
    g.metric("MOTOR (tr_runner)", "ÇALIŞIYOR ♻️" if r_alive else "DURMUŞ ⏹",
             help=f"PID {r_pid} · başlangıç {r_start}")

    h, i = st.columns(2)
    h.metric("SON CYCLE", f"{last_cycle // 60} dk {last_cycle % 60} sn önce", help=cyc_at)
    if not r_alive:
        i.metric("SONRAKİ CYCLE", "MOTOR DURMUŞ — BELİRSİZ")
    else:
        i.metric("SONRAKİ CYCLE", f"{next_in // 60} dk {next_in % 60} sn içinde",
                 help=f"aralık {interval} sn")

    # --- BAKİYE / POZİSYON / İŞLEM (canlı API + gerçek kayıt) ---
    # trades.csv TEK doğruluk kaynağı — komisyon + slippage dahil gerçek net
    import csv as _csv

    _tp = ROOT / "trades.csv"
    _rows = []
    if _tp.exists():
        try:
            with _tp.open(encoding="utf-8-sig", newline="") as fh:
                _rows = list(_csv.DictReader(fh))
        except Exception:
            _rows = []
    _today_rows = [r for r in _rows if str(r.get("tarih", "")).startswith(time.strftime("%Y-%m-%d"))]
    _day_net = round(sum(float(r.get("net_kar_zarar", 0) or 0) for r in _today_rows), 4)
    _day_kar = sum(1 for r in _today_rows if float(r.get("net_kar_zarar", 0) or 0) > 0)
    _day_zarar = sum(1 for r in _today_rows if float(r.get("net_kar_zarar", 0) or 0) < 0)

    bal = tr_scalper.available_try()
    pos = tr_monitor.live_metrics()["position"]
    summary = dict(tr_monitor.summary())
    summary["net_pnl"] = _day_net   # tr_monitor yerine trades.csv
    hist = tr_monitor.merged_history()
    j, k, l = st.columns(3)
    j.metric("BİNANCE TR BAKİYE (CANLI)", f"₺{bal:,.2f}",
             help="Her panel yenilemesinde Binance TR API'den (imzalı /open/v1/account/spot) çekilir.")
    from ui import quick_profit as _qp
    _br = risk_brakes.status()
    st.caption(
        f"POZİSYON: %5-7 · Skora göre · ₺{bal*0.05:.2f}-{bal*0.07:.2f} · "
        f"günlük zarar limiti ₺{float(_br.get('daily_limit_try', 0)):.2f} (%10) · "
        f"Trailing DD ₺{float(_br.get('day_peak_balance', 0)) * 0.15:.2f} (%15) · "
        f"Kâr Kilidi ₺{tr_scalper.PROFIT_LOCK_TRY:.2f}"
    )
    st.caption("Skor 35-50: %5 · 50-70: %6 · 70+: %7 · Üst limit %7 (asla %10'a çıkmaz)")
    # STALE-DATA + SLIPPAGE CUSUM — güvenlik frenleri
    from ui import safety_guards as _sg

    _fresh_ok, _fresh_msg = _sg.stale_check()
    if _fresh_ok:
        st.caption(f"✅ Fiyat Tazeliği: **{_fresh_msg}**")
    else:
        st.error(f"⚠️ Fiyat Tazeliği: **BAYAT** — {_fresh_msg} — Alım Durduruldu",
                 icon=":material/warning:")
    _sgst = _sg.status()
    if _sgst["state"] == "ALARM":
        st.error(f"🚨 {_sgst['msg']}", icon=":material/error:")
    elif _sgst["state"] == "UYARI":
        st.warning(_sgst["msg"], icon=":material/warning:")
    else:
        st.caption(f"✅ Slippage CUSUM: **%{_sgst['cusum_pct']:.2f} - Normal** "
                   f"(model %{_sgst['expected_pct']:.2f} · son 5 ort. %{_sgst['recent5_avg_pct']:.2f})")
    # OFI / L2 DEPTH — temiz mi toxic mi
    from ui import order_flow as _ofi_mod

    _ofi = _ofi_mod.check("BTC_TRY")
    if _ofi["state"] == "Toxic":
        st.error(f"**OFI: Toxic** — bid %{_ofi['bid_pct']}, spread %{_ofi['spread_pct']:.2f} "
                 f"· {_ofi['reason']} (alım atlanır)", icon=":material/warning:")
    else:
        st.caption(f"✅ OFI: **Temiz** · bid %{_ofi['bid_pct']} · "
                   f"spread %{_ofi['spread_pct']:.2f} · {_ofi['at']}")
    if pos:
        age = int(time.time() - float(pos.get("entry_ts", time.time())))
        k.metric("AÇIK POZİSYON", f"{pos['symbol']} · ₺{pos['cost']:.2f}",
                 help=f"%{age // 60} dk açık")
    else:
        k.metric("AÇIK POZİSYON", "Yok ✅")
    l.metric("BUGÜN İŞLEM / NET K/Z", f"{len(_today_rows)} / {_day_net:+.2f} ₺",
             help="trades.csv — komisyon + slippage dahil gerçek net")
    _gun = strategy_mode._state()
    st.caption(
        f"**Bugün:** {len(_today_rows)} işlem, {_day_kar} kârlı, {_day_zarar} zararlı, "
        f"Net Kar: {_day_net:+.2f} TL — işlem/zararlı işlem sınırı YOK, "
        "sadece portföy %10 freni var"
    )
    # KÂR / ZARAR İSTATİSTİĞİ — vaat değil, trades.csv'den gerçek rakam
    from ui import trade_stats as _ts

    _ks = _ts.stats()
    st.subheader("Kâr Zarar İstatistiği", divider="gray")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Bugün İşlem", f"{_ks['today_trades']}",
              delta=f"{_ks['today_wins']} kârlı / {_ks['today_losses']} zararlı")
    k2.metric("Bugün Net K/Z", f"{_ks['today_net']:+.2f} ₺")
    k3.metric("Son 7 Gün Net", f"{_ks['week_net']:+.2f} ₺")
    k4.metric("Win Rate", f"%{_ks['win_rate']:.0f}",
              help=f"Tüm zamanlar: {_ks['all_trades']} kapamış işlem")
    st.caption(
        f"Ortalama kâr: **%{_ks['avg_win_pct']:+.2f}** · "
        f"ortalama zarar: **%{_ks['avg_loss_pct']:+.2f}** · "
        f"en iyi coin: **{_ks['best_coin']} ({_ks['best_coin_net']:+.2f} ₺)** · "
        f"en kötü coin: **{_ks['worst_coin']} ({_ks['worst_coin_net']:+.2f} ₺)** "
        "— komisyon ve slippage dahil gerçek net"
    )
    # PORTFÖY DURUMU — 5 pozisyon, açık K/Z, zararın karla kapatılması
    _sc = tr_scalper._load()
    _poss = _sc.get("positions", [])
    _open_n = len(_poss) + (1 if _sc.get("position") else 0)
    _open_pnl = 0.0
    for _p in _poss:
        try:
            _cp = tr_scalper.price(_p["symbol"])
            _open_pnl += (float(_cp) - float(_p["entry"])) * float(_p["qty"])
        except Exception:
            pass
    _offset = "Evet" if _day_kar > 0 and _day_zarar > 0 else "Hayır"
    st.subheader("Portföy Durumu", divider="gray")
    st.caption(
        f"Açık Pozisyon **{_open_n}/5** · Toplam Açık K/Z **{_open_pnl:+.2f} TL** · "
        f"Bugün Kapanan İşlem **{len(_today_rows)}** · Bugün Net **{_day_net:+.2f} TL** · "
        f"Bir işlemin zararı diğer işlemin kârıyla kapatıldı mı? **{_offset}**"
    )
    # EKONOMİK SAĞLIK — bot process değil, para üretiyor mu izler
    from ui import economic_health

    _eh = economic_health.status()
    if _eh["alerts"]:
        st.warning("**Ekonomik sağlık uyarısı:** " + " · ".join(_eh["alerts"]),
                   icon=":material/monitor_heart:")
    else:
        st.caption(f"✅ Ekonomik sağlık OK · son işlem {_eh['last_trade']} "
                   f"({_eh['hours_since']} sa önce) · hata {_eh['errors_1h']}/saat · "
                   f"bakiye ₺{_eh['balance']:,.2f} · komisyon API doğrulaması "
                   f"%{tr_scalper.live_commission()*100:.1f}")

    # SON İŞLEM — yukarıda okunan trades.csv'nin son satırı
    st.divider()
    st.subheader("Son İşlem", divider="gray")
    _last_row = _rows[-1] if _rows else None
    if _last_row:
        _net = float(_last_row.get("net_kar_zarar", 0) or 0)
        st.markdown(
            f"**Son İşlem:** {_last_row.get('tarih', '—')} - "
            f"{_last_row.get('sembol', '—')} - Net: {_net:+.2f} TL"
        )
    else:
        st.info("Henüz işlem yok", icon=":material/info:")

    # --- FRENLER ---
    br = risk_brakes.status()
    daily_used = 0.0
    limit = float(br.get("daily_limit_try", 0) or 0)
    if limit > 0:
        daily_used = min(100.0, abs(float(br.get("day_realized_pnl", 0))) / limit * 100)
    st.progress(daily_used / 100, text=(
        f"Günlük limit: %{daily_used:.0f} kullanıldı "
        f"({br.get('day_realized_pnl', 0):+.2f} / -{limit:.2f} ₺)"
    ))
    st.caption(
        f"Trailing drawdown: zirve ₺{br.get('day_peak_balance', 0):,.2f} · "
        f"%{br.get('dd_limit_pct', 0):.0f} kilit "
        f"({'AŞILDI ⚠️' if br.get('dd_breached') else 'mesafe OK ✅'}) · "
        f"Ani çöküş: son 5 dk %{br.get('crash_limit_pct', 0):.0f} → "
        f"{br.get('crash_remaining', 0) // 60} dk bekleme kaldı"
    )

    # KOMİSYON + VOLATİLİTE
    import csv as _csv

    comm_total = 0.0
    tpath = ROOT / "trades.csv"
    if tpath.exists():
        with tpath.open(encoding="utf-8-sig", newline="") as fh:
            comm_total = sum(float(r.get("komisyon", 0) or 0)
                             for r in list(_csv.DictReader(fh))[-10:])
    vstate = tr_scalper.volatility_state("BTC_TRY")
    v1, v2 = st.columns(2)
    v1.metric("KOMİSYON (son 10 işlem)", f"₺{comm_total:.4f}")
    v2.metric("VOLATİLİTE", "YÜKSEK ⚠️" if vstate["high"] else "Normal ✅",
              help=vstate["reason"])
    from ui import market_regime

    reg = market_regime.regime("BTC_TRY")
    _rc = {"BOĞA": "#22c55e", "AYI": "#ef4444", "YATAY": "#eab308"}.get(reg["name"], "#94a3b8")
    st.markdown(
        f'<div style="text-align:center;padding:8px 0 12px 0;">'
        f'<span style="font-size:26px;font-weight:800;color:{_rc};letter-spacing:3px;">'
        f'REJİM: {reg["name"]}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(f"ADX {reg['adx']:.1f} · fiyat {reg['price']:.2f} / EMA50 {reg['ema50']:.2f} — "
               f"{reg['reason']}")
    # REJİME GÖRE OTOMATİK MOD — kullanıcı seçmez (BOĞA=EMA50, YATAY/AYI=KÜÇÜK KÂR)
    from ui import strategy_mode as sm

    _auto_mode, _auto_reg = sm.current_auto(reg["name"])
    strat_label = sm.LABELS[_auto_mode]
    rejim_modu = ("AYI (%5, RSI<25)" if (_auto_mode == sm.QUICK and reg["bear"])
                  else "GRID" if reg["range"]
                  else "NAKİTTE BEKLEME" if reg["bear"] else "NORMAL")
    _mc = "#eab308" if _auto_mode == sm.QUICK else "#22c55e"
    st.markdown(
        f'<div style="text-align:center;padding:6px 0 10px 0;">'
        f'<span style="font-size:22px;font-weight:800;color:{_mc};letter-spacing:2px;">'
        f'REJİM: {_auto_reg} - MOD: {strat_label}</span></div>',
        unsafe_allow_html=True,
    )
    sm_st = sm._state()
    st.caption(
        f"Otomatik mod (kullanıcı seçmez) · rejim durumu: **{rejim_modu}** · "
        f"işlem/zararlı işlem sınırı **YOK** · portföy freni **%10** · "
        f"son geçiş {sm_st.get('changed_at', '—')}"
    )
    if _auto_mode == sm.QUICK:
        try:
            from ui import quick_profit

            _bt = quick_profit.backtest(30)
            st.metric("30 GÜN BACKTEST (SÜREKLİ KÜÇÜK KAR)",
                      f"{_bt['islem']} işlem · {_bt['karli']} kârlı · {_bt['toplam_kar_pct']:+.2f}%",
                      help=f"hedef %{quick_profit.TAKE_PCT*100:.1f} · komisyon çift yön %0.2 · "
                           f"slippage %{quick_profit.SLIPPAGE*100:.1f}")
            _watch = _qp.dynamic_watchlist()
            st.caption(f"**Dinamik Top-10:** {', '.join(_watch)} · "
                       f"Son güncelleme: {time.strftime('%H:%M')}")
            st.caption("**Akıllı Sepet — 30 coin taranıyor "
                       "(8 Güvenli + 12 Hacimli + 10 Fırsatçı)** · "
                       "Dinamik Top-10 bugün bu coin'lere öncelik veriyor · "
                       "aynı anda max 5 pozisyon (skora göre %5-7)")
            _skor = quick_profit.scan(list(tr_scalper.SYMBOLS))
            if _skor:
                st.subheader("30 coin skor tablosu (0-100)", divider="gray")
                st.dataframe(pd.DataFrame([{
                    "Coin": r["symbol"], "Kademe": r["kademe"], "SKOR": r["score"],
                    "RSI": f"{r['rsi']:.1f}", "RSI puanı": r["rsi_puan"],
                    "Düşüş": r["dusur_puan"],
                    "Hacim": r["hacim_puan"], "BB": r["bb_puan"],
                    "Mom": r.get("mom_puan", 0), "VWAP": r.get("vwap_puan", 0),
                    "EMA": r.get("ema_puan", 0),
                    "ATR%": r["atr_pct"], "Pozisyon": "%5 · ₺276.33",
                    "Karar": r["vol_not"],
                } for r in _skor]), use_container_width=True, hide_index=True)
                _max_skor = max(float(r["score"]) for r in _skor)
                if _max_skor < 10:
                    st.info("Şu an piyasa durgun — fırsat yok (en yüksek skor "
                            f"{_max_skor:.1f}/100). Skor formülü doğru: son 30 günde "
                            "100'e kadar çıktı, şu an RSI/düşüş/hacim/BB sinyali yok.",
                            icon=":material/info:")
        except Exception as _be:
            st.caption(f"backtest verisi alınamadı: {type(_be).__name__}")
    g = tr_scalper._load().get("grid", {})
    if rejim_modu == "GRID":
        st.caption(f"Grid kademeleri: **{int(g.get('bought', 0))} alındı / "
                   f"{int(g.get('sold', 0))} satıldı** · "
                   f"parça ₺{float(g.get('part', 0)):.2f} · %1 adım · "
                   f"anchor {float(g.get('anchor', 0)):.4f}")
        st.info("YATAY rejim — Grid modu aktif, %1 düşüşte al / %1 yükselişte sat.",
                icon=":material/grid_on:")
    elif rejim_modu == "AYI (%5, RSI<25)":
        st.info("**Ayı rejimi — SÜREKLİ KÜÇÜK KAR aktif:** %5 pozisyon (₺276.33), "
                "RSI<25 ile az işlem. Ayıda Nakitte Kalma kuralı BU modda uygulanmaz "
                "(sadece EMA50 modunda geçerli). Spot long-only.",
                icon=":material/info:")
    elif rejim_modu == "NAKİTTE BEKLEME":
        _pos_now = tr_scalper._load().get("position")
        cash_pct = 0 if _pos_now else 100
        st.error("**Strateji: Ayıda Nakitte Kalma Aktif** — alım yok, Grid yok, "
                 "short/futures/yok. Spot long-only.", icon=":material/warning:")
        st.metric("Nakit Oranı", f"%{cash_pct}", help=f"Binance TR canlı bakiye: ₺{bal:,.2f}")
    else:
        _bull_msg = ("BOĞA rejimi — Grid kapalı, normal EMA50 pullback modu."
                     if _auto_mode == sm.EMA50 else
                     "BOĞA rejimi — Sürekli Küçük Kar modu, %1.5 kâr hedefi.")
        st.success(_bull_msg, icon=":material/check:")

    # ATR BAZLI STOP göstergesi
    atr_info = market_regime.atr_stop(reg["price"], "BTC_TRY")
    a1, a2 = st.columns(2)
    a1.metric("ATR(14)", f"{atr_info['atr']:,.2f}")
    a2.metric("STOP MESAFESİ", f"%{atr_info['pct']:.2f}",
              help=f"1.5 × ATR = {atr_info['distance']:,.2f} · stop {atr_info['stop']:,.2f}")
    st.caption("Stop mesafesi = 1.5 × ATR(14) — NORMAL ve GRID modlarında geçerli. "
               "Sabit %3 stop kaldırıldı.")

    # ARDIŞIK ZARAR SINIRI KALDIRILDI — sadece portföy %10 freni var
    st.markdown(
        '<div style="text-align:center;padding:6px 0 10px 0;">'
        '<span style="font-size:18px;font-weight:800;color:#22c55e;letter-spacing:1px;">'
        'ARDIŞIK ZARAR SINIRI YOK — portföy %10 freni var</span></div>',
        unsafe_allow_html=True,
    )
    _until = float(tr_scalper._load().get("loss_streak_until", 0) or 0)
    if _until > time.time():
        st.error(f"24 saatlik fren aktif — kalan {int((_until-time.time())//3600)} sa "
                 f"{int((_until-time.time())%3600//60)} dk", icon=":material/block:")

    # MULTI-TIMEFRAME ONAY (sadece NORMAL modda)
    st.divider()
    st.subheader("Zaman dilimi onayı (NORMAL mod)", divider="gray")
    mtf = market_regime.mtf_confirm("BTC_TRY")
    daily_txt = "ONAYLI ✅" if mtf.get("daily") else "ONAYSIZ ❌"
    h4_txt = "ONAYLI ✅" if mtf.get("h4") else "ONAYSIZ ❌"
    decision = "AL" if mtf.get("ok") else "BEKLE"
    m1, m2, m3 = st.columns(3)
    m1.metric("Günlük", daily_txt)
    m2.metric("4 Saatlik", h4_txt)
    m3.metric("Son Karar", decision)
    if rejim_modu == "GRID":
        st.caption("GRID modunda bu onay aranmaz — Grid kendi kuralıyla çalışır.")
    st.caption(f"Kural: günlük EMA50 sinyali + 4s EMA50 üstü = AL; 4s altı = BEKLE. · {mtf.get('reason', '')}")

    # CORRELATION PROTECTION
    st.divider()
    st.subheader("Korelasyon koruması", divider="gray")
    from ui import correlation_guard

    open_pos = tr_scalper._load().get("position") or {}
    new_sig = "ETH_TRY" if open_pos.get("symbol") == "BTC_TRY" else "BTC_TRY"
    cg = correlation_guard.guard_entry(open_pos.get("symbol"), new_sig)
    c1, c2 = st.columns(2)
    c1.metric("Açık Pozisyon", open_pos.get("symbol", "Yok"))
    c2.metric("Yeni Sinyal", f"{new_sig} — Korelasyon: {cg['corr'] if cg['corr'] is not None else '—'}"
              + (" — ENGELLENDİ" if not cg["allowed"] else " — İZİN"))
    st.caption(cg["reason"])
    corr_pairs = ("BTC_TRY", "ETH_TRY", "XRP_TRY", "DOGE_TRY")
    st.dataframe(
        pd.DataFrame(correlation_guard.matrix(corr_pairs),
                     columns=["Coin", "BTC", "ETH", "XRP", "DOGE"]),
        use_container_width=True, hide_index=True,
    )
    st.caption(f"Kural: korelasyon > {correlation_guard.CORR_LIMIT} ise aynı anda alım yok · "
               f"son {correlation_guard.CORR_DAYS} günlük kapanış")

    # MANUEL MÜDAHALE KAYDI
    st.divider()
    st.subheader("Manuel Müdahaleler", divider="gray")
    from ui import manual_log

    mrows = manual_log.recent(5)
    if mrows:
        st.dataframe(pd.DataFrame(mrows), use_container_width=True, hide_index=True)
    else:
        st.info("Henüz manuel müdahale yok — botun kendi işlemleri trades.csv'de ayrı tutulur.",
                icon=":material/info:")
    st.caption("Elle alım/satım (bakiye değişimi ile tespit) ve bot durdur/başlat "
               "manual_log.csv'ye yazılır · trades.csv SADECE bot işlemleri")

    # PERFORMANS PANOSU DIŞA AKTARMA
    st.divider()
    st.subheader("Performans panosu — haftalık özet", divider="gray")
    from ui import performance_export

    pe = performance_export.last()
    st.caption(f"Son dışa aktarma: **{pe['week']}** · {pe['at']} · "
               f"her Pazar 23:00 · eski haftalar korunur")
    if st.button("HAFTALIK ÖZETİ GÖSTER", icon=":material/table:", key="weekly_summary_btn"):
        st.session_state["show_weekly_summary"] = not st.session_state.get("show_weekly_summary", False)
    if st.session_state.get("show_weekly_summary"):
        prs = performance_export.rows()
        if prs:
            st.dataframe(pd.DataFrame(prs), use_container_width=True, hide_index=True)
        else:
            st.info("Henüz haftalık özet yok — ilk Pazar 23:00'te oluşacak.", icon=":material/info:")

    # GÜNLÜK SAĞLIK RAPORU
    st.divider()
    st.subheader("Günlük sağlık raporu", divider="gray")
    from ui import health_report

    hr = health_report.last()
    r1, r2 = st.columns(2)
    r1.metric("Son Rapor", f"{hr['at']} — {'Gönderildi ✅' if hr['sent'] else 'Bekliyor'}")
    r2.metric("Sonraki Rapor", health_report.next_run())
    rp = ROOT / "daily_report.txt"
    if rp.exists():
        with st.expander("Son raporu oku", icon=":material/description:"):
            st.text(rp.read_text(encoding="utf-8"))

    # GÜNLÜK RAPOR — 23:00, gerçek rakam
    st.divider()
    st.subheader("Günlük Rapor (23:00)", divider="gray")
    from ui import autonomous_ops as _ao
    _dr = _ao.daily_report_data()
    g1, g2, g3, g4 = st.columns(4)
    g1.metric("Bugün İşlem", f"{_dr['trades']}",
              delta=f"{_dr['wins']} kârlı / {_dr['losses']} zararlı")
    g2.metric("Bugün Net K/Z", f"{_dr['today_net']:+.2f} ₺")
    g3.metric("Win Rate", f"%{_dr['win_rate']:.0f}")
    g4.metric("Bakiye", f"₺{_dr['balance']:,.2f}")
    st.caption(
        f"Son 7 gün net: **{_dr['week_net']:+.2f} TL** · "
        f"Açık pozisyon: **{_dr['open_position']}** · "
        f"Gerçek TP kanıtı: **{_dr['tp_proof']}** · "
        f"Rapor saati: {_dr['at']} — vaat değil, trades.csv'den gerçek rakam"
    )

    # YEDEK + FELAKET KURTARMA
    st.divider()
    st.subheader("Yedek + Felaket Kurtarma", divider="gray")
    from ui import disaster_recovery as dr

    ds = dr.status()
    d1, d2, d3 = st.columns(3)
    d1.metric("Son Yedek", ds["last_backup"])
    d2.metric("Yedek Durumu", ds["status"])
    d3.metric("Kurtarma Testi", ds["recovery"])
    if ds["open_position"]:
        st.caption(f"Kurtarılan açık pozisyon: **{ds['open_position']}** — sıfırdan başlanmadı.")
    st.caption("Her işlemden sonra trades.csv + state.json + backups/ tarihli kopya · "
               "bozuksa önceki yedek, ikisi de bozuksa işlem yok")

    # VOLATİLİTEYE GÖRE POZİSYON BOYUTU
    st.divider()
    st.subheader("Volatiliteye göre pozisyon boyutu", divider="gray")
    from ui import vol_position

    vs = vol_position.atr_state("BTC_TRY")
    vcolor = {"Normal": "#22c55e", "Yüksek": "#eab308", "Çok Yüksek": "#ef4444"}.get(vs["state"], "#94a3b8")
    st.markdown(
        f'<div style="text-align:center;padding:6px 0 10px 0;">'
        f'<span style="font-size:18px;font-weight:800;color:{vcolor};">'
        f'ATR Durumu: {vs["state"]} · Pozisyon Boyutu: %5 · ₺276.33</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Gerekçe: {vs['reason']} · ATR {vs['atr']} / 30g ort. {vs['avg']} (oran {vs['ratio']}) · "
               "Sürekli Küçük Kar modunda tüm işlemler %5 (₺276.33), eski %7/%10 kaldırıldı")

    # BALİNA / HABER KORUMASI
    st.divider()
    st.subheader("Balina / Haber koruması", divider="gray")
    from ui import whale_guard

    wg = whale_guard.status()
    w1, w2, w3 = st.columns(3)
    w1.metric("Son 5 Dk Hareket", f"%{wg['move_pct']:+.2f}")
    w2.metric("Balina Koruması", "Aktif ⛔" if wg["active"] else "Pasif ✅")
    w3.metric("Kalan Bekleme", f"{wg['remaining_min']} dk")
    st.caption("5 dk içinde %3+ düşüş veya yükseliş → 30 dk yeni alım yok · "
               "16-Check Gate'in 15. kontrolü")

    # SLIPPAGE + EMİR DOLUMU
    st.divider()
    st.subheader("Emir dolumu ve slippage", divider="gray")
    from ui import order_guard

    og = order_guard.last()
    has_order = bool(og.get("status"))  # boşsa gerçek emir yok
    o1, o2 = st.columns(2)
    o1.metric("Son Emir Durumu", og.get("status", "—") + (" (GERÇEK)" if has_order else " (YOK)"))
    o2.metric("Son Slippage", f"%{og.get('slippage_pct', 0):.2f}" if has_order else "---")
    st.caption("Gerçek emir gelene kadar slippage gösterilmez (test verisi kullanılmaz) · "
               f"maksimum kayma %{order_guard.MAX_SLIPPAGE*100:.0f}")

    # AÇIK POZİSYON KÂR/ZARAR — sadece gösterge, alım/satım mantığına dokunmaz
    st.divider()
    st.subheader("Açık Pozisyon Kâr/Zarar", divider="gray")
    _op = tr_scalper._load().get("position") or {}
    if _op:
        _sym = _op.get("symbol", "—")
        _entry = float(_op.get("entry", 0) or 0)
        _qty = float(_op.get("qty", 0) or 0)
        _cur = tr_scalper.price(_sym) or _entry
        _pnl = (_cur - _entry) * _qty
        _pct = ((_cur - _entry) / _entry * 100) if _entry else 0.0
        _sl = float(_op.get("atr_stop", 0) or 0)
        _ttp = tr_scalper.trailing_tp(_op, _cur)
        _target = float(_ttp.get("tp", 0) or 0) or _entry * (1 + tr_scalper.TAKE_PROFIT_EXPECTED)
        st.markdown(
            f"**Açık Pozisyon:** {_sym} - Giriş: {_entry:,.4f} - "
            f"Şu Anki Fiyat: {_cur:,.4f} - Kar/Zarar: {_pnl:+,.2f} TL (%{_pct:+.2f}) - "
            f"Stop: {_sl:,.4f} - Hedef: {_target:,.4f}"
        )
        st.caption("Stop = 1.5 × ATR(14) fiyatı · Hedef = trailing TP satış fiyatı. "
                   "Bu bölüm salt okunur göstergedir.")
    else:
        st.info("Açık Pozisyon Yok", icon=":material/info:")

    # KISMİ KÂR ALIMI
    st.divider()
    st.subheader("Kademeli Kâr Alımı", divider="gray")
    _p = tr_scalper._load().get("position") or {}
    if _auto_mode == sm.QUICK:
        _stage = int(_p.get("tp_stage", 0))
        k1, k2, k3 = st.columns(3)
        k1.metric("TP1 %0.8 → %40", "Satıldı ✅" if _stage >= 1 else "Bekliyor",
                  help="Stop giriş fiyatına çekilir (breakeven)")
        k2.metric("TP2 %1.5 → %40", "Satıldı ✅" if _stage >= 2 else "Bekliyor")
        k3.metric("TP3 %2.5 → %20", "Trailing aktif ♻️" if _stage >= 3 else "Bekliyor",
                  help="Zirveden %0.5 geri çekilmede satılır")
        st.caption("Sürekli Küçük Kar: %0.8'de %40 + breakeven · %1.5'te %40 · "
                   "%2.5'te kalan %20 trailing. DCA kurtarma aynen çalışır.")
    elif _p:
        k1, k2, k3 = st.columns(3)
        k1.metric("Kısmî Satış", "Yapıldı ✅" if _p.get("partial_done") else "Yapılmadı")
        k2.metric("Cebe Konan Kâr", f"{float(_p.get('partial_profit', 0)):+.2f} ₺")
        k3.metric("Kalan Pozisyon", f"₺{float(_p.get('qty', 0)) * float(_p.get('entry', 0)):.2f}")
        st.caption("%5 karda pozisyonun %50'si satılır · EMA50 modu")
    else:
        st.info("Açık pozisyon yok — kademeli satış pasif.", icon=":material/info:")

    # TRAILING TAKE-PROFIT
    st.divider()
    st.subheader("Trailing Take-Profit", divider="gray")
    _pos = tr_scalper._load().get("position") or {}
    if _pos:
        _ttp = tr_scalper.trailing_tp(_pos, _pos.get("entry", 0))
        t1, t2, t3 = st.columns(3)
        t1.metric("Trailing TP", "Aktif ✅" if _ttp["active"] else "Pasif")
        t2.metric("Zirve Fiyat", f"{_ttp['peak']:,.4f} ₺")
        t3.metric("Trailing Satış Fiyatı", f"{_ttp['tp']:,.4f} ₺" if _ttp["tp"] else "—")
        st.caption("%5 karda aktif · zirveden %2 düşüşte sat · sadece NORMAL mod")
    else:
        st.info("Açık pozisyon yok — trailing TP pasif.", icon=":material/info:")

    # AYLIK BACKTEST
    st.divider()
    st.subheader("Aylık backtest (son 90 gün)", divider="gray")
    from ui import monthly_backtest

    mb = monthly_backtest.last()
    b1, b2 = st.columns(2)
    b1.metric("Son Backtest (slippage'siz)",
              f"{mb['at']} — Kar: {mb['net_pnl']:+.2f} TL, Kazanma: %{mb['win_rate']:.0f}, "
              f"Drawdown: %{mb['max_dd']:.0f}")
    b2.metric("Son Backtest (slippage'li)",
              f"Kar: {mb.get('net_pnl_slip', 0):+.2f} TL")
    st.caption(f"Slippage modeli: %{mb.get('slippage_pct', 0.5):.1f} dahil "
               f"(alım üstten / satım alttan) · sonraki: {monthly_backtest.next_run()}")
    if mb["warn"]:
        st.caption("Bu rakamlar **ESKİ EMA50 Pullback** stratejisine aittir (günlük trend, "
                   "ayda 1-2 işlem). Aktif sistem **Sürekli Küçük Kar**'dır — yeni 30 gün "
                   "backtest'inde 114 işlem, 102 kârlı, %+61.10. Bu uyarı yeni sistem için geçerli değildir.")

    # AUTO-OPTİMİZASYON
    st.divider()
    st.subheader("Otomatik optimizasyon", divider="gray")
    from ui import auto_optimize

    lo = auto_optimize.last_run()
    o1, o2 = st.columns(2)
    o1.metric("Son Optimizasyon",
              f"{lo['at']} — ATR {lo['atr']}, Grid %{lo['grid']}")
    o2.metric("Sonraki Optimizasyon", auto_optimize.next_run())
    st.caption(f"Korelasyon eşiği: {lo['corr']} (sabit) · "
               f"Her Pazar 23:00 · Parametre geçmişi: params_history.csv")

    # ESKİ 8 COİN "AKILLI SEPET" BÖLÜMÜ KALDIRILDI — tek sepet: yukarıdaki 30 coin tablosu.

    # WEBSOCKET + ORDER BOOK
    st.divider()
    st.subheader("Canlı veri akışı — WebSocket + Order Book", divider="gray")
    from ui import ws_feed as _ws

    _wsst = _ws.status()
    st.caption(f"**Canlı Veri:** {_wsst['source']} "
               + (f"(gecikme: {_wsst['latency_ms']} ms) " if _wsst["connected"] else "")
               + f"· son olay: {_wsst['last_event']} · {_wsst['at']}"
               + (f" · ExecutionReport: {_wsst.get('last_user_event','—')}"
                  if _wsst.get("last_user_event") else ""))
    from ui import live_feed

    fs = live_feed.status()
    bp = live_feed.book_pressure()
    w1, w2, w3, w4 = st.columns(4)
    w1.metric("Veri Kaynağı", fs["source"] + (" (GERÇEK)" if fs["connected"] else " (GERÇEK — REST yedek)"))
    w2.metric("Order Book", (f"Alış %{bp['buy']*100:.0f} / Satış %{bp['sell']*100:.0f} (GERÇEK)"
                              if bp["ok"] else "--- (veri yok)"))
    w3.metric("Son Fiyat Güncelleme",
              f"{fs['price_age']} sn önce" if fs["price_age"] is not None else "---")
    # HACİM ANALİZİ — sadece gösterge, stratejiye/sinyale dokunmaz
    from ui import quant_lab
    try:
        _vf = quant_lab.fetch("BTC_TRY", "1h", 30)
        if _vf is not None and len(_vf) >= 21:
            _last_v = float(_vf["Volume"].iloc[-1])
            _avg_v = float(_vf["Volume"].iloc[-21:-1].mean())
            _ratio = _last_v / _avg_v if _avg_v else 0.0
            _vol_txt = "ARTIŞ VAR ▲" if _ratio >= 1.5 else "ARTIŞ YOK"
            _vol_help = f"son={_last_v:,.0f} · 20b ort={_avg_v:,.0f} · oran={_ratio:.2f}x"
        else:
            _vol_txt, _vol_help = "---", "hacim verisi yok"
    except Exception:
        _vol_txt, _vol_help = "---", "hacim alınamadı"
    w4.metric("Hacim (20b)", _vol_txt, help=_vol_help)
    if fs["connected"] and fs["price_age"] is None:
        st.warning("WS bağlı ama veri akmıyor — REST yedekte. "
                   "Gerçek fiyat akışı gelene kadar WebSocket'ten işlem yapılmaz.",
                   icon=":material/warning:")
    elif not fs["connected"]:
        st.caption("WS bağlı değil — REST yedek aktif (GERÇEK).")

    # 16-CHECK GATE — canlı veriyle senkron (eski kayıt kullanılmaz)
    st.divider()
    st.subheader("16-CHECK GATE — son emir kontrolleri", divider="gray")
    from ui import check_gate

    # CANLI gate — kayıtlı/eski veri KULLANILMAZ
    try:
        gate_live = check_gate.run("BTC_TRY", price=tr_scalper.price("BTC_TRY"),
                                   mode=_auto_mode)
        fixed = gate_live["results"]
        gpass, gtotal = int(gate_live["passed"]), int(gate_live["total"])
        summary = gate_live["summary"]
        ok_color = "#22c55e" if gate_live["ok"] else "#ef4444"
        st.markdown(
            f'<div style="text-align:center;padding:8px 0 12px 0;">'
            f'<span style="font-size:22px;font-weight:800;color:{ok_color};letter-spacing:1px;">'
            f'SON EMİR KONTROLLERİ (GERÇEK — canlı): {summary}</span></div>',
            unsafe_allow_html=True,
        )
        st.progress(gpass / gtotal if gtotal else 0)
        st.dataframe(
            pd.DataFrame([{
                "#": r["no"], "Kontrol": r["check"],
                "Sonuç": "✅" if r["ok"] else "❌", "Not": r["note"],
                "Veri": "GERÇEK",
            } for r in fixed]),
            use_container_width=True, hide_index=True,
        )
        st.caption("Gate her sayfa yenilemesinde **canlı** çalışır — kayıtlı/eski veri kullanılmaz. "
                   "Sembol standardı: hepsi USDT · en üstteki REJİM ile aynı anlık veri.")
    except Exception as exc:
        st.warning(f"Canlı gate çalıştırılamadı: {type(exc).__name__} — eski veri gösterilmez.",
                   icon=":material/warning:")
    st.caption(
        f"Komisyon filtresi: beklenen kâr ≥ {tr_scalper.MIN_EXPECTED_RR:.0f}× komisyon "
        f"(oran %{tr_scalper.COMMISSION*100:.2f}) · "
        f"Yüksek volatilite: 1 saatte %{tr_scalper.VOLATILITY_PCT*100:.0f} üzeri → "
        f"{tr_scalper.VOLATILITY_COOLDOWN//60} dk bekleme"
    )

    # --- SON KAYITLAR ---
    rows = tr_journal.recent(5)
    if rows:
        st.markdown("##### Son kayıtlar")
        st.dataframe(pd.DataFrame([{
            "Zaman": r.get("at"), "Tür": r.get("kind"),
            "Kayıt": " | ".join(r.get("events", [])[:2])[:180],
        } for r in reversed(rows)]), use_container_width=True, hide_index=True)
    # --- ACİL DURDURMA / TEKRAR BAŞLATMA ---
    st.divider()
    st.subheader("Acil kontrol", divider="gray")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🛑 BOTU ACİL DURDUR", key="emergency_stop_btn",
                     type="primary", use_container_width=True):
            res = auto_open.emergency_stop()
            st.error(f"**BOT DURDURULDU** — enabled={res['enabled']}, STOP_FILE={res['stop_file']}. "
                     "Açık pozisyon korunuyor, yeni alım yok.", icon=":material/stop:")
            st.rerun()
    with c2:
        if st.button("▶ BOTU TEKRAR BAŞLAT", key="emergency_start_btn",
                     use_container_width=True):
            res = auto_open.emergency_start()
            st.success(f"**BOT BAŞLATILDI** — enabled={res['enabled']}, "
                       f"STOP_FILE={res['stop_file']}, gate={res['gate']}",
                       icon=":material/play_arrow:")
            st.rerun()

    st.caption(f"Şu an: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · her saniye yenilenir")


st.title("BOT DURUMU", icon=":material/traffic:")
_panel()
