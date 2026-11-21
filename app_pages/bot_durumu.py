"""BOT DURUMU — saniyesi saniyesine gerçek durum (koddan kanıt, tahmin yok)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from ui import (auto_open, autonomous, autonomous_ops, risk_brakes, tr_journal,
                tr_monitor, tr_runner, tr_scalper)


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
    bal = tr_scalper.available_try()
    pos = tr_monitor.live_metrics()["position"]
    summary = tr_monitor.summary()
    hist = tr_monitor.merged_history()
    j, k, l = st.columns(3)
    j.metric("BİNANCE TR BAKİYE (canlı)", f"₺{bal:,.2f}")
    if pos:
        age = int(time.time() - float(pos.get("entry_ts", time.time())))
        k.metric("AÇIK POZİSYON", f"{pos['symbol']} · ₺{pos['cost']:.2f}",
                 help=f"%{age // 60} dk açık")
    else:
        k.metric("AÇIK POZİSYON", "Yok ✅")
    l.metric("BUGÜN İŞLEM / NET K/Z",
             f"{len([x for x in hist if str(x.get('exit_time', '')).startswith(time.strftime('%Y-%m-%d'))])} / "
             f"{summary['net_pnl']:+.2f} ₺")

    if hist:
        last = hist[-1]
        st.caption(
            f"**Son işlem:** {last.get('exit_time', '—')} · {last.get('symbol', '—')} · "
            f"net **{last.get('net_pnl', last.get('pnl', 0)):+.2f} ₺**"
        )

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
    vstate = tr_scalper.volatility_state("BTCUSDT")
    v1, v2 = st.columns(2)
    v1.metric("KOMİSYON (son 10 işlem)", f"₺{comm_total:.4f}")
    v2.metric("VOLATİLİTE", "YÜKSEK ⚠️" if vstate["high"] else "Normal ✅",
              help=vstate["reason"])
    from ui import market_regime

    reg = market_regime.regime("BTCUSDT")
    _rc = {"BOĞA": "#22c55e", "AYI": "#ef4444", "YATAY": "#eab308"}.get(reg["name"], "#94a3b8")
    st.markdown(
        f'<div style="text-align:center;padding:8px 0 12px 0;">'
        f'<span style="font-size:26px;font-weight:800;color:{_rc};letter-spacing:3px;">'
        f'REJİM: {reg["name"]}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(f"ADX {reg['adx']:.1f} · fiyat {reg['price']:.2f} / EMA50 {reg['ema50']:.2f} — "
               f"{reg['reason']}")
    mode = tr_scalper._load().get("mode", "NAKİTTE BEKLEME")
    if reg["range"]:
        mode = "GRID"
    elif reg["bear"]:
        mode = "NAKİTTE BEKLEME"
    else:
        mode = "NORMAL"
    _mc = {"GRID": "#eab308", "NORMAL": "#22c55e",
           "NAKİTTE BEKLEME": "#ef4444"}[mode]
    st.markdown(
        f'<div style="text-align:center;padding:6px 0 10px 0;">'
        f'<span style="font-size:22px;font-weight:800;color:{_mc};letter-spacing:2px;">'
        f'MOD: {mode}</span></div>',
        unsafe_allow_html=True,
    )
    g = tr_scalper._load().get("grid", {})
    if mode == "GRID":
        st.caption(f"Grid kademeleri: **{int(g.get('bought', 0))} alındı / "
                   f"{int(g.get('sold', 0))} satıldı** · "
                   f"parça ₺{float(g.get('part', 0)):.2f} · %1 adım · "
                   f"anchor {float(g.get('anchor', 0)):.4f}")
        st.info("YATAY rejim — Grid modu aktif, %1 düşüşte al / %1 yükselişte sat.",
                icon=":material/grid_on:")
    elif mode == "NAKİTTE BEKLEME":
        _pos_now = tr_scalper._load().get("position")
        cash_pct = 0 if _pos_now else 100
        st.error("**Strateji: Ayıda Nakitte Kalma Aktif** — alım yok, Grid yok, "
                 "short/futures/yok. Spot long-only.", icon=":material/warning:")
        st.metric("Nakit Oranı", f"%{cash_pct}")
    else:
        st.success("BOĞA rejimi — Grid kapalı, normal EMA50 pullback modu.",
                   icon=":material/check:")

    # ATR BAZLI STOP göstergesi
    atr_info = market_regime.atr_stop(reg["price"], "BTCUSDT")
    a1, a2 = st.columns(2)
    a1.metric("ATR(14)", f"{atr_info['atr']:,.2f}")
    a2.metric("STOP MESAFESİ", f"%{atr_info['pct']:.2f}",
              help=f"1.5 × ATR = {atr_info['distance']:,.2f} · stop {atr_info['stop']:,.2f}")
    st.caption("Stop mesafesi = 1.5 × ATR(14) — NORMAL ve GRID modlarında geçerli. "
               "Sabit %3 stop kaldırıldı.")

    # ARDIŞIK ZARAR FRENİ göstergesi
    from ui import market_regime as _mr

    ls = _mr.loss_streak_count(tr_scalper._load())
    _lc = "#ef4444" if ls >= 3 else ("#eab308" if ls >= 2 else "#22c55e")
    st.markdown(
        f'<div style="text-align:center;padding:6px 0 10px 0;">'
        f'<span style="font-size:20px;font-weight:800;color:{_lc};letter-spacing:1px;">'
        f'ARDIŞIK ZARAR: {ls} / 3</span></div>',
        unsafe_allow_html=True,
    )
    _until = float(tr_scalper._load().get("loss_streak_until", 0) or 0)
    if _until > time.time():
        st.error(f"24 saatlik fren aktif — kalan {int((_until-time.time())//3600)} sa "
                 f"{int((_until-time.time())%3600//60)} dk", icon=":material/block:")

    # MULTI-TIMEFRAME ONAY (sadece NORMAL modda)
    st.divider()
    st.subheader("Zaman dilimi onayı (NORMAL mod)", divider="gray")
    mtf = market_regime.mtf_confirm("BTCUSDT")
    daily_txt = "ONAYLI ✅" if mtf.get("daily") else "ONAYSIZ ❌"
    h4_txt = "ONAYLI ✅" if mtf.get("h4") else "ONAYSIZ ❌"
    decision = "AL" if mtf.get("ok") else "BEKLE"
    m1, m2, m3 = st.columns(3)
    m1.metric("Günlük", daily_txt)
    m2.metric("4 Saatlik", h4_txt)
    m3.metric("Son Karar", decision)
    if mode == "GRID":
        st.caption("GRID modunda bu onay aranmaz — Grid kendi kuralıyla çalışır.")
    st.caption(f"Kural: günlük EMA50 sinyali + 4s EMA50 üstü = AL; 4s altı = BEKLE. · {mtf.get('reason', '')}")

    # CORRELATION PROTECTION
    st.divider()
    st.subheader("Korelasyon koruması", divider="gray")
    from ui import correlation_guard

    open_pos = tr_scalper._load().get("position") or {}
    new_sig = "ETHUSDT" if open_pos.get("symbol") == "BTCUSDT" else "BTCUSDT"
    cg = correlation_guard.guard_entry(open_pos.get("symbol"), new_sig)
    c1, c2 = st.columns(2)
    c1.metric("Açık Pozisyon", open_pos.get("symbol", "Yok"))
    c2.metric("Yeni Sinyal", f"{new_sig} — Korelasyon: {cg['corr'] if cg['corr'] is not None else '—'}"
              + (" — ENGELLENDİ" if not cg["allowed"] else " — İZİN"))
    st.caption(cg["reason"])
    corr_pairs = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT")
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

    vs = vol_position.atr_state("BTCUSDT")
    vcolor = {"Normal": "#22c55e", "Yüksek": "#eab308", "Çok Yüksek": "#ef4444"}.get(vs["state"], "#94a3b8")
    st.markdown(
        f'<div style="text-align:center;padding:6px 0 10px 0;">'
        f'<span style="font-size:18px;font-weight:800;color:{vcolor};">'
        f'ATR Durumu: {vs["state"]} · Pozisyon Boyutu: %{vs["pct"]*100:.0f}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Gerekçe: {vs['reason']} · ATR {vs['atr']} / 30g ort. {vs['avg']} (oran {vs['ratio']})")

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

    # KISMİ KÂR ALIMI
    st.divider()
    st.subheader("Kısmî kâr alımı", divider="gray")
    _p = tr_scalper._load().get("position") or {}
    if _p:
        pp = tr_scalper.partial_profit(_p, _p.get("entry", 0))
        k1, k2, k3 = st.columns(3)
        k1.metric("Kısmî Satış", "Yapıldı ✅" if _p.get("partial_done") else "Yapılmadı")
        k2.metric("Cebe Konan Kâr", f"{float(_p.get('partial_profit', 0)):+.2f} ₺")
        k3.metric("Kalan Pozisyon", f"₺{float(_p.get('qty', 0)) * float(_p.get('entry', 0)):.2f}")
        st.caption("%5 karda pozisyonun %50'si satılır, kalanı trailing TP ile devam eder · sadece NORMAL mod")
    else:
        st.info("Açık pozisyon yok — kısmî satış pasif.", icon=":material/info:")

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
        st.warning("BACKTEST UYARISI — strateji gözden geçirilmeli.", icon=":material/warning:")

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

    # AKILLI SEPET + FUNDING
    st.divider()
    st.subheader("Akıllı Sepet — 8 coin taranıyor", divider="gray")
    from ui import smart_basket

    pick = smart_basket.select()
    st.markdown("**Sepet Sıralaması:** " + " · ".join(
        f"{i+1}. {r['symbol']} — Skor {r['score']}" for i, r in enumerate(pick["ranking"][:8])))
    s1, s2 = st.columns(2)
    s1.metric("Seçilen Coin", pick["selected"])
    s2.metric("Funding Rate", f"%{pick['funding']:.4f}" if pick["funding"] is not None else "N/A (spot)")
    st.dataframe(
        pd.DataFrame([{
            "Coin": r["symbol"], "Skor": r["score"], "Rejim": r["regime"],
            "MTF": "✅" if r["mtf_ok"] else "❌", "Alış Baskısı": f"%{r['book_buy']:.0f}",
            "Gate": "✅" if r["gate_ok"] else "❌", "Funding": f"%{r['funding']}" if r["funding"] is not None else "N/A",
        } for r in pick["ranking"]]), use_container_width=True, hide_index=True,
    )
    st.caption("En yüksek skorlu coin'e alım · aynı anda max 2 pozisyon (her biri %10, toplam %20)")

    # WEBSOCKET + ORDER BOOK
    st.divider()
    st.subheader("Canlı veri akışı — WebSocket + Order Book", divider="gray")
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
        _vf = quant_lab.fetch("BTCUSDT", "1h", 30)
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
        gate_live = check_gate.run("BTCUSDT", price=tr_scalper.price("BTCUSDT"))
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
