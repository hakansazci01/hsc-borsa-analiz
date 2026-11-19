"""
Görsel güven ve istatistik katmanı.

Fintech arayüz ilkelerini uygular: güven sinyalleri, net büyük rakamlar,
tutarlı kart düzeni ve ölçülü mikro-animasyonlar. Tüm stiller `hv-` önekiyle
sınırlıdır; analiz motorlarına ve diğer sayfalara etkisi yoktur.
"""

from __future__ import annotations

import streamlit as st


CSS = """
<style>
@keyframes hvFloat { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-7px)} }
@keyframes hvIn { from{opacity:0;transform:translateY(14px) scale(.99)} to{opacity:1;transform:none} }
@keyframes hvPulse { 0%,100%{opacity:.55;transform:scale(1)} 50%{opacity:.12;transform:scale(1.7)} }
@keyframes hvShine { 0%{background-position:-180% 0} 100%{background-position:180% 0} }
@keyframes hvCandle { from{opacity:0;transform:scaleY(.15)} to{opacity:1;transform:none} }
@keyframes hvDraw { to{stroke-dashoffset:0} }
@keyframes hvCoinFloat { 0%,100%{transform:translateY(0) rotate(-8deg)} 50%{transform:translateY(-10px) rotate(8deg)} }
@keyframes hvNoteFloat { 0%,100%{transform:translateY(0) rotate(3deg)} 50%{transform:translateY(-7px) rotate(-3deg)} }
.hv-hero {
  position: relative; overflow: hidden;
  background: linear-gradient(125deg,#0b1220 0%,#16243a 58%,#1c3a60 100%);
  border: 1px solid rgba(96,165,250,.32); border-radius: 20px;
  padding: 26px 28px; margin-bottom: 16px;
  box-shadow: 0 14px 38px rgba(2,6,23,.38);
  animation: hvIn .55s cubic-bezier(.2,.8,.2,1) both;
}
.hv-orb {
  position: absolute; width: 260px; height: 260px; border-radius: 50%;
  right: -70px; top: -110px;
  background: radial-gradient(circle, rgba(96,165,250,.30), transparent 70%);
  animation: hvFloat 7s ease-in-out infinite;
}
.hv-orb::after {
  content: ""; position: absolute; width: 130px; height: 130px;
  border-radius: 50%; background: rgba(52,211,153,.22);
  right: 130px; top: 150px; animation: hvPulse 3.4s ease-in-out infinite;
}
.hv-tag {
  position: relative; display: inline-block; font-size: 11px; font-weight: 800;
  letter-spacing: 2.2px; color: #93C5FD;
  background: rgba(96,165,250,.12); border: 1px solid rgba(96,165,250,.34);
  border-radius: 999px; padding: 4px 11px; margin-bottom: 12px;
}
.hv-title {
  position: relative; margin: 0 0 8px; font-size: 27px; line-height: 1.25;
  font-weight: 800; color: #F8FAFC;
}
.hv-desc { position: relative; margin: 0; color: #94A3B8; font-size: 13.5px; line-height: 1.6; }
.hv-stats { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin: 4px 0 14px; }
.hv-stat {
  animation: hvIn .5s cubic-bezier(.2,.8,.2,1) both;
  border: 1px solid rgba(96,165,250,.26); border-radius: 14px;
  background: linear-gradient(160deg, rgba(30,41,59,.85), rgba(15,23,42,.7));
  padding: 13px 14px; transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease;
}
.hv-stat:nth-child(1){animation-delay:.04s}
.hv-stat:nth-child(2){animation-delay:.10s}
.hv-stat:nth-child(3){animation-delay:.16s}
.hv-stat:nth-child(4){animation-delay:.22s}
.hv-stat:hover {
  transform: translateY(-3px); border-color: rgba(96,165,250,.6);
  box-shadow: 0 10px 26px rgba(96,165,250,.18);
}
.hv-num { font-size: 22px; font-weight: 800; color: #F1F5F9; line-height: 1.1; }
.hv-num small { font-size: 12px; color: #60A5FA; }
.hv-lbl { margin-top: 5px; font-size: 11.5px; color: #94A3B8; }
.hv-live {
  display: inline-flex; align-items: center; gap: 8px; font-size: 12px;
  color: #34D399; font-weight: 700;
}
.hv-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #34D399; position: relative;
}
.hv-dot::after {
  content: ""; position: absolute; inset: -4px; border-radius: 50%;
  background: #34D399; animation: hvPulse 2.4s ease-in-out infinite;
}
.hv-shine {
  background: linear-gradient(100deg, rgba(96,165,250,0) 30%, rgba(96,165,250,.18) 50%, rgba(96,165,250,0) 70%);
  background-size: 200% 100%; animation: hvShine 4.5s linear infinite;
  height: 1px; margin-top: 14px;
}
.hv-chart {
  border: 1px solid rgba(96,165,250,.26); border-radius: 14px;
  background: rgba(15,23,42,.8); padding: 11px 13px 7px; margin: 2px 0 12px;
}
.hv-chart-head { display: flex; justify-content: space-between; align-items: center;
  font-size: 12px; font-weight: 800; color: #CBD5E1; margin-bottom: 3px; }
.hv-candle { animation: hvCandle .5s cubic-bezier(.2,.8,.2,1) both;
  transform-box: fill-box; transform-origin: center; }
.hv-ema { fill: none; stroke: #60A5FA; stroke-width: 1.7; stroke-dasharray: 900;
  stroke-dashoffset: 900; animation: hvDraw 2.8s ease forwards; opacity: .85; }
.hv-axis { display: flex; justify-content: space-between; color: #64748B; font-size: 10px; margin-top: -3px; }
.hv-praise { border-left: 2px solid rgba(52,211,153,.55); padding: 3px 0 3px 12px; margin: 2px 0 10px; }
.hv-praise-head { font-size: 12px; font-weight: 800; color: #34D399; letter-spacing: .4px; margin-bottom: 8px; }
.hv-praise-item { display: flex; gap: 9px; align-items: flex-start; margin: 7px 0;
  animation: hvIn .5s cubic-bezier(.2,.8,.2,1) both; }
.hv-praise-item:nth-child(2){animation-delay:.05s}
.hv-praise-item:nth-child(3){animation-delay:.12s}
.hv-praise-item:nth-child(4){animation-delay:.19s}
.hv-praise-item > span { color: #34D399; font-size: 13px; line-height: 1.35; }
.hv-praise-item b { display: block; font-size: 12.5px; color: #E2E8F0; }
.hv-praise-item small { display: block; color: #94A3B8; font-size: 11px; margin-top: 1px; line-height: 1.4; }
.hv-step-card {
  animation: hvIn .5s cubic-bezier(.2,.8,.2,1) both;
  border: 1px solid rgba(96,165,250,.24); border-radius: 12px;
  background: rgba(30,41,59,.6); padding: 11px 12px; transition: transform .2s, border-color .2s;
}
.hv-step-card:nth-child(2){animation-delay:.06s}
.hv-step-card:nth-child(3){animation-delay:.12s}
.hv-step-card:hover { transform: translateY(-3px); border-color: rgba(96,165,250,.6); }
.hv-step-no {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%; font-size: 11px; font-weight: 800;
  background: rgba(96,165,250,.18); color: #93C5FD; border: 1px solid rgba(96,165,250,.45);
  margin-bottom: 6px;
}
.hv-step-card b { display: block; font-size: 12.5px; color: #E2E8F0; }
.hv-step-card small { display: block; font-size: 10.5px; color: #94A3B8; margin-top: 2px; }
.hv-feature {
  animation: hvIn .5s cubic-bezier(.2,.8,.2,1) both;
  display: flex; gap: 10px; align-items: flex-start;
  border: 1px solid rgba(148,163,184,.16); border-radius: 12px;
  background: rgba(15,23,42,.55); padding: 10px 12px; transition: transform .2s, border-color .2s;
}
.hv-feature:hover { transform: translateY(-2px); border-color: rgba(52,211,153,.45); }
.hv-feature-icon {
  flex: 0 0 26px; height: 26px; border-radius: 8px; display: flex; align-items: center; justify-content: center;
  background: rgba(96,165,250,.12); color: #60A5FA; font-size: 13px; font-weight: 800;
}
.hv-feature b { display: block; font-size: 12px; color: #E2E8F0; }
.hv-feature small { display: block; font-size: 10.5px; color: #94A3B8; margin-top: 2px; line-height: 1.35; }
.hv-footer-band {
  animation: hvIn .6s cubic-bezier(.2,.8,.2,1) both;
  border: 1px solid rgba(96,165,250,.22); border-radius: 16px;
  background: linear-gradient(100deg, rgba(15,23,42,.9), rgba(30,58,95,.55), rgba(15,23,42,.9));
  padding: 14px 18px; margin-top: 18px;
}
.hv-footer-items { display: flex; flex-wrap: wrap; gap: 18px 30px; justify-content: space-around; }
.hv-footer-item { text-align: center; color: #CBD5E1; font-size: 12px; font-weight: 700; }
.hv-footer-item span { display: block; color: #60A5FA; font-size: 17px; margin-bottom: 2px; }
.hv-footer-note { text-align: center; color: #64748B; font-size: 11px; margin-top: 10px; }
.hv-money-field { position: relative; overflow: hidden; }
.hv-footer-band { position: relative; overflow: hidden; }
.hv-footer-items, .hv-footer-note { position: relative; z-index: 2; }
.hv-coin {
  position: absolute; display: flex; align-items: center; justify-content: center;
  width: 54px; height: 54px; border-radius: 50%; font-weight: 800; font-size: 22px;
  color: #34D399; border: 2px solid rgba(52,211,153,.5);
  background: radial-gradient(circle at 35% 30%, rgba(52,211,153,.30), rgba(16,185,129,.05));
  box-shadow: 0 0 22px rgba(52,211,153,.16), inset 0 0 12px rgba(52,211,153,.12);
  opacity: .55; animation: hvCoinFloat 6s ease-in-out infinite;
}
.hv-banknote {
  position: absolute; display: flex; align-items: center; justify-content: center;
  width: 96px; height: 54px; border-radius: 10px; font-weight: 800; font-size: 25px;
  color: #93C5FD; border: 1px solid rgba(96,165,250,.45);
  background: linear-gradient(135deg, rgba(96,165,250,.20), rgba(52,211,153,.12));
  box-shadow: 0 0 22px rgba(96,165,250,.12);
  opacity: .45; animation: hvNoteFloat 8s ease-in-out infinite;
}
.hv-banknote::before, .hv-banknote::after {
  content: ""; position: absolute; left: 10px; right: 10px; height: 2px;
  background: rgba(148,163,184,.28); border-radius: 2px;
}
.hv-banknote::before { top: 9px; }
.hv-banknote::after { bottom: 9px; }
.hv-hero .hv-coin { opacity: .4; animation-delay: .8s; }
.hv-hero .hv-banknote { opacity: .3; animation-delay: 1.6s; }
@media (max-width: 900px) { .hv-stats { grid-template-columns: repeat(2,1fr); } }
@media (prefers-reduced-motion: reduce) {
  .hv-hero, .hv-stat, .hv-orb, .hv-orb::after, .hv-dot::after, .hv-shine,
  .hv-candle, .hv-ema, .hv-praise-item, .hv-step-card, .hv-feature, .hv-footer-band,
  .hv-coin, .hv-banknote { animation: none !important; }
  .hv-ema { stroke-dashoffset: 0; }
}
</style>
"""


def inject_visual_css() -> None:
    """Görsel katmanın CSS'ini enjekte eder (her sayfada güvenle çağrılabilir)."""
    st.html(CSS)


def market_chart_card() -> None:
    """Gerçek BIST 100 verisiyle animasyonlu mum grafiği."""
    from ui.real_chart import render

    render()


def praise_block() -> None:
    """Ürünün güçlü yönlerini dürüst ve sakin bir dille anlatır."""
    st.html(
        """
<div class="hv-praise">
  <div class="hv-praise-head">Neden HSC Borsa Analiz?</div>
  <div class="hv-praise-item"><span>✦</span><div><b>Derin analiz, sade karar.</b><small>9 zaman dilimi ve KAP verisi tek bir kartta özetlenir.</small></div></div>
  <div class="hv-praise-item"><span>✦</span><div><b>Rakamları saklamaz.</b><small>Kaybeden sinyaller de dahil şeffaf performans defteri tutar.</small></div></div>
  <div class="hv-praise-item"><span>✦</span><div><b>Risk önce, kâr sonra.</b><small>ATR stop, rejim ve Kelly boyutuyla disiplinli plan sunar.</small></div></div>
  <div class="hv-praise-item"><span>✦</span><div><b>Karar yine sizde.</b><small>Gerçek emir gönderilmez; yalnızca kurgusal işlem yapılır.</small></div></div>
</div>
"""
    )


def brand_panel() -> None:
    """Giriş ekranının solunda marka/istatistik paneli."""
    st.html(
        """
<div class="hv-hero">
  <div class="hv-orb"></div>
  <div class="hv-banknote" style="right:170px;top:64px">₺</div>
  <div class="hv-coin" style="right:58px;bottom:30px">₺</div>
  <div class="hv-tag">HSC · BIST ANALİZ</div>
  <div class="hv-title">Veriyle karar ver.<br/>Disiplinle yönet.</div>
  <p class="hv-desc">Gerçek BIST verisi, 9 zaman dilimi uyumu, şeffaf performans defteri ve risk odaklı karar desteği — tek panelde.</p>
  <div class="hv-shine"></div>
</div>
"""
    )
    market_chart_card()
    stat_strip()
    praise_block()
    st.html('<div class="hv-live" style="margin:2px 0 8px"><span class="hv-dot"></span> Kurgusal işlem sistemi hazır · gerçek emir gönderilmez</div>')
    trust_row()


def stat_strip() -> None:
    """Dört animasyonlu istatistik kartı."""
    st.html(
        """
<div class="hv-stats">
  <div class="hv-stat"><div class="hv-num">804</div><div class="hv-lbl">BIST hissesi taranır</div></div>
  <div class="hv-stat"><div class="hv-num">16</div><div class="hv-lbl">analiz aracı</div></div>
  <div class="hv-stat"><div class="hv-num">1<small> dk</small></div><div class="hv-lbl">canlı mum verisi</div></div>
  <div class="hv-stat"><div class="hv-num">0</div><div class="hv-lbl">gerçek emir gönderimi</div></div>
</div>
"""
    )


def trust_row() -> None:
    """Fintech güven sinyalleri (Material ikonlu rozetler)."""
    st.caption("Güven ve analiz")
    with st.container(horizontal=True):
        st.badge("Şifre korumalı", icon=":material/lock:", color="green")
        st.badge("Canlı veri", icon=":material/sensors:", color="blue")
        st.badge("Rejim analizi", icon=":material/psychology:", color="violet")
        st.badge("Paper-only", icon=":material/security:", color="orange")


def login_feature_panel() -> None:
    """Formun altındaki boşluğu adım rehberi ve özellik kartlarıyla doldurur."""
    st.container(height=1, border=False)
    st.markdown("**3 adımda başlayın**")
    c1, c2, c3 = st.columns(3, gap="small")
    steps = [
        ("1", "Kayıt ol", "Güvenli giriş oluştur"),
        ("2", "Hisse seç", "804 şirket arasından"),
        ("3", "Kararı gör", "Tek net sinyal kartı"),
    ]
    for col, (no, title, desc) in zip((c1, c2, c3), steps):
        with col:
            st.html(
                f'<div class="hv-step-card"><div class="hv-step-no">{no}</div>'
                f'<b>{title}</b><small>{desc}</small></div>'
            )

    st.container(height=1, border=False)
    st.markdown("**Panelde neler var?**")
    features = [
        ("⚡", "Anlık sinyal", "1 dk mumlarla AL/SAT tetikleyici"),
        ("◈", "İşlem ajansı", "Tam plan: giriş, stop, hedef, boyut"),
        ("▤", "BIST tarayıcı", "804 hissesi saniyeler içinde taranır"),
        ("◎", "Risk merkezi", "Rejim, Kelly, Monte Carlo, VaR"),
        ("✦", "Performans defteri", "R çarpanıyla şeffaf sonuç kaydı"),
        ("✉", "Bildirimler", "Karar değişince ntfy / Telegram / e-posta"),
    ]
    for i in range(0, len(features), 2):
        left, right = st.columns(2, gap="small")
        for col, (symbol, title, desc) in zip((left, right), features[i:i + 2]):
            with col:
                st.html(
                    f'<div class="hv-feature"><div class="hv-feature-icon">{symbol}</div>'
                    f'<div><b>{title}</b><small>{desc}</small></div></div>'
                )


def auth_footer() -> None:
    """Giriş sayfasının altındaki geniş şeffaflık şeridi."""
    st.html(
        """
<div class="hv-footer-band hv-money-field">
  <div class="hv-coin" style="left:24px;top:6px">₺</div>
  <div class="hv-banknote" style="right:120px;top:0">₺</div>
  <div class="hv-coin" style="right:26px;bottom:8px;width:42px;height:42px;font-size:17px">₺</div>
  <div class="hv-footer-items">
    <div class="hv-footer-item"><span>◈</span>Gerçek BIST verisi</div>
    <div class="hv-footer-item"><span>◎</span>İstatistiksel doğrulama</div>
    <div class="hv-footer-item"><span>⚖</span>Risk odaklı plan</div>
    <div class="hv-footer-item"><span>✦</span>Şeffaf sonuç defteri</div>
    <div class="hv-footer-item"><span>⚡</span>Gerçek emir yok</div>
  </div>
  <div class="hv-footer-note">Yatırım tavsiyesi değildir · Geçmiş performans gelecek getiriyi garanti etmez · Tüm işlemler kurgusaldır</div>
</div>
"""
    )
