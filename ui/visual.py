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
@media (max-width: 900px) { .hv-stats { grid-template-columns: repeat(2,1fr); } }
@media (prefers-reduced-motion: reduce) {
  .hv-hero, .hv-stat, .hv-orb, .hv-orb::after, .hv-dot::after, .hv-shine { animation: none !important; }
}
</style>
"""


def inject_visual_css() -> None:
    """Görsel katmanın CSS'ini enjekte eder (her sayfada güvenle çağrılabilir)."""
    st.html(CSS)


def brand_panel() -> None:
    """Giriş ekranının solunda marka/istatistik paneli."""
    st.html(
        """
<div class="hv-hero">
  <div class="hv-orb"></div>
  <div class="hv-tag">HSC · BIST ANALİZ</div>
  <div class="hv-title">Veriyle karar ver.<br/>Disiplinle yönet.</div>
  <p class="hv-desc">Gerçek BIST verisi, 9 zaman dilimi uyumu, şeffaf performans defteri ve risk odaklı karar desteği — tek panelde.</p>
  <div class="hv-shine"></div>
</div>
"""
    )
    stat_strip()
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
