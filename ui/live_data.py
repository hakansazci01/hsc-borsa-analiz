"""
Canlı BIST veri katmanı.

borsapy (TradingView / KAP kaynaklı) üzerinden:
- anlık fiyat ve günlük özet (fast_info),
- 5 dakikalık gün içi OHLCV,
- KAP / şirket haberleri,
- 9 zaman diliminde teknik AL/SAT sinyalleri.

Tüm çağrılar kısa TTL ile önbelleğe alınır; böylece otomatik yenileme
gerçekten yeni veri çeker, gereksiz yere her rerun'da ağa çıkılmaz.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st


# BIST'te en çok işlem gören/kullanıcıların ilgisini çeken semboller
BIST_SYMBOLS: dict[str, str] = {
    "THYAO": "Türk Hava Yolları",
    "GARAN": "Garanti BBVA",
    "ISCTR": "Türkiye İş Bankası",
    "AKBNK": "Akbank",
    "YKBNK": "Yapı Kredi",
    "ASELS": "Aselsan",
    "SISE": "Şişecam",
    "BIMAS": "BİM Mağazalar",
    "TUPRS": "Tüpraş",
    "EREGL": "Ereğli Demir Çelik",
    "KCHOL": "Koç Holding",
    "SAHOL": "Sabancı Holding",
    "FROTO": "Ford Otosan",
    "TOASO": "Tofaş",
    "PGSUS": "Pegasus",
    "TCELL": "Turkcell",
    "SASA": "Sasa Polyester",
    "GUBRF": "Gübre Fabrikaları",
    "HEKTS": "Hektaş",
    "ASTOR": "Astor Enerji",
    "EKGYO": "Emlak Konut GYO",
    "HALKB": "Halkbank",
    "VAKBN": "VakıfBank",
    "BIST100": "BIST 100 Endeksi",
}

STRATEGIES: dict[str, dict[str, int]] = {
    "Kısa vadeli": {"1m": 3, "5m": 3, "15m": 2, "30m": 1, "1h": 1},
    "Dengeli": {"5m": 1, "15m": 2, "1h": 2, "4h": 2, "1d": 3},
    "Uzun vadeli": {"4h": 1, "1d": 3, "1W": 3, "1M": 2},
}


def normalize_symbol(symbol: str) -> str:
    """THYAO.IS / thyaro gibi girdileri borsapy sembolüne (THYAO) çevirir."""
    return symbol.strip().upper().removesuffix(".IS")


@st.cache_data(ttl="60s", max_entries=100, show_spinner=False)
def get_live_snapshot(symbol: str) -> dict[str, Any]:
    """Tek sembol için fiyat + haber + teknik sinyal anlık görüntüsü."""
    import borsapy as bp

    from ui.bist_universe import load_companies
    from ui.stream import live_quote

    sym = normalize_symbol(symbol)
    snap: dict[str, Any] = {
        "symbol": sym,
        "name": load_companies().get(sym, BIST_SYMBOLS.get(sym, sym)),
        "fetched_at": datetime.now(),
        "errors": [],
    }
    ticker = bp.Ticker(sym)

    # Önce WebSocket akışından anlık kotasyon (hızlı); yoksa yavaş yedeğe düş
    quote = live_quote(sym)
    if quote and quote.get("price"):
        snap["info"] = {
            "price": quote["price"],
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "volume": quote.get("volume"),
            "market_cap": quote.get("market_cap"),
            "pe_ratio": quote.get("pe_ratio"),
            "bid": quote.get("bid"),
            "ask": quote.get("ask"),
            "session": quote.get("session"),
            "quote_time": quote.get("timestamp"),
            "currency": quote.get("currency", "TRY"),
            "change_pct": quote.get("change_pct"),
        }
        snap["quote_source"] = quote["source"]
    else:
        try:
            fi = ticker.fast_info
            snap["info"] = {
                "price": getattr(fi, "last_price", None),
                "open": getattr(fi, "open", None),
                "high": getattr(fi, "day_high", None),
                "low": getattr(fi, "day_low", None),
                "volume": getattr(fi, "volume", None),
                "market_cap": getattr(fi, "market_cap", None),
                "pe_ratio": getattr(fi, "pe_ratio", None),
                "currency": getattr(fi, "currency", "TRY"),
            }
            if snap["info"].get("open"):
                snap["info"]["change_pct"] = (
                    (snap["info"]["price"] / snap["info"]["open"] - 1) * 100
                    if snap["info"].get("price") else 0.0
                )
            snap["quote_source"] = "borsapy fast_info (yedek)"
        except Exception as exc:
            snap["errors"].append(f"Fiyat: {exc}")

    try:
        snap["intraday"] = ticker.history(period="1d", interval="5m")
    except Exception as exc:
        snap["errors"].append(f"Gün içi veri: {exc}")

    try:
        snap["news"] = ticker.news
    except Exception as exc:
        snap["errors"].append(f"Haber: {exc}")

    try:
        snap["signals"] = ticker.ta_signals_all_timeframes()
    except Exception as exc:
        snap["errors"].append(f"Teknik sinyal: {exc}")

    return snap


@st.cache_data(ttl="120s", max_entries=1, show_spinner=False)
def scan_bist(symbols: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """BIST listesini hızlıca tarar: sembol, şirket, günlük teknik sinyal.

    Not: `fast_info` çağrısı hisse başına ~5 saniye sürdüğü için taramada
    kullanılmaz; sinyal hesaplaması borsapy'nin hızlı teknik motoruyla yapılır.
    Anlık fiyat, ilgili hissenin detay panelinde gösterilir.
    """
    import borsapy as bp
    from ui.bist_universe import load_companies

    universe = load_companies()
    rows: list[tuple[str, ...]] = []
    for raw in symbols:
        sym = normalize_symbol(raw)
        if sym == "BIST100":
            continue
        name = universe.get(sym, BIST_SYMBOLS.get(sym, sym))
        try:
            sig = bp.Ticker(sym).ta_signals(interval="1d").get("summary", {}).get("recommendation", "—")
            rows.append((sym, name, sig))
        except Exception:
            rows.append((sym, name, "VERİ YOK"))
    return tuple(rows)
