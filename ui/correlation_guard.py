"""
CORRELATION PROTECTION — aynı anda yüksek korelasyonlu 2 coin'e girilmez.

Kural: son 30 günün günlük kapanışları arasında Pearson korelasyonu > 0.85 ise
ikinci alım engellenir. Örn: BTC açıkken ETH alınmaz.

Veri: gerçek Binance TR günlük mumları (quant_lab.fetch). Hiçbir şey uydurulmaz.
"""

from __future__ import annotations

from typing import Any

from ui import quant_lab

CORR_LIMIT = 0.85
CORR_DAYS = 30


def daily_closes(symbol: str, days: int = CORR_DAYS):
    f = quant_lab.fetch(symbol, "1d", days + 5)
    if f is None or len(f) < 10:
        return None
    return f["Close"].tail(days).reset_index(drop=True)


def correlation(a: str, b: str) -> float | None:
    """İki coin'in son 30 günlük kapanış korelasyonu (-1..1)."""
    ca, cb = daily_closes(a), daily_closes(b)
    if ca is None or cb is None:
        return None
    n = min(len(ca), len(cb))
    if n < 10:
        return None
    va, vb = ca.tail(n).pct_change().dropna(), cb.tail(n).pct_change().dropna()
    if len(va) < 8:
        return None
    c = va.corr(vb)
    return None if c != c else float(c)  # NaN -> None


def guard_entry(open_symbol: str | None, new_symbol: str) -> dict[str, Any]:
    """Açık pozisyon varken yeni alımı korelasyona göre kontrol et."""
    if not open_symbol or open_symbol == new_symbol:
        return {"allowed": True, "corr": None, "reason": "aynı coin veya pozisyon yok"}
    c = correlation(open_symbol, new_symbol)
    if c is None:
        return {"allowed": True, "corr": None, "reason": "korelasyon verisi yok — izin"}
    if c > CORR_LIMIT:
        return {"allowed": False, "corr": round(c, 2),
                "reason": f"KORELASYON YÜKSEK, ALIM ENGELLENDİ ({open_symbol}-{new_symbol} = {c:.2f} > {CORR_LIMIT})"}
    return {"allowed": True, "corr": round(c, 2),
            "reason": f"korelasyon {c:.2f} ≤ {CORR_LIMIT} — izin"}


def matrix(symbols: tuple[str, ...]) -> list[list[Any]]:
    """Küçük korelasyon matrisi (panel için)."""
    out: list[list[Any]] = []
    for a in symbols:
        row: list[Any] = [a]
        for b in symbols:
            if a == b:
                row.append(1.0)
            else:
                c = correlation(a, b)
                row.append(round(c, 2) if c is not None else "—")
        out.append(row)
    return out
