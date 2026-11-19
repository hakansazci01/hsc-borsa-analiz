"""
Birleşik hareket sistemi (motion tokens).

Stripe / Linear / Vercel / Material 3 ilkeleri:
- Varsayılan durum **sakinlik**; hareket bilgi taşıdığında kullanılır
- Micro 120ms, state 200ms, panel 260ms; ease-out giriş, ease-in çıkış
- Yalnızca `transform` ve `opacity` animasyonu (compositor-only)
- 40-90ms stagger ile hiyerarşi; tek "kahraman" an
- `prefers-reduced-motion` her şeyi kapatır; kritik bilgi harekete bağlı değildir

Bu modül yalnızca arayüz katmanıdır; analiz sonuçlarına dokunmaz.
"""

from __future__ import annotations

import streamlit as st


CSS = """
<style>
:root{
  --hsc-dur-micro: 120ms;
  --hsc-dur-state: 200ms;
  --hsc-dur-panel: 260ms;
  --hsc-ease-out: cubic-bezier(.25,1,.5,1);
  --hsc-ease-enter: cubic-bezier(.2,0,0,1);
  --hsc-ease-exit: cubic-bezier(.3,0,1,1);
  --hsc-stagger: 60ms;
  --hsc-lift: -2px;
  --hsc-primary: #60A5FA;
}
@keyframes hscmIn{
  from{ opacity:0; transform:translateY(12px); }
  to  { opacity:1; transform:none; }
}
@keyframes hscmSweep{ to{ transform:translateX(100%); } }
.hscm-card{
  contain: content;
  transition: transform var(--hsc-dur-state) var(--hsc-ease-out),
              border-color var(--hsc-dur-state) var(--hsc-ease-out);
}
.hscm-card:hover{ transform: translateY(var(--hsc-lift)); }
.hscm-stagger > *{
  animation: hscmIn var(--hsc-dur-panel) var(--hsc-ease-out) both;
  animation-delay: calc(var(--i, 0) * var(--hsc-stagger));
}
.hscm-num{ font-variant-numeric: tabular-nums; }
.hscm-skel{
  position: relative; overflow: hidden; border-radius: 8px;
  background: #1b2230; margin: 4px 0;
}
.hscm-skel::after{
  content:""; position:absolute; inset:0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.08), transparent);
  transform: translateX(-100%);
  animation: hscmSweep 1.4s ease-in-out infinite;
  will-change: transform;
}
.hscm-btn button, button{
  transition: transform var(--hsc-dur-micro) var(--hsc-ease-out),
              box-shadow var(--hsc-dur-micro) var(--hsc-ease-out);
}
button:active{ transform: translateY(0); }
:focus-visible{ outline: 2px solid var(--hsc-primary); outline-offset: 2px; }
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{
    animation:none !important; transition:none !important; scroll-behavior:auto !important;
  }
  .hv-ema{ stroke-dashoffset:0 !important; }
  .hv-candle{ opacity:1 !important; transform:none !important; }
  .hscm-skel::after{ animation:none !important; }
}
</style>
"""


def inject_motion_tokens() -> None:
    """Hareket token'larını ve erişilebilirlik korumalarını yükler."""
    st.html(CSS)


def skeleton(height: int = 18, width: str = "100%") -> None:
    """Yer tutan, kaymasız yükleme iskeleti (CSS-only)."""
    st.html(f'<div class="hscm-skel" style="height:{height}px;width:{width}" '
            f'aria-hidden="true" role="presentation"></div>')


def stagger(items: list[str], gap: str = "10px") -> None:
    """Çocukları 60ms aralıklarla sırayla beliren bir satır/kutu oluşturur."""
    children = "".join(
        f'<div style="--i:{i}">{html}</div>' for i, html in enumerate(items)
    )
    st.html(
        f'<div class="hscm-stagger" style="display:grid;gap:{gap}">{children}</div>'
    )
