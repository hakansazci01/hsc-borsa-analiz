"""
Giriş ekranındaki gerçek BIST 100 mum grafiği.

Veri kaynağı: borsapy Index("XU100").history — gerçek günlük OHLC.
Veri alınamazsa **hiçbir şey gösterilmez**; sahte/örnek veri üretilmez.
"""

from __future__ import annotations

import streamlit as st


@st.cache_data(ttl="30m", show_spinner=False)
def bist100_daily():
    try:
        import borsapy as bp

        frame = bp.Index("XU100").history(period="3mo", interval="1d")
        if frame is None or frame.empty:
            return None
        required = {"Open", "High", "Low", "Close"}
        if not required.issubset(frame.columns):
            return None
        return frame[list(required)].dropna().tail(30)
    except Exception:
        return None


def render() -> None:
    import pandas as pd

    frame = bist100_daily()
    if frame is None or len(frame) < 10:
        st.caption("BIST 100 verisi alınamadı; grafik gösterilmiyor (sahte veri üretilmez).")
        return

    import pandas as _pd

    bars = [
        (float(r.Open), float(r.High), float(r.Low), float(r.Close))
        for r in frame.itertuples()
    ]
    lo = min(b[2] for b in bars)
    hi = max(b[1] for b in bars)
    low_min = lo - max(1.0, lo * 0.002)
    high_max = hi + max(1.0, hi * 0.002)
    span = high_max - low_min or 1
    count = len(bars)
    slot = 330 / count

    def py(value: float) -> float:
        return 132.0 - (value - low_min) / span * 112.0

    parts: list[str] = []
    for i, (o, h, l, c) in enumerate(bars):
        x = 15 + i * slot + slot / 2
        color = "#34D399" if c >= o else "#F87171"
        parts.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{py(h):.1f}" y2="{py(l):.1f}" '
            f'stroke="{color}" stroke-width="1" opacity=".9"/>'
        )
        top, bottom = py(max(o, c)), py(min(o, c))
        parts.append(
            f'<rect class="hv-candle" style="animation-delay:{i * 0.045:.2f}s" '
            f'x="{x - 2.6:.1f}" y="{top:.1f}" width="5.2" height="{max(bottom - top, 2):.1f}" '
            f'fill="{color}" rx="1"/>'
        )

    closes = pd.Series([b[3] for b in bars])
    ema = closes.ewm(span=9, adjust=False).mean().tolist()
    ema_points = " ".join(
        f"{15 + i * slot + slot / 2:.1f},{py(v):.1f}" for i, v in enumerate(ema)
    )
    grid = "".join(
        f'<line x1="8" x2="352" y1="{yy}" y2="{yy}" stroke="#334155" '
        f'stroke-width=".7" stroke-dasharray="3 5"/>'
        for yy in (36, 76, 116)
    )
    first_date = str(frame.index[0])[:10]
    last_date = str(frame.index[-1])[:10]
    svg = (
        f'<svg viewBox="0 0 360 150" width="100%" height="132" role="img" '
        f'aria-label="BIST 100 gercek gunluk mum grafigi {first_date} - {last_date}">{grid}'
        f'<polyline class="hv-ema" points="{ema_points}"/>'
        f'{"".join(parts)}'
        f'<text x="350" y="33" fill="#94A3B8" font-size="9" text-anchor="end">{high_max:,.0f}</text>'
        f'<text x="350" y="119" fill="#94A3B8" font-size="9" text-anchor="end">{low_min:,.0f}</text>'
        "</svg>"
    )
    component = f"""
<html><head><style>
  body {{ margin:0; background:#0f172a; font-family:Inter,Arial,sans-serif; }}
  .hv-chart {{ border:1px solid rgba(96,165,250,.26); border-radius:14px;
    background:rgba(15,23,42,.8); padding:10px 13px 6px; }}
  .hv-chart-head {{ display:flex; justify-content:space-between; align-items:center;
    font-size:12px; font-weight:800; color:#CBD5E1; margin-bottom:3px; }}
  .hv-candle {{ animation:hvCandle .5s cubic-bezier(.2,.8,.2,1) both;
    transform-box:fill-box; transform-origin:center; }}
  .hv-ema {{ fill:none; stroke:#60A5FA; stroke-width:1.7; stroke-dasharray:900;
    stroke-dashoffset:900; animation:hvDraw 2.8s ease forwards; }}
  .hv-axis {{ display:flex; justify-content:space-between; color:#64748B;
    font-size:10px; margin-top:-3px; }}
  @keyframes hvCandle {{ from{{opacity:0;transform:scaleY(.15)}} to{{opacity:1;transform:none}} }}
  @keyframes hvDraw {{ to{{stroke-dashoffset:0}} }}
  @media (prefers-reduced-motion: reduce) {{
    .hv-candle,.hv-ema {{ animation:none }} .hv-ema {{ stroke-dashoffset:0 }}
  }}
</style></head><body>
<div class="hv-chart">
  <div class="hv-chart-head"><span>BIST 100 · gerçek günlük veri</span>
  <span style="font-size:10px;color:#64748B">kaynak: borsapy · {last_date}</span></div>
  {svg}
  <div class="hv-axis"><span>{first_date}</span><span>{last_date}</span></div>
</div></body></html>
"""
    st.components.v1.html(component, height=176, scrolling=False)
