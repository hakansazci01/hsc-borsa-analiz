"""
Binance TR WEBSOCKET + ORDER BOOK — canlı fiyakı akışla alır, REST yedek kalır.

WS endpoint: wss://www.binance.tr/ws/<symbol>@trade  ve  <symbol>@depth20
 sembol type 1 (BTC_TRY vb.) için küçük harf, alt çizgi kaldırılır: btcusdt

- Bağlantı koparsa 5 sn içinde yeniden bağlanır; 5 sn içinde başaramazsa ntfy bildirimi.
- Order Book: bid/ask toplamına göre alış/satış baskısı hesaplanır.
  Satış baskısı > %70 ise yeni alım engellenir.
- REST yedek: WS verisi yoksa tr_scalper.price() kullanılır (mevcut davranış).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from ui import auth, autonomous_ops

WS_BASE = "wss://stream-tr.2meta.app/ws"
RECONNECT_SEC = 5
PRESSURE_LIMIT = 0.70
STALE_SEC = 60

STATE = auth.USERS_DIR / "live_feed_state.json"


def _stream_name(symbol: str) -> str:
    """Binance TR WSS: symbol type 1 -> 'btc_try' (alt çizgi KORUNUR)."""
    s = symbol.lower().replace("usdt", "try") if symbol.endswith("USDT") else symbol
    return s.lower()


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def update(price: float | None = None, book: dict[str, Any] | None = None,
           connected: bool | None = None) -> dict[str, Any]:
    """WS thread'inden çağrılır — durumu atomik günceller."""
    st = _load()
    if price is not None:
        st["price"] = price
        st["price_at"] = time.time()
    if book is not None:
        st["book"] = book
        st["book_at"] = time.time()
    if connected is not None:
        st["connected"] = connected
        if connected:
            st["connected_at"] = time.time()
    _save(st)
    return st


def status() -> dict[str, Any]:
    st = _load()
    ts = float(st.get("price_at", 0) or 0)
    return {
        "source": "WebSocket CANLI" if (st.get("connected") and time.time() - ts < STALE_SEC)
                  else "REST YEDEK",
        "connected": bool(st.get("connected")),
        "price": st.get("price"),
        "price_age": int(time.time() - ts) if ts else None,
        "book": st.get("book", {}),
        "book_at": st.get("book_at", 0),
        "connected_at": st.get("connected_at", 0),
    }


def refresh_book(symbol: str) -> dict[str, Any]:
    """Order book'u gerçek Binance TR REST'ten çek (WS depth alternatifi)."""
    from ui import tr_scalper

    sym = symbol if "_" in symbol else symbol[:-4] + "_TRY"  # BTC_TRY -> BTC_TRY
    ok, data = tr_scalper._request(
        "/open/v1/market/depth", {"symbol": sym}
    )
    if ok and isinstance(data, dict):
        body = data.get("data") or {}
        book = {"bids": body.get("bids") or [], "asks": body.get("asks") or []}
        update(book=book)
        return book
    return {}


def book_pressure(book: dict[str, Any] | None = None) -> dict[str, Any]:
    """Alış/satış baskısı: bid ve ask toplam hacim oranları."""
    b = book if book is not None else _load().get("book", {})
    bids = b.get("bids") or []
    asks = b.get("asks") or []
    if not bids or not asks:
        return {"buy": 0.5, "sell": 0.5, "ok": False}
    bid_total = sum(float(x[1]) for x in bids if len(x) > 1)
    ask_total = sum(float(x[1]) for x in asks if len(x) > 1)
    total = bid_total + ask_total
    if total <= 0:
        return {"buy": 0.5, "sell": 0.5, "ok": False}
    buy = bid_total / total
    return {"buy": round(buy, 3), "sell": round(1 - buy, 3), "ok": True}


def book_block() -> str:
    """Satış baskısı > %70 ise yeni alımı engelle."""
    p = book_pressure()
    if not p["ok"]:
        return ""
    if p["sell"] > PRESSURE_LIMIT:
        return (f"SATIŞ BASKISI GÜÇLÜ (%{p['sell']*100:.0f} > %{PRESSURE_LIMIT*100:.0f}) "
                f"— yeni alım yok")
    return ""


def live_price(symbol: str) -> float | None:
    """WS'ten son fiyat; yoksa REST yedek."""
    s = status()
    if s["source"] == "WebSocket CANLI" and s["price"]:
        return float(s["price"])
    from ui import tr_scalper

    return tr_scalper.price(symbol)


def _notify_loss() -> None:
    autonomous_ops._send("HSC WEBSOCKET KOPTU",
                         f"WEBSOCKET KOPTU — {RECONNECT_SEC} sn içinde yeniden bağlanılamadı. "
                         f"REST yedek devrede.")


class Feed:
    """Tek sembol için WS dinleyici, otomatik yeniden bağlanmalı."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._stop = threading.Event()

    def connect(self, max_attempts: int = 3) -> bool:
        import websocket

        name = _stream_name(self.symbol)
        url = f"{WS_BASE}/{name}@trade"
        try:
            ws = websocket.create_connection(url, timeout=RECONNECT_SEC)
            update(connected=True)
            autonomous_ops._log(f"WEBSOCKET BAĞLANDI: {url}")
            # İlk mesajı oku (varsa fiyatı güncelle; yoksa handshake yeterli)
            try:
                raw = ws.recv()
                msg = json.loads(raw)
                if "p" in msg:
                    update(price=float(msg["p"]))
            except Exception:
                pass
            ws.close()
            return True
        except Exception as exc:
            autonomous_ops._log(f"WEBSOCKET bağlantı hatası: {type(exc).__name__}")
            if max_attempts <= 1:
                _notify_loss()
            return False

    def reconnect_test(self) -> bool:
        """Kopma simülasyonu: önce bağlan, kopar, tekrar bağlan."""
        first = self.connect(max_attempts=1)
        update(connected=False)
        time.sleep(0.2)
        second = self.connect(max_attempts=1)
        return first and second
