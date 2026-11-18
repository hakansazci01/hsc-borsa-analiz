"""
Canlı BIST fiyat akışı (WebSocket).

borsapy'nin TradingView WebSocket istemcisini uygulama genelinde tek ve
kalıcı bir bağlantı olarak tutar; subscribe edilen hisselerin kotasyonları
arka planda güncellenir. get_quote() ise ~1 ms'de son kotasyonu döndürür.
Bağlantı/akış başarısız olursa None döner; çağıran katman yavaş (fast_info)
yedeğe geçer.

Not: Ücretsiz akış varsayılan olarak ~15 dakika gecikmelidir; seans durumu
kotasyonda ('current_session') belirtilir.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

import streamlit as st

# TradingView heartbeat paketleri (~h~N) borsapy tarafından uyarı olarak
# yazılıyor; akış sağlıklı olduğu için konsol gürültüsünü azaltıyoruz.
logging.getLogger("borsapy.stream").setLevel(logging.ERROR)

from ui.live_data import normalize_symbol


_STREAM_LOCK = threading.Lock()


@st.cache_resource(show_spinner=False)
def get_stream():
    """Uygulama ömrü boyunca yaşayan tek WebSocket bağlantısı.

    Bağlantı hatasını önbelleğe almamak için hata burada yutulur;
    live_quote() sonraki çağrıda yeniden connect() deneyebilir.
    """
    import borsapy as bp

    stream = bp.TradingViewStream()
    try:
        stream.connect(timeout=10)
    except Exception:
        pass
    return stream


def is_stream_alive() -> bool:
    try:
        return bool(get_stream().is_connected)
    except Exception:
        return False


def live_quote(symbol: str, wait: bool = True, timeout: float = 8.0) -> dict[str, Any] | None:
    """Sembol için güncel kotasyonu döndürür; başarısızlıkta None."""
    try:
        stream = get_stream()
        sym = normalize_symbol(symbol)

        # Aynı stream nesnesi tüm oturumlarca paylaşılıyor: bağlantı ve
        # abonelik değişikliklerini kilit içinde yapıyoruz.
        with _STREAM_LOCK:
            if not stream.is_connected:
                try:
                    stream.disconnect()
                except Exception:
                    pass
                try:
                    if not stream.connect(timeout=10):
                        return None
                except Exception:
                    return None
            if sym not in stream.subscribed_symbols:
                stream.subscribe(sym)

        quote = stream.get_quote(sym)
        if quote is None and wait:
            quote = stream.wait_for_quote(sym, timeout=timeout)
        if quote is None:
            return None

        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Istanbul")
        raw = quote.get("_raw", {}) or {}
        updated = quote.get("_updated")
        ts = quote.get("timestamp")
        return {
            "price": quote.get("last"),
            "change": quote.get("change"),
            "change_pct": quote.get("change_percent"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "prev_close": quote.get("prev_close"),
            "volume": quote.get("volume"),
            "bid": quote.get("bid"),
            "ask": quote.get("ask"),
            "bid_size": quote.get("bid_size"),
            "ask_size": quote.get("ask_size"),
            "market_cap": quote.get("market_cap"),
            "pe_ratio": quote.get("pe_ratio"),
            "eps": quote.get("eps"),
            "dividend_yield": quote.get("dividend_yield"),
            "beta": quote.get("beta"),
            "description": quote.get("description"),
            "currency": quote.get("currency", "TRY"),
            "session": raw.get("current_session", "unknown"),
            "timestamp": datetime.fromtimestamp(ts, tz=tz).strftime("%d.%m.%Y %H:%M:%S") if ts else None,
            "updated_at": datetime.fromtimestamp(updated, tz=tz).strftime("%H:%M:%S") if updated else None,
            "source": "TradingView WebSocket (borsapy)",
        }
    except Exception:
        return None
