"""
Çoklu hisse toplu analizi — HIZLI MOD.

Tam analiz (geçmiş veri + KAP + rejim) hisse başına ~5 sn sürüyordu; 12 hisse
sayfayı dakikalarca kilitliyordu. Toplu mod yalnızca:
- WebSocket anlık kotasyon (~0.2 sn)
- borsapy günlük teknik öneri / oy dökümü (~0.3 sn)
kullanır. Böylece 12 hisse ~5 sn içinde sonuç verir. Detaylı analiz tek hisse
üzerinden (bot sohbeti) çalışmaya devam eder.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ui.stream import live_quote


REQUIRED_SESSION = "Seans içinde teyit edin"


@st.cache_data(ttl="60s", max_entries=200, show_spinner=False)
def quick_decision(symbol: str, risk_items: Any) -> dict[str, Any] | None:
    import borsapy as bp

    risk = dict(risk_items)
    try:
        quote = live_quote(symbol) or {}
        tech = bp.Ticker(symbol).ta_signals(interval="1d").get("summary", {}) or {}
        rec = str(tech.get("recommendation", "NEUTRAL")).upper()
        values = {
            "STRONG_BUY": 2, "BUY": 1, "NEUTRAL": 0,
            "SELL": -1, "STRONG_SELL": -2,
        }
        score = values.get(rec, 0)
        buy = int(tech.get("buy", 0) or 0)
        sell = int(tech.get("sell", 0) or 0)
        neutral = int(tech.get("neutral", 0) or 0)
        total = max(buy + sell + neutral, 1)
        consensus = max(buy, sell) / total

        confidence = int(min(95, max(5, round(35 + abs(score) * 18 + consensus * 25))))
        decision = "AL" if score >= 1 else "SAT" if score <= -1 else "BEKLE"
        price = float(quote.get("price") or 0)
        change = float(quote.get("change_pct") or 0)
        stop_pct = float(risk.get("stop_loss_pct", 0.05))
        target_pct = float(risk.get("take_profit_pct", 0.10))
        stop = round(price * (1 - stop_pct), 2) if decision == "AL" else (
            round(price * (1 + stop_pct), 2) if decision == "SAT" else None
        )
        target = round(price * (1 + target_pct), 2) if decision == "AL" else (
            round(price * (1 - target_pct), 2) if decision == "SAT" else None
        )
        reasons = [
            f"Teknik öneri: {rec} (AL {buy} / SAT {sell} / nötr {neutral})",
            f"Anlık kotasyon: {price:,.2f} ₺ ({change:+.2f}%)",
            REQUIRED_SESSION,
        ]
        return {
            "Sembol": symbol.upper(),
            "Karar": decision,
            "Güven": confidence,
            "Skor": round(score, 2),
            "Fiyat": price,
            "Değişim %": round(change, 2),
            "Stop": stop,
            "Hedef": target,
            "Rejim": "hızlı mod",
            "Gerekçe": " | ".join(reasons[:2]),
            "Seans": quote.get("session", "—"),
            "Kaynak": quote.get("source", "WebSocket"),
            "Reasons": reasons,
        }
    except Exception:
        return None


def analyze_batch(
    symbols: list[str],
    settings: dict[str, Any],
    limit: int = 12,
    progress: bool = False,
) -> list[dict[str, Any]]:
    risk_items = tuple(sorted(settings.get("risk", {}).items()))
    results: list[dict[str, Any]] = []
    items = symbols[:limit]
    bar = st.progress(0.0, text="Toplu analiz hazırlanıyor...") if progress else None
    for index, symbol in enumerate(items, 1):
        row = quick_decision(symbol.strip().upper(), risk_items)
        if row:
            results.append(row)
        if bar is not None:
            bar.progress(index / len(items), text=f"{index}/{len(items)} hisse analiz edildi")
    if bar is not None:
        bar.empty()
    return results


def render_batch(results: list[dict[str, Any]]) -> None:
    if not results:
        st.info(
            "Seçilen hisseler için sinyal üretilemedi. Birazdan yeniden deneyin veya tek hisse analizi kullanın.",
            icon=":material/info:",
        )
        return

    order = {"AL": 0, "BEKLE": 1, "SAT": 2}
    results = sorted(results, key=lambda r: (order.get(r["Karar"], 3), -r["Güven"]))

    c1, c2, c3 = st.columns(3)
    c1.metric("Analiz edilen", len(results), icon=":material/analytics:")
    c2.metric("AL sinyali", sum(1 for r in results if r["Karar"] == "AL"), icon=":material/trending_up:")
    c3.metric("SAT sinyali", sum(1 for r in results if r["Karar"] == "SAT"), icon=":material/trending_down:")

    def _karar_color(value: str) -> str:
        colors = {"AL": "#065F46", "BEKLE": "#B45309", "SAT": "#991B1B"}
        return f"background-color: {colors.get(value, '#475569')}; color: white; font-weight: 600;"

    table = pd.DataFrame([{k: v for k, v in r.items() if k != "Reasons"} for r in results])
    st.dataframe(
        table.style.map(_karar_color, subset=["Karar"]),
        hide_index=True,
        column_config={
            "Fiyat": st.column_config.NumberColumn("Fiyat", format="%.2f"),
            "Değişim %": st.column_config.NumberColumn("Değişim %", format="%+.2f"),
            "Güven": st.column_config.ProgressColumn("Güven", min_value=0, max_value=100, format="%d"),
            "Skor": st.column_config.NumberColumn("Skor", format="%+.2f"),
            "Gerekçe": st.column_config.TextColumn("Gerekçe", width="large"),
        },
        alt="Seçilen hisselerin toplu AL BEKLE SAT kararları",
    )

    with st.expander("Hisse hisse gerekçeler", icon=":material/help:"):
        for r in results:
            st.markdown(f"### {r['Sembol']} — {r['Karar']} (güven %{r['Güven']})")
            st.caption(
                f"Fiyat {r['Fiyat']:,.2f} · değişim %{r['Değişim %']:+.2f} · "
                f"skor {r['Skor']:+.2f} · seans {r['Seans']}"
            )
            for reason in r.get("Reasons", []):
                st.markdown(f"- {reason}")


def batch_text(results: list[dict[str, Any]]) -> str:
    lines = [f"**{len(results)} hisse analiz edildi (hızlı sinyal modu):**", ""]
    for r in results:
        lines.append(
            f"- **{r['Sembol']}**: {r['Karar']} · güven %{r['Güven']} · "
            f"fiyat {r['Fiyat']:,.2f} ({r['Değişim %']:+.2f}%)"
        )
    lines += ["", "Detaylı gerekçeler toplu analiz panelinde. Seans içinde fiyatı teyit edin."]
    return "\n".join(lines)
