"""Akıllı Panel: tek ekranda piyasa durumu, net karar ve kurgusal portföy."""

from __future__ import annotations

import logging

import streamlit as st

from ui import (
    audit_log, data_freshness, glossary, guide_ui, insights, motion, paper,
    performance, smart_guide, trust_gate, visual,
)
from ui.bist_universe import load_companies, ordered_symbols
from ui.components import real_money_warning
from ui.core import analysis_args, analyze_symbol
from ui.help_texts import h
from ui.market_session import status as session_status


st.html(
    """
<style>
.hsc-hero {
  background: linear-gradient(125deg, #0b1220 0%, #152238 55%, #1d3a5f 100%);
  border: 1px solid rgba(96,165,250,.28);
  border-radius: 18px; padding: 24px 28px; margin: 2px 0 16px;
  box-shadow: 0 10px 30px rgba(2,6,23,.35);
}
.hsc-hero-tag { font-size: 11px; letter-spacing: 2.4px; color: #60A5FA; font-weight: 700; }
.hsc-hero h2 { margin: 6px 0 6px; font-size: 27px; color: #F1F5F9; }
.hsc-hero p { margin: 0; color: #94A3B8; font-size: 14px; line-height: 1.5; }
.hsc-step {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 50%; font-size: 13px; font-weight: 800;
  background: rgba(96,165,250,.16); color: #60A5FA; border: 1px solid rgba(96,165,250,.4);
  margin-right: 8px;
}
.hsc-chip { display: inline-block; padding: 5px 12px; border-radius: 999px; font-weight: 700; font-size: 13px; }
.hsc-buy { background: rgba(16,185,129,.14); color: #34D399; border: 1px solid rgba(16,185,129,.42); }
.hsc-wait { background: rgba(245,158,11,.14); color: #FBBF24; border: 1px solid rgba(245,158,11,.42); }
.hsc-sell { background: rgba(244,63,94,.14); color: #F87171; border: 1px solid rgba(244,63,94,.42); }
.hsc-volatile { background: rgba(251,146,60,.14); color: #FDBA74; border: 1px solid rgba(251,146,60,.42); }
.hsc-verdict { border-radius: 14px; padding: 16px 20px; border-left: 6px solid; margin: 12px 0 4px; }
.hsc-verdict.buy { border-color: #34D399; background: rgba(16,185,129,.10); }
.hsc-verdict.wait { border-color: #FBBF24; background: rgba(245,158,11,.10); }
.hsc-verdict.sell { border-color: #F87171; background: rgba(244,63,94,.10); }
.hsc-big { font-size: 25px; font-weight: 800; line-height: 1.25; }
.hsc-note { font-size: 13px; color: #94A3B8; }
</style>
"""
)

st.html(
    """
<div class="hsc-hero">
  <div class="hsc-hero-tag">HSC BORSA ANALİZ</div>
  <h2>Akıllı Panel</h2>
  <p>Önce ne yapacağınızı bilin. Piyasa durumu, tek net karar ve kurgusal portföyünüz — tek ekranda, sade dille.</p>
</div>
"""
)

st.html(
    '<div class="hv-live" style="margin:2px 0 12px"><span class="hv-dot"></span> '
    'Canlı piyasa verisi bağlı · karar destek sistemi aktif</div>'
)

settings = st.session_state.settings
user = st.session_state.user


def _tone(action: str) -> str:
    if action == "AL":
        return "buy"
    if action.startswith("SAT"):
        return "sell"
    return "wait"


# ---------------------------------------------------------------- 1. Rejim
regime = smart_guide.market_regime()
guide = smart_guide.guide_for(regime)
with st.container(border=True, key="hsc_regime_card"):
    st.markdown("**1 · Piyasa durumu**")
    guide_ui.tip(
        "Rejim rozeti ne anlama geliyor?",
        [
            "**Yeşil (Yükseliş):** ana eğilim yukarı; planlı alım ve İşlem ajansı uygun.",
            "**Kırmızı (Düşüş):** eğilim aşağı; yeni alım yerine risk yönetimi öne çıkar.",
            "**Sarı (Yatay):** net yön yok; kısa vadeli tetikleyiciler veya BEKLE.",
            "**Turuncu (Oynak):** fiyat sert hareket ediyor; pozisyonu küçültün.",
        ],
        key="panel_regime",
        label="Rozet ne demek?",
    )
    left, right = st.columns([1.05, 2.1], gap="medium")
    with left:
        st.html(
            f'<div class="hsc-chip hsc-{guide["tone"]}">'
            f'{guide["chip"]} {regime.get("regime", "Yatay")}</div>'
        )
        st.caption(f"Rejim güveni: **%{int(regime.get('confidence', 0) or 0)}**")
        st.caption(guide["headline"])
    with right:
        st.markdown(f"**Size önerilen yöntem:** {guide['method']}")
        st.caption(guide["why"])
        st.caption(f"**Risk notu:** {guide['risk']}")
        if st.button(
            guide["page_label"], icon=":material/arrow_forward:", key="hsc_guide_open"
        ):
            st.switch_page(guide["page"])

# ---------------------------------------------------------------- 2. Karar
with st.container(border=True, key="hsc_decision_card"):
    st.markdown("**2 · Hisse ve net karar**")
    guide_ui.tip(
        "Burada ne seçmelisiniz?",
        [
            "**Hisse seçin:** listeden bir BIST hissesi seçin; karar kartı otomatik güncellenir.",
            "**Karar kartı:** yeşil AL, sarı BEKLE/İZLE, kırmızı SAT anlamına gelir. Güven skoru tek başına karar değildir.",
            "**Giriş / Stop / Hedef:** işlem taslağının seviyeleridir; stop zararı sınırlar, hedef kârı belirler.",
            "**Kurgusal pozisyon aç:** yalnızca seans içinde ve AL sinyalinde aktiftir; gerçek emir gönderilmez.",
        ],
        key="panel_decision",
        label="Nasıl kullanılır?",
    )

    universe = load_companies()
    symbols = ordered_symbols(universe)
    preferred = str(
        st.session_state.get("selected_symbol")
        or (settings.get("symbols") or ["THYAO"])[0]
    )
    index = symbols.index(preferred) if preferred in symbols else 0
    symbol = st.selectbox(
        "Hisse seçin", symbols, index=index, key="hsc_symbol",
        format_func=lambda s: f"{s} · {universe.get(s, s)}",
        help=h("bist_search"),
    )

    if st.session_state.get("hsc_prev_symbol") != symbol:
        st.session_state["hsc_prev_symbol"] = symbol
        st.session_state["hsc_flash_msg"] = f"{symbol} seçildi · karar kartı güncellendi."
    _flash_msg = st.session_state.pop("hsc_flash_msg", None)
    if _flash_msg:
        guide_ui.flash(_flash_msg)

    # "Bugün ne yapmalı?" — tek bir birleşik öneri
    with st.container(border=True, key="hsc_top_pick"):
        st.markdown("**Bugün ne yapmalı?** · izleme listem")
        guide_ui.tip(
            "Bu öneri nasıl oluşuyor?",
            [
                "İzleme listenizdeki hisseler taranır; risk profilinize uyan en güçlü aday seçilir.",
                "Güven eşiğini geçen aday yoksa sistem açıkça **BEKLE** der; uydurma sinyal üretmez.",
                "Aday gördüğünüzde 'Bu hisseyi incele' ile karar kartına taşıyabilirsiniz.",
            ],
            key="panel_top_pick",
            label="Nasıl hesaplanır?",
        )
        pick = smart_guide.top_pick(settings, regime)
        if not pick:
            st.caption("İzleme listesi analiz edilemedi. Birazdan tekrar deneyin.")
        elif pick["status"] != "ok":
            st.caption(pick["plain"])
        else:
            rec_pick = pick["recommendation"]
            st.markdown(
                f"**{pick['symbol']}** · {rec_pick['action']} · güven **%{rec_pick['confidence']}**"
            )
            st.caption(pick["plain"])
            if st.button("Bu hisseyi incele", icon=":material/analytics:", key="hsc_pick_open"):
                st.session_state.hsc_symbol = pick["symbol"]
                st.session_state.selected_symbol = pick["symbol"]
                st.rerun()

    st.container(height=1, border=False)
    try:
        args = analysis_args(settings)
        yf_symbol = symbol if symbol.endswith(".IS") else f"{symbol}.IS"
        result = analyze_symbol(
            yf_symbol, args["period"], args["interval"], args["indicators"],
            args["weights"], args["thresholds"], args["risk"],
            args["backtest_cfg"], args["guards"],
        )
        info, bt = result["info"], result["backtest"]
        rec = insights.recommendation(
            info, bt, str(settings.get("profile", "Dengeli")), settings.get("risk", {})
        )
        # Fail-closed veri kapısı: bozuk/eski veride AL/SAT bastırılır.
        snap = data_freshness.snapshot(symbol)
        gate = trust_gate.evaluate(
            symbol,
            {"decision": rec["action"], "confidence": rec["confidence"]},
            snap, settings,
        )
        rec = trust_gate.apply_gate(rec, gate)
        audit_log.append(user, "PANEL_KARAR", {
            "symbol": symbol,
            "decision": rec["action"],
            "gate": gate["level"],
            "source": gate["source"],
            "idempotency_key": gate["decision_id"],
        })
    except Exception as exc:
        logging.exception("Akıllı Panel analiz hatası: %s", exc)
        info, rec = None, None

    if not rec:
        st.warning(
            "Bu hisse için şu an analiz verisi alınamadı. İnternet bağlantısını kontrol edip "
            "birazdan tekrar deneyin.", icon=":material/warning:"
        )
    else:
        trust_gate.render(gate)
        tone = _tone(rec["action"])
        st.html(
            f'<div class="hsc-verdict {tone}">'
            f'<div class="hsc-big">{symbol} · {rec["action"]}</div>'
            f'<div class="hsc-note">Güven skoru %{rec["confidence"]} · '
            f'{insights.signal_label(str(info.get("signal", "NEUTRAL")))}</div></div>'
        )
        st.caption(smart_guide.plain_summary(rec, info, regime))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Giriş", f"{rec['entry']:,.2f} ₺", help="Son analiz fiyatı.")
        m2.metric("Stop", f"{rec['stop']:,.2f} ₺", help=h("stop_loss"))
        m3.metric("Hedef", f"{rec['target']:,.2f} ₺", help=h("take_profit"))
        m4.metric("Önerilen pay", f"%{rec['size_pct']}", help=h("position_size"))

        data_freshness.freshness_badges(symbol)

        session = session_status()
        b1, b2 = st.columns([1.1, 1], gap="medium")
        with b1:
            if st.button(
                "Kurgusal pozisyon aç",
                icon=":material/add_circle:",
                key="hsc_open",
                disabled=rec["action"] != "AL" or not session["in_session"],
                help="Yalnızca seans içinde ve AL sinyalinde; gerçek emir gönderilmez.",
            ):
                qty = float(rec["amount"]) / float(rec["entry"]) if rec["entry"] else 0
                paper.open_position(
                    user, symbol, round(qty, 2), float(rec["entry"]),
                    float(rec["stop"]), float(rec["target"]), int(rec["confidence"]),
                    f"Akıllı panel: {rec['action']}",
                )
                st.toast(f"{symbol} kurgusal pozisyon açıldı.", icon=":material/check:")
        with b2:
            if st.button(
                "Detaylı analizi aç", icon=":material/open_in_new:", key="hsc_detail"
            ):
                st.session_state.selected_symbol = symbol
                st.switch_page("app_pages/hisse.py")

# ---------------------------------------------------------------- 3. Portföy
with st.container(border=True, key="hsc_pnl_panel"):
    st.markdown("**3 · Kurgusal portföyüm**")
    guide_ui.tip(
        "Portföy rakamları ne ifade ediyor?",
        [
            "**Açık pozisyon:** henüz kapatılmamış kurgusal işlem sayısı.",
            "**Açık K/Z:** bu pozisyonların güncel fiyatla hesaplanan kâr/zararı.",
            "**Kapanan sinyal / Net R:** sonuç defterine işlenen işlem sayısı ve toplam R çarpanı.",
            "Detay ve veri sıfırlama için **Hesabım** sayfasını kullanın.",
        ],
        key="panel_portfolio",
        label="Bu sayılar ne?",
    )
    try:
        open_positions = paper.evaluate(user, settings)
    except Exception as exc:
        logging.exception("Akıllı Panel portföy değerleme hatası: %s", exc)
        open_positions = []
    summary = performance.summarize(performance.read_records(user))
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Açık pozisyon", len(open_positions))
    p2.metric(
        "Açık K/Z",
        f"{sum(float(x.get('pnl_amount', 0) or 0) for x in open_positions):+,.0f} ₺",
    )
    p3.metric("Kapanan sinyal", summary["total"] if summary else 0)
    p4.metric("Net R", f"{summary['net_r']:+.2f}R" if summary else "—")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Hesabımı aç", icon=":material/person:", key="hsc_account"):
            st.switch_page("app_pages/hesabim.py")
    with c2:
        if st.button("Sinyal performansı", icon=":material/query_stats:", key="hsc_perf"):
            st.switch_page("app_pages/performans.py")

real_money_warning(compact=True)

# ---------------------------------------------------------------- Gelişmiş
ADVANCED = [
    ("İşlem ajansı", "app_pages/ajans.py", ":material/psychology:"),
    ("Anlık sinyal", "app_pages/anlik.py", ":material/flash_on:"),
    ("Sinyal terminali", "app_pages/terminal.py", ":material/monitoring:"),
    ("BIST tarayıcı", "app_pages/tarayici.py", ":material/radar:"),
    ("İşlem botu", "app_pages/bot.py", ":material/smart_toy:"),
    ("Canlı işlem", "app_pages/canli.py", ":material/bolt:"),
    ("Akıllı risk merkezi", "app_pages/risk.py", ":material/shield:"),
    ("Strateji laboratuvarı", "app_pages/laboratuvar.py", ":material/science:"),
    ("Denetim ve doğrulama", "app_pages/denetim.py", ":material/fact_check:"),
    ("Piyasa analizi", "app_pages/piyasa.py", ":material/dashboard:"),
    ("Hisse detayı", "app_pages/hisse.py", ":material/analytics:"),
    ("Portföy ve test", "app_pages/portfoy.py", ":material/account_balance_wallet:"),
    ("Ayarlar", "app_pages/ayarlar.py", ":material/settings:"),
]
with st.expander("Gelişmiş analizler — tüm araçlar", icon=":material/tune:"):
    st.caption("Buradaki 13 araç olduğu gibi çalışmaya devam eder; Akıllı Panel yalnızca sade bir giriş kapısıdır.")
    cols = st.columns(3)
    for i, (title, path, icon) in enumerate(ADVANCED):
        with cols[i % 3]:
            if st.button(title, icon=icon, key=f"hsc_adv_{i}", use_container_width=True):
                st.switch_page(path)

st.markdown("**HSC farkı — güveni gösterir, iddia etmez**")
motion.stagger([
    '<div class="hscm-card" style="border:1px solid rgba(52,211,153,.35);border-radius:10px;padding:9px 11px;'
    'background:rgba(52,211,153,.08);font-size:12px;color:#34D399;font-weight:700">✓ Veri kapısı: taze ve tutarlı veri</div>',
    '<div class="hscm-card" style="border:1px solid rgba(96,165,250,.35);border-radius:10px;padding:9px 11px;'
    'background:rgba(96,165,250,.08);font-size:12px;color:#93C5FD;font-weight:700">✓ Maliyet sonrası R hesabı</div>',
    '<div class="hscm-card" style="border:1px solid rgba(251,146,60,.35);border-radius:10px;padding:9px 11px;'
    'background:rgba(251,146,60,.08);font-size:12px;color:#FDBA74;font-weight:700">✓ Kaybedenler de defterde</div>',
    '<div class="hscm-card" style="border:1px solid rgba(167,139,250,.35);border-radius:10px;padding:9px 11px;'
    'background:rgba(167,139,250,.08);font-size:12px;color:#C4B5FD;font-weight:700">✓ Gerçek emir yok</div>',
])

audit_log.render_panel(user)
visual.trust_row()
glossary.render_glossary()
