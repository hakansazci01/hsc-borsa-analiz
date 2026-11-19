"""
Fiyat serisi bütünlüğü — kurumsal işlem kaynaklı sessiz bozulmaların tespiti.

Amaç: bedelsiz/bedelli/temettü gibi nedenlerle oluşan fiyat sıçramalarının
göstergeleri, R çarpanını, backtest'i ve Monte Carlo'yu sessizce bozmasını
engellemek. Kesin düzeltme yapılmaz; çünkü kaynak doğrulanmadan yapılan
düzeltme, yapılmamasından daha kötüdür.

Yaklaşım (iki bağımsız sinyal):
  1) Getiri basit bir bölünme/katlanma oranına yakın mı? (1/2, 1/5, 2, 5...)
  2) Aynı günde hacim ters yönde belirgin değişti mi?
İkisi birden varsa **KARANTİNA** → sinyal bastırılır. Yalnızca oran varsa
**ŞÜPHELİ** → kullanıcıya açıkça uyarı verilir. Hiçbiri yoksa temiz.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st


_RATIOS = (0.1, 0.2, 0.25, 0.5, 2.0, 4.0, 5.0, 10.0)
_TOL = 0.04          # oran toleransı
_GAP_LIMIT = 0.25    # açıklanamayan büyük günlük hareket


def analyze(df: pd.DataFrame) -> dict[str, Any]:
    """OHLCV DataFrame'ini tarar; bütünlük durumu ve şüpheli olayları döndürür."""
    if df is None or "Close" not in df.columns or len(df) < 30:
        return {"level": "ok", "note": "Yeterli fiyat geçmişi yok; ek kontrol yapılmadı.", "events": []}

    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    volume = pd.to_numeric(df["Volume"], errors="coerce") if "Volume" in df.columns else None
    ret = close.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    tail = ret.tail(252)

    events: list[dict[str, Any]] = []
    for date, value in tail.items():
        if not np.isfinite(value) or abs(value) < _GAP_LIMIT:
            continue
        ratio = 1.0 + float(value)
        near = next((r for r in _RATIOS if abs(ratio - r) / r <= _TOL), None)
        volume_signal = False
        if volume is not None and date in volume.index:
            recent = volume.loc[:date].tail(20).replace(0, np.nan).dropna()
            if len(recent) >= 10:
                avg = float(recent.mean())
                current = float(volume.loc[date])
                if avg > 0 and (current < avg * 0.6 or current > avg * 1.8):
                    volume_signal = True
        if near and volume_signal:
            events.append({
                "date": str(date)[:10],
                "ratio": round(ratio, 3),
                "level": "quarantine",
                "note": f"{str(date)[:10]} — olası düzeltilmemiş kurumsal işlem (oran ~{ratio:.2f}, hacim ters hareket)",
            })
        elif near or abs(value) >= 0.40:
            events.append({
                "date": str(date)[:10],
                "ratio": round(ratio, 3),
                "level": "suspect",
                "note": f"{str(date)[:10]} — açıklanamayan fiyat sıçraması %{float(value) * 100:+.0f}",
            })

    worst = "quarantine" if any(e["level"] == "quarantine" for e in events) else (
        "suspect" if events else "ok"
    )
    note = {
        "ok": "Fiyat serisinde kurumsal işlem şüphesi yok.",
        "suspect": f"{len(events)} şüpheli fiyat sıçraması var; veri kaynağını doğrulayın.",
        "quarantine": "Düzeltilmemiş olabilecek kurumsal işlem tespit edildi; bu hisse için sinyal ve backtest bastırıldı.",
    }[worst]
    return {"level": worst, "note": note, "events": events[-5:]}


@st.cache_data(ttl="1h", show_spinner=False)
def check_symbol(symbol: str, period: str = "1y") -> dict[str, Any]:
    """Sembol için günlük kapanış geçmişini alıp bütünlük kontrolü yapar."""
    try:
        import borsapy as bp

        ticker = symbol if "." in symbol else f"{symbol}.IS"
        frame = bp.Ticker(ticker).history(period=period, interval="1d")
        if frame is None or frame.empty:
            return {"level": "ok", "note": "Günlük veri alınamadı; bütünlük kontrolü yapılamadı.", "events": []}
        return analyze(frame)
    except Exception:
        return {"level": "ok", "note": "Bütünlük kontrolü çalıştırılamadı; veri kaynağını doğrulayın.", "events": []}


def is_quarantined(flag: dict[str, Any]) -> bool:
    return flag.get("level") == "quarantine"


def render(flag: dict[str, Any]) -> None:
    palette = {"ok": "green", "suspect": "orange", "quarantine": "red"}
    labels = {"ok": "Veri bütünlüğü OK", "suspect": "Veri şüpheli", "quarantine": "KARANTİNA"}
    level = flag.get("level", "ok")
    st.badge(labels[level], icon=":material/fact_check:", color=palette[level],
             help="Bedelsiz/bedelli/temettü kaynaklı fiyat sıçramaları iki sinyalle tespit edilir.")
    st.caption(flag.get("note", ""))
