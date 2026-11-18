"""
BIST evreni: Borsa İstanbul'da kayıtlı tüm şirketleri internetten çeker.

Birincil kaynak: borsapy.companies() (KAP temelli şirket listesi).
İnternet yoksa son başarılı liste yerel JSON önbelleğinden okunur.
Böylece arayüz sabit bir listeyle sınırlı kalmaz; 800+ hissenin tamamı aranabilir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st


CACHE_PATH = Path(__file__).resolve().parent.parent / "results" / "bist_companies.json"

# Arayüzde üstte gösterilen, likiditesi yüksek tanıdık semboller
FEATURED = [
    "THYAO", "GARAN", "ISCTR", "ASELS", "AKBNK", "YKBNK", "SISE", "BIMAS",
    "TUPRS", "EREGL", "KCHOL", "SAHOL", "FROTO", "TOASO", "PGSUS", "TCELL",
    "SASA", "GUBRF", "HEKTS", "ASTOR", "EKGYO", "HALKB", "VAKBN", "BIST100",
]


def _fallback() -> dict[str, str]:
    if CACHE_PATH.exists():
        try:
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                return data
        except (OSError, ValueError):
            pass
    return {s: s for s in FEATURED}


@st.cache_data(ttl="24h", show_spinner=False)
def load_companies() -> dict[str, str]:
    """{ticker: şirket adı} sözlüğünü döndürür (internetten, önbellekli)."""
    try:
        import warnings

        import borsapy as bp

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            df = bp.companies()
        universe: dict[str, str] = {}
        for ticker, name in zip(df["ticker"].astype(str), df["name"].astype(str)):
            ticker = ticker.strip().upper()
            if ticker and ticker not in universe:
                universe[ticker] = name.strip()
        if len(universe) < 50:
            raise ValueError("Şirket listesi beklenenden kısa geldi.")
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(universe, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return universe
    except Exception:
        return _fallback()


def ordered_symbols(universe: dict[str, str]) -> list[str]:
    """Tanıdık semboller önce, gerisi alfabetik."""
    rest = sorted(s for s in universe if s not in FEATURED)
    return [s for s in FEATURED if s in universe] + rest


def search_symbols(universe: dict[str, str], query: str, limit: int = 60) -> list[str]:
    """Sembol veya şirket adına göre hızlı filtreleme."""
    q = query.strip().upper()
    if not q:
        return ordered_symbols(universe)[:limit]
    tr_lower = lambda text: text.replace("I", "ı").replace("İ", "i").lower()
    lowered = tr_lower(query.strip())
    exact = [s for s in universe if s == q]
    starts = [s for s in universe if s.startswith(q) and s != q]
    contains = [
        s for s in universe
        if q in s or lowered in tr_lower(universe[s])
        if s not in exact and s not in starts
    ]
    return (exact + starts + contains)[:limit]


def company_info(universe: dict[str, str], symbol: str) -> dict[str, Any]:
    return {"symbol": symbol, "name": universe.get(symbol, symbol)}
