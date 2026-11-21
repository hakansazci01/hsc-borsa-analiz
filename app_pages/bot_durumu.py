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
    health = autonomous.HEARTBEAT
    try:
        hb = json.loads(health.read_text(encoding="utf-8"))
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
    mode = tr_scalper._load().get("mode", "BEKLEME")
    if reg["range"]:
        mode = "GRID"
    elif reg["bear"]:
        mode = "BEKLEME"
    else:
        mode = "NORMAL"
    _mc = {"GRID": "#eab308", "NORMAL": "#22c55e", "BEKLEME": "#ef4444"}[mode]
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
    elif mode == "BEKLEME":
        st.warning("AYI rejimi — Grid yapılmaz, tamamen bekleme. Para güvende.",
                   icon=":material/warning:")
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
