"""OTONOM DURUM — tek bakışta sistemin gerçek durumu (10 sn'de bir yenilenir)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from ui import autonomous, tr_journal, tr_monitor, tr_scalper


st.title("Otonom durum", icon=":material/monitoring:")
st.caption(
    "Bu sayfa **10 saniyede bir kendiliğinden yenilenir.** Bütün değerler gerçek "
    "Binance TR API'sinden ve yerel karar kayıtlarındandır; tahmin/simülasyon değildir."
)


@st.fragment(run_every="10s")
def _dashboard():
    # --- yönetici sağlığı ---
    hb_path = autonomous.HEARTBEAT
    try:
        hb = json.loads(hb_path.read_text(encoding="utf-8"))
        age = int(time.time() - float(hb.get("ts", 0)))
    except Exception:
        hb, age = {}, 999999

    alive = age <= 180
    state = autonomous._load()
    decision = state.get("last_decision", {})
    acc = autonomous.accuracy(state)

    a, b, c, d = st.columns(4)
    a.metric("YÖNETİCİ", "🟢 ÇALIŞIYOR" if alive else "🔴 DURDU",
             help=f"Son nabız {age} sn önce")
    b.metric("SON KARAR", decision.get("decision", "—"))
    c.metric("DOĞRULANMIŞ EDGE", decision.get("robust", 0),
             help="Eğitim ve dış örneklemde pozitif çıkan strateji sayısı")
    d.metric("ÖNGÖRÜ İSABETİ", f"%{acc['rate']}" if acc["rate"] is not None else "—",
             help=f"{acc['n']} gerçek fiyat testi")

    if not alive:
        st.error("⚠️ Yönetici nabzı 3 dakikadan eski. 5-dakikalık Windows görevi "
                 "sistemi otomatik başlatacak; veya aşağıdaki düğmeye basın.")
    else:
        st.caption(
            f"✅ Nabız **{hb.get('at', '—')}** · PID **{hb.get('pid', '—')}** · "
            f"son analiz **{decision.get('at', '—')}**"
        )

    # --- sermaye ve pozisyon ---
    st.divider()
    bal = tr_scalper.available_try()
    pos = tr_monitor.live_metrics()["position"]
    summary = tr_monitor.summary()
    e, f, g = st.columns(3)
    e.metric("KULLANILABİLİR TRY", f"₺{bal:,.2f}")
    f.metric("AÇIK POZİSYON", pos["symbol"] if pos else "Yok")
    g.metric("GERÇEKLEŞEN K/Z", f"{summary['net_pnl']:+.2f} ₺")

    if pos:
        st.success(
            f"**{pos['symbol']}** · {pos['qty']} adet · giriş {pos['entry']:,.4f} ₺ · "
            f"anlık {pos['price']:,.4f} ₺ · **{pos['pnl']:+.3f} ₺ ({pos['pct']:+.2f}%)** · "
            f"geçen süre {pos['elapsed']}",
            icon=":material/trending_up:",
        )
        st.progress(pos["progress"], text=(
            f"KİLİTLİ STOP {pos['effective_sl']:,.4f} ◀ giriş {pos['entry']:,.4f} ▶ "
            f"HEDEF {pos['tp']:,.4f}"
        ))
    else:
        reasons = decision.get("reasons", [])
        st.info(
            "**Açık işlem yok.** "
            + ("Neden: " + " · ".join(reasons) if reasons else "Giriş sinyali bekleniyor.")
            + " Bu, sistemin doğru çalıştığı anlamına gelir: edge/rejim uygun olmadan "
              "para riske atılmaz.",
            icon=":material/info:",
        )

    # --- işlem defteri ---
    st.divider()
    st.subheader("İşlem defteri — ne yapıldı / neden yapılmadı", divider="gray")
    records = tr_journal.recent(12)
    if records:
        rows = [{
            "Zaman": r.get("at", "—"),
            "Tür": r.get("kind", "—"),
            "Kayıt": " | ".join(r.get("events", [])[:2])[:180],
        } for r in reversed(records)]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Henüz kayıt yok.")

    if st.button("ŞİMDİ ANALİZ ET VE KARAR VER", icon=":material/refresh:", key="status_run"):
        with st.spinner("Gerçek veriler analiz ediliyor..."):
            d = autonomous.run_once()
        st.caption(f"Karar: **{d['decision']}** — " + ("; ".join(d["reasons"]) or "edge doğrulandı"))
        st.rerun()


_dashboard()
