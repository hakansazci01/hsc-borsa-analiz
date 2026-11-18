"""
Belirgin "trafik lambası" sinyal gösterimi.

Kural (erişilebilirlik): renk tek başına anlam taşımaz; her durum ayrıca
sembol (●/○), ikon ve yazı ile belirtilir. TradingView benzeri oy sayımı,
bantlı gauge ve volatilite bandı birlikte gösterilir.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.help_texts import h


ZONE_LABELS = {
    "AL": ("● AL", "green", ":material/check_circle:"),
    "BEKLE": ("● BEKLE", "orange", ":material/pause_circle:"),
    "SAT": ("● SAT", "red", ":material/cancel:"),
}
INACTIVE_LABELS = {
    "AL": "○ AL", "BEKLE": "○ BEKLE", "SAT": "○ SAT",
}


def gauge_value(decision: dict[str, Any]) -> int:
    """Karar + güveni 0-100 gauge değerine çevirir (kırmızı→yeşil)."""
    conf = float(decision.get("confidence", 0) or 0)
    d = decision.get("decision", "BEKLE")
    if d == "AL":
        return int(70 + conf / 100 * 25)
    if d == "SAT":
        return int(30 - conf / 100 * 25)
    return int(40 + conf / 100 * 20)


def lamp_row(decision: dict[str, Any]) -> None:
    """Üç lambalı, aktif olanı vurgulanan yatay satır."""
    active = decision.get("decision", "BEKLE")
    cols = st.columns(3)
    for col, key in zip(cols, ("AL", "BEKLE", "SAT")):
        with col:
            if key == active:
                label, color, icon = ZONE_LABELS[key]
                st.badge(label, color=color, icon=icon, width="stretch", help=h("signal"))
            else:
                st.badge(INACTIVE_LABELS[key], color="gray", width="stretch", help=h("signal"))


def _gauge(decision: dict[str, Any]) -> None:
    value = gauge_value(decision)
    conf = decision.get("confidence", 0)
    st.echarts_chart(
        {
            "series": [
                {
                    "type": "gauge",
                    "min": 0,
                    "max": 100,
                    "startAngle": 210,
                    "endAngle": -30,
                    "radius": "92%",
                    "center": ["50%", "58%"],
                    "axisLine": {
                        "lineStyle": {
                            "width": 20,
                            "color": [
                                [0.34, "#DC2626"],
                                [0.67, "#FBBF24"],
                                [1, "#34D399"],
                            ],
                        }
                    },
                    "pointer": {
                        "icon": "path://M2.9,0.7L2.9,0.7c1.4,0,2.6,1.2,2.6,2.6l0,67.1c0,1.4-1.2,2.6-2.6,2.6L2.9,73 c-1.4,0-2.6-1.2-2.6-2.6L0.3,3.3C0.3,1.9,1.5,0.7,2.9,0.7z",
                        "length": "62%",
                        "width": 7,
                        "offsetCenter": [0, "5%"],
                        "itemStyle": {"color": "#F8FAFC"},
                    },
                    "anchor": {"show": True, "size": 12, "itemStyle": {"color": "#F8FAFC"}},
                    "axisTick": {"show": False},
                    "splitLine": {"show": False},
                    "axisLabel": {"show": False},
                    "title": {
                        "show": True,
                        "offsetCenter": [0, "72%"],
                        "color": "#94A3B8",
                        "fontSize": 12,
                    },
                    "detail": {
                        "valueAnimation": True,
                        "formatter": "{value}",
                        "fontSize": 34,
                        "fontWeight": "bolder",
                        "color": "#F1F5F9",
                        "offsetCenter": [0, "28%"],
                    },
                    "data": [{"value": value, "name": f"Güven %{conf}"}],
                }
            ]
        },
        height=215,
        alt=f"Sinyal göstergesi: {decision.get('decision')}, güven yüzde {conf}",
    )


def _volatility_band(volatility_pct: float | None) -> dict[str, str]:
    if volatility_pct is None:
        return {"label": "—", "color": "gray", "text": "Oynaklık verisi yok"}
    if volatility_pct < 2:
        return {"label": "Düşük", "color": "green", "text": f"%{volatility_pct:.2f} — sakin"}
    if volatility_pct < 4:
        return {"label": "Orta", "color": "orange", "text": f"%{volatility_pct:.2f} — dikkat"}
    return {"label": "Yüksek", "color": "red", "text": f"%{volatility_pct:.2f} — pozisyon azalt"}


def render_signal_panel(
    decision: dict[str, Any],
    snap: dict[str, Any] | None = None,
    volatility_pct: float | None = None,
) -> None:
    """Trafik lambası + gauge + oy dökümü + doğrulama kontrolü."""
    d = decision.get("decision", "BEKLE")
    conf = decision.get("confidence", 0)

    with st.container(border=True, key="signal_panel"):
        with st.container(horizontal=True, vertical_alignment="bottom"):
            st.markdown("#### Sinyal lambası", help=h("signal"))
        lamp_row(decision)

        left, right = st.columns([1, 1.25], gap="medium")
        with left:
            _gauge(decision)
            st.caption(f"Karar: **{d}** · Güven: **%{conf}** · Skor: **{decision.get('score', 0):+.2f}**")
        with right:
            tech = decision.get("technical", {}) or {}
            buy = int(tech.get("buy_votes", 0) or 0)
            sell = int(tech.get("sell_votes", 0) or 0)
            neutral = int(tech.get("neutral_votes", 0) or 0)
            st.markdown("**Teknik oy dökümü**", help=h("recommendation"))
            st.progress(
                buy / max(buy + sell + neutral, 1),
                text=f"AL oyları: {buy}",
            )
            st.progress(
                sell / max(buy + sell + neutral, 1),
                text=f"SAT oyları: {sell}",
            )
            st.progress(
                neutral / max(buy + sell + neutral, 1),
                text=f"Nötr oylar: {neutral}",
            )

            vol = _volatility_band(volatility_pct)
            st.badge(f"Oynaklık: {vol['label']}", color=vol["color"], help=h("volatility"))
            st.caption(vol["text"])

        checks = [
            ("Trend / zaman dilimleri", "positive" if buy > sell else "negative" if sell > buy else "neutral"),
            ("KAP haberi", "positive" if decision.get("news", {}).get("score", 0) > 0 else "negative" if decision.get("news", {}).get("score", 0) < 0 else "neutral"),
            ("Piyasa rejimi", "negative" if decision.get("regime") in ("Düşüş", "Yüksek oynaklık") else "positive"),
            ("Veri tazeliği", "negative" if (snap or {}).get("info", {}).get("session") not in (None, "regular", "open") else "neutral"),
        ]
        st.markdown("**Onay kontrolleri**", help="Kararı destekleyen veya zayıflatan ana faktörler.")
        for label, tone in checks:
            icon = ":material/check_circle:" if tone == "positive" else ":material/cancel:" if tone == "negative" else ":material/remove:"
            st.markdown(f"- {icon} {label}")

        st.caption("Renk tek başına anlam taşımaz: ● dolu sembol aktif durumu, ○ boş sembol pasif durumu gösterir.")
