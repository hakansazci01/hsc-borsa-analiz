"""OTONOM DURUM — tek bakışta sistemin gerçek durumu (10 sn'de bir yenilenir)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from ui import autonomous, quant_lab, summary_report, tr_journal, tr_monitor, tr_scalper


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

    # --- ÖZET RAPOR ---
    st.divider()
    st.subheader("Başarı özeti — tek bakışta", divider="gray")
    rep = summary_report.build()
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Toplam karar", rep["decisions"])
    q2.metric("Öngörü testi", rep["prediction_tests"])
    q3.metric("Doğru / Yanlış", f"{rep['prediction_correct']} / {rep['prediction_wrong']}")
    q4.metric("İsabet", f"%{rep['accuracy']}" if rep["accuracy"] is not None else "—")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Emir kaydı", rep["orders"])
    c2.metric("İşlem", rep["trades"])
    c3.metric("Net K/Z", f"{rep['net_pnl']:+.2f} ₺")
    c4.metric("Bakiye", f"₺{rep['balance']:,.0f}")
    with st.expander("Tam özet raporunu oku", icon=":material/description:"):
        st.markdown(summary_report.to_markdown(rep))
        if st.button("Raporu dosyaya yaz (GitHub için)", key="write_report"):
            path = summary_report.write()
            st.success(f"Yazıldı: `{path.relative_to(summary_report.ROOT)}`", icon=":material/check:")

    # --- TAM TETİKLEYİCİ: ne zaman alır / satar ---
    st.divider()
    st.subheader("Tam tetikleyici — sistem NE ZAMAN işlem yapar?", divider="gray")
    st.markdown(
        """
        **ALım için üç koşulun hepsi birden gerçekleşmeli:**
        1. Doğrulanmış edge mevcut (şu an ✅ 50)
        2. BTC **günlük kapanışı EMA50'nin üstüne geçmeli** (ayı rejimi bitmeli)
        3. Hedef coin'in günlük kapanışı kendi EMA50'sini geçip pullback yapmalı

        **SATış için:** +%0,80 kâr hedefi, -%0,35 stop, zirveden %0,35 trailing,
        veya 15 dakikadan uzun durgunluk.
        """
    )
    coins = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT",
             "ADAUSDT", "LINKUSDT", "BNBUSDT", "SOLUSDT")
    trig_rows = []
    for sym in coins:
        frame = quant_lab.fetch(sym, "1d", 200)
        if frame is None:
            continue
        m = quant_lab.ema(frame["Close"], 50)
        last = float(frame["Close"].iloc[-1])
        ma = float(m.iloc[-1])
        dist = (last / ma - 1) * 100
        trig_rows.append({
            "Coin": sym.replace("USDT", ""),
            "Fiyat": round(last, 4),
            "EMA50": round(ma, 4),
            "EMA50 mesafesi": f"{dist:+.1f}%",
            "Giriş": "HAZIR ✅" if dist > 0 else f"%{abs(dist):.1f} yükseliş gerekli",
        })
    if trig_rows:
        st.dataframe(pd.DataFrame(trig_rows), use_container_width=True, hide_index=True)
    st.caption(
        "Bu tablo **gerçek günlük veriden** üretilir. 'Giriş' sütunu HAZIR olduğunda "
        "ve BTC de EMA50 üstüne geçtiğinde motor kendiliğinden emir atar. "
        "Şu an hiçbiri HAZIR değil — bu yüzden işlem yok."
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

    st.divider()
    st.subheader("Bildirimler", divider="gray")
    from ui import notify
    from ui.core import default_settings

    topic = str(default_settings().get("alerts", {}).get("ntfy_topic", "") or "")
    if topic:
        st.caption(
            f"Gerçek emir/karar değişiminde telefonunuza push gider. "
            f"Abone olmak için: **https://ntfy.sh/{topic}** (tarayıcıda açın, "
            "ntfy uygulamasıyla QR okutun)."
        )
        if st.button("Test bildirimi gönder", key="ntfy_test_btn"):
            ok, msg = notify.send_ntfy("HSC test bildirimi — sistem çalışıyor.", topic)
            st.caption(("✅ " if ok else "❌ ") + msg)
    else:
        st.caption("Bildirim konusu tanımlı değil.")

    if st.button("ŞİMDİ ANALİZ ET VE KARAR VER", icon=":material/refresh:", key="status_run"):
        with st.spinner("Gerçek veriler analiz ediliyor..."):
            d = autonomous.run_once()
        st.caption(f"Karar: **{d['decision']}** — " + ("; ".join(d["reasons"]) or "edge doğrulandı"))
        st.rerun()


_dashboard()
