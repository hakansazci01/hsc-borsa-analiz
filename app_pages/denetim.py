"""Denetim ve doğrulama: hata kaynakları, istatistiksel güven ve gerçek para kontrol listesi."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import api_keys
from ui.audit import (
    backtest_report, data_quality_report, readiness_check, signal_quality_report,
)
from ui.config_doctor import (
    STATUS_COLOR, STATUS_LABEL, run_all as doctor_run, summary as doctor_summary,
)
from ui.broker import account_status
from ui.bist_universe import load_companies, ordered_symbols
from ui.components import real_money_warning
from ui.core import analysis_args, analyze_symbol
from ui.finnhub import us_quote
from ui.help_texts import h
from ui.live_data import get_live_snapshot
from ui.risk_engine import adjust_decision_for_regime, detect_regime
from ui.trade_engine import build_decision


settings = st.session_state.settings
universe = load_companies()

st.subheader("Denetim ve doğrulama", divider="gray")
real_money_warning()

# ---- Yapılandırma Doktoru ----
with st.container(border=True):
    st.subheader("Yapılandırma Doktoru", divider="gray")
    st.caption(
        "config.yaml, API anahtarları, kullanıcı dosyaları ve sonuç raporları doğrulanır. "
        "Değerler gösterilmez; yalnızca dosya bütünlüğü ve alan tipleri kontrol edilir."
    )
    doctor_rows = doctor_run(st.session_state.user)
    doctor_counts = doctor_summary(doctor_rows)
    c1, c2, c3 = st.columns(3)
    c1.metric("Geçerli", doctor_counts["ok"], icon=":material/check_circle:")
    c2.metric("Uyarı", doctor_counts["warn"], icon=":material/warning:")
    c3.metric("Hata", doctor_counts["error"], icon=":material/error:")
    for row in doctor_rows:
        with st.container(horizontal=True, vertical_alignment="bottom"):
            st.badge(STATUS_LABEL[row["status"]], color=STATUS_COLOR[row["status"]])
            st.markdown(f"**{row['title']}**")
            st.caption(row["detail"])
        if row["fix"]:
            st.caption(f"→ {row['fix']}")
    if doctor_counts["error"]:
        st.error(
            "Yapılandırmada hata var. Bu dosyalar düzeltilmeden sinyaller güvenilir olmayabilir.",
            icon=":material/error:",
        )


def _yahoo_symbol(raw: str) -> str:
    s = raw.strip().upper()
    if "." in s:
        return s
    return s + ".IS" if s in universe and s != "BIST100" else s


symbol = st.selectbox(
    "Denetlenecek BIST hissesi", ordered_symbols(universe),
    format_func=lambda s: f"{s} · {universe.get(s, s)}",
    key="audit_symbol", help=h("bist_search"),
)
args = analysis_args(settings)

try:
    res = analyze_symbol(
        _yahoo_symbol(symbol), args["period"], args["interval"], args["indicators"],
        args["weights"], args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
    )
    snap = get_live_snapshot(symbol)
    decision = build_decision(snap, "Dengeli", settings["risk"], 0.25)
    try:
        decision = adjust_decision_for_regime(decision, detect_regime(symbol))
    except Exception:
        pass
    regime = {"confidence": decision.get("regime_confidence", 50), "regime": decision.get("regime", "")} if decision.get("regime") else None
except Exception as exc:
    st.error(f"{symbol} için denetim verisi alınamadı: {exc}", icon=":material/error:")
    st.stop()

bt_report = backtest_report(res["backtest"], settings["risk"])
dq = data_quality_report(snap)
sq = signal_quality_report(decision, regime)
ready = readiness_check(bt_report, dq, sq)

# ---- Bilinen hata kaynakları ----
with st.container(border=True):
    st.subheader("Hata kaynakları ve alınan önlemler", divider="gray")
    st.dataframe(
        pd.DataFrame([
            {"Hata kaynağı": "Backtest'te giriş gününün High/Low ile stop kontrolü (look-ahead)",
             "Etki": "Getiri ve kazanma oranını yapay yükseltiyordu",
             "Durum": "DÜZELTİLDİ", "Açıklama": "Giriş günü kontrolü atlanıyor; işlem ertesi gün kapanışta açılıyor."},
            {"Hata kaynağı": "Kayma (slippage) ve komisyon eksikliği",
             "Etki": "Gerçek işlem maliyeti olduğundan düşük hesaplanıyordu",
             "Durum": "DÜZELTİLDİ", "Açıklama": "Giriş/çıkışta %0.1 kayma + komisyon uygulanıyor; duyarlılık tablosu eklendi."},
            {"Hata kaynağı": "2 yıllık kümülatif VWAP (güncel adil fiyat değil)",
             "Etki": "Fiyat/VWAP sinyali gecikmeli ve anlamsız olabiliyordu",
             "Durum": "DÜZELTİLDİ", "Açıklama": "20 günlük kaydırılmalı VWAP kullanılıyor."},
            {"Hata kaynağı": "Ücretsiz BIST verisinde ~15 dk gecikme",
             "Etki": "Anlık al/sat kararı güncel fiyatı yansıtmayabilir",
             "Durum": "KALIYOR", "Açıklama": "Lisanslı gerçek zamanlı veri / aracı kurum API'si gerekir."},
            {"Hata kaynağı": "Küçük backtest örneklemi",
             "Etki": "Kazanma oranı istatistiksel olarak güvenilmez",
             "Durum": "ÖLÇÜLDÜ", "Açıklama": f"{bt_report['trades']} işlem; %95 güven aralığı %{bt_report['ci_low']}-{bt_report['ci_high']}."},
            {"Hata kaynağı": "Haber duyarımı sözlük tabanlı",
             "Etki": "KAP başlıkları yanlış yorumlanabilir",
             "Durum": "KISMI", "Açıklama": "Yönlü başlık oranı gösterilir; LLM tabanlı yorumlama değildir."},
            {"Hata kaynağı": "Walk-forward / out-of-sample doğrulama yok",
             "Etki": "Parametreler değişen rejimlere uyum sağlamayabilir",
             "Durum": "EKSİK", "Açıklama": "Ayrı bir doğrulama çalışması gereklidir."},
        ]),
        hide_index=True,
        alt="Sinyal sisteminin hata kaynakları ve düzeltilme durumları",
    )

# ---- Backtest güvenilirliği ----
with st.container(border=True):
    st.subheader("Backtest istatistiksel güvenilirliği", divider="gray")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Kapanmış işlem", bt_report["trades"], help=h("trades"))
    m2.metric("Kazanma oranı", f"%{bt_report['win_rate_pct']}", help=h("win_rate"))
    m3.metric("Kâr faktörü", bt_report["profit_factor"] if bt_report["profit_factor"] else "—",
              help="Toplam kazancın toplam kayba oranı. 1'in altında strateji kayıp üretiyor demektir.")
    m4.metric("Beklenti / işlem", f"{bt_report['expectancy_pct']:+.3f}%", help="İşlem başına ortalama getiri (maliyetler sonrası).")

    st.caption(
        f"Kazanma oranı %95 güven aralığı: **%{bt_report['ci_low']} – %{bt_report['ci_high']}** · "
        f"Örneklem: **{bt_report['sample_verdict']}**"
    )
    st.info(bt_report["verdict"], icon=":material/info:")

    st.markdown("**Kayma duyarlılığı**")
    sens = pd.DataFrame(bt_report["sensitivity"])
    st.dataframe(sens, hide_index=True, alt="Farklı kayma oranlarında işlem beklentisi")
    st.caption(
        f"Mevcut ayarda kayma %{bt_report['base_slippage_pct']:.2f}. "
        "Kayma arttıkça beklenti negatife dönüyorsa gerçek işlemde kâr etmek zordur."
    )

# ---- Veri ve sinyal kalitesi ----
c1, c2 = st.columns(2, gap="medium")
with c1:
    with st.container(border=True):
        st.subheader("Veri kalitesi", divider="gray")
        st.metric("Tazelik", dq["freshness"], help="Kotasyonun şu anki saate göre yaşı.")
        st.caption(
            f"Kaynak: {dq['source']} · Seans: {dq['session']} · "
            f"Kotasyon: {dq['quote_time']} · Yaş: {dq['age_minutes']} dk"
        )
        for warning in dq["warnings"]:
            st.caption(f"- {warning}")
        from ui import source_attestation

        source_attestation.render_panel()
        from ui import live_readiness

        live_readiness.render()
with c2:
    with st.container(border=True):
        st.subheader("Sinyal kalitesi", divider="gray")
        st.metric("Kalite skoru", f"{sq['score']}/100", help=h("confidence"))
        st.caption(
            f"Zaman dilimi uzlaşısı: %{sq['consensus_pct']} · "
            f"AL oyu {sq['buy_votes']} / SAT oyu {sq['sell_votes']} / nötr {sq['neutral_votes']}"
        )
        st.caption(f"Haber: {sq['news_items']} başlık, yönlü olan %{sq['news_directional_pct']}")
        for warning in sq["warnings"]:
            st.caption(f"- {warning}")

# ---- Kontrol listesi ----
st.container(height=1, border=False)
with st.container(border=True):
    st.subheader("Gerçek para kontrol listesi", divider="gray")
    st.error(
        f"**{ready['headline']}** — {ready['summary']}",
        icon=":material/gpp_maybe:",
    )
    st.dataframe(
        pd.DataFrame(ready["items"]),
        hide_index=True,
        alt="Gerçek para ile işlem öncesi zorunlu kontrollerin durumu",
    )

    st.markdown("**Gerçek para öncesi yapılması gerekenler**")
    st.markdown(
        "1. **Lisanslı veri:** Borsa İstanbul onaylı gerçek zamanlı veri sağlayıcısı veya aracı kurum API'si edinin.\n"
        "2. **Emir altyapısı:** Aracı kurumun test ortamında emir iletimini doğrulayın; bu uygulama emir göndermez.\n"
        "3. **Kağıt işlem:** En az 50-100 sinyali gerçek zamanlı takip edip sinyalin sonucunu kaydedin.\n"
        "4. **Walk-forward doğrulama:** Parametreleri dönemlere ayırıp out-of-sample performansı ölçün.\n"
        "5. **Sermaye kuralı:** İşlem başına riski %1-2 ile sınırlayın; pozisyonu Kelly tavanıyla sınırlandırın.\n"
        "6. **Teyit:** Her emir öncesi güncel fiyatı ve KAP bildirimlerini manuel kontrol edin."
    )

# ---- Veri kaynakları ve API rehberi ----
st.container(height=1, border=False)
with st.container(border=True):
    st.subheader("Veri kaynakları ve API anahtarları", divider="gray")
    st.caption(
        "Aşağıda her verinin nereden geldiği, anahtarın nereden alınacağı ve hangi dosyaya "
        "kaydedileceği gösterilir. Anahtar değerleri arayüzde gösterilmez."
    )
    st.info(
        "Kayıt adresine git → anahtarı kopyala → aşağıdaki ** Anahtarları tarayıcıdan düzenle** "
        "bölümüne yapıştır **veya** proje kökündeki `.streamlit/secrets.toml` dosyasına ilgili bölümü ekle.",
        icon=":material/info:",
    )
    api_keys.render_guide()
    api_keys.render_editor()
    from ui import secret_policy

    secret_policy.render_panel()

    st.markdown("**Hızlı bağlantı testleri**")
    t1, t2 = st.columns(2)
    with t1:
        ok = bool(us_quote("AAPL"))
        st.badge("Finnhub", color="green" if ok else "orange")
        st.caption("AAPL kotasyonu alındı" if ok else "BIST kapsamı yok veya anahtar geçersiz")
    with t2:
        alpaca = account_status()
        st.badge("Alpaca paper", color="green" if alpaca.get("ok") else "orange")
        st.caption("Bağlı" if alpaca.get("ok") else alpaca.get("reason", "Kullanılamıyor"))

st.caption("Bu denetim bir garanti değildir. Geçmiş performans gelecek getiriyi göstermez.")
