"""BOT DURUMU — saniyesi saniyesine gerçek durum (koddan kanıt, tahmin yok)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from ui import (autonomous, autonomous_ops, risk_brakes, tr_journal,
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

    # --- SON KAYITLAR ---
    rows = tr_journal.recent(5)
    if rows:
        st.markdown("##### Son kayıtlar")
        st.dataframe(pd.DataFrame([{
            "Zaman": r.get("at"), "Tür": r.get("kind"),
            "Kayıt": " | ".join(r.get("events", [])[:2])[:180],
        } for r in reversed(rows)]), use_container_width=True, hide_index=True)
    st.caption(f"Şu an: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · her saniye yenilenir")


st.title("BOT DURUMU", icon=":material/traffic:")
_panel()
