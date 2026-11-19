"""
Piyasa genişliği (breadth) — mevcut ücretsiz/gecikmeli tarama verisinden
hesaplanan, yalnızca bağlam sağlayan bir gösterge.

Sinyal üretmez, AL/SAT yönü önermez. Gecikmeli ve kapsamı sınırlı veriyle
"piyasa geniş mi, dar mı?" sorusuna kabaca yanıt verir.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


@st.cache_data(ttl="5m", show_spinner=False)
def compute(limit: int = 800) -> dict[str, Any]:
    try:
        from ui.screener import scan_all

        rows = scan_all("close > 0", limit=limit)
    except Exception:
        return {"ready": False, "note": "Tarama verisi alınamadı; genişlik hesaplanamadı."}
    if not rows:
        return {"ready": False, "note": "Tarama boş döndü; genişlik hesaplanamadı."}

    changes: list[float] = []
    rsi_values: list[float] = []
    for row in rows:
        try:
            change = float(row.get("Değişim %"))
            changes.append(change)
        except (TypeError, ValueError):
            pass
        try:
            rsi_values.append(float(row.get("RSI")))
        except (TypeError, ValueError):
            pass

    if not changes:
        return {"ready": False, "note": "Geçerli değişim verisi yok; genişlik hesaplanamadı."}

    advances = sum(1 for c in changes if c > 0.01)
    declines = sum(1 for c in changes if c < -0.01)
    unchanged = len(changes) - advances - declines
    median = sorted(changes)[len(changes) // 2]
    rsi_bull = sum(1 for r in rsi_values if r > 50)
    coverage = len(changes) / max(limit, 1)

    ready = coverage >= 0.9
    return {
        "ready": ready,
        "universe": len(rows),
        "covered": len(changes),
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "median_change": round(median, 2),
        "rsi_bull_pct": round(rsi_bull / len(rsi_values) * 100, 1) if rsi_values else None,
        "coverage_pct": round(coverage * 100, 1),
        "note": (
            "Genişlik verisi kapsamlı." if ready
            else "Kapsam düşük; genişlik yorumu yapılmıyor."
        ),
    }


def render(flag: dict[str, Any]) -> None:
    if not flag.get("ready"):
        st.caption("⚠ " + flag.get("note", "Genişlik hesaplanamadı."))
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Yükselen", flag["advances"])
    c2.metric("Düşen", flag["declines"])
    c3.metric("Medyan değişim", f"{flag['median_change']:+.2f}%")
    c4.metric("RSI>50", f"%{flag['rsi_bull_pct']}" if flag["rsi_bull_pct"] is not None else "—")
    st.caption(
        f"Tarama kapsamı {flag['covered']}/{flag['universe']} (%{flag['coverage_pct']}) · "
        "gecikmeli veri · yalnızca piyasa bağlamıdır, alım/satım sinyali değildir."
    )
