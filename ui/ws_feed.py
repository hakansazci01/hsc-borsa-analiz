"""Binance TR WEBSOCKET — hibrit canlı veri. REST polling yedek kalır.

Doğrulanmış TR endpoint'leri (docs + canlı test 2026-11-22):
  wss://stream-cloud.binance.tr/ws/!miniTicker@arr      -> 30 coin anlık fiyat
  wss://stream-cloud.binance.tr/ws/<sym>@kline_3m/15m   -> 3m / 15m mum
  wss://ws-api.binance.tr:443/ws-api/v3                 -> user data (executionReport)

Koparsa 5 sn bekle, 3 kez dene, olmazsa REST'te kal — bot durmaz.
WS verisi request-weight'e girmez (Binance TR docs).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from ui import auth, autonomous_ops

WS_MARKET = "wss://stream-cloud.binance.tr/ws/!miniTicker@arr"
WS_KLINE = "wss://stream-cloud.binance.tr/ws/{sym}@kline_{tf}"
WS_USER = "wss://ws-api.binance.tr:443/ws-api/v3"
RECONNECT_SEC = 5
MAX_RETRIES = 3
STATE = auth.USERS_DIR / "ws_state.json"

_thread: threading.Thread | None = None
_stop = threading.Event()


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def log(msg: str) -> None:
    autonomous_ops._log(msg)


def status() -> dict[str, Any]:
    st = _load()
    age = int(time.time() - float(st.get("event_at", 0) or 0)) if st.get("event_at") else None
    connected = bool(st.get("connected")) and (age is None or age < 90)
    return {
        "connected": connected,
        "source": "WebSocket BAĞLI" if connected else "REST YEDEK",
        "latency_ms": int(float(st.get("latency_ms", 0) or 0)),
        "age": age,
        "mode": "WS" if connected else "REST",
        "last_event": st.get("last_event", "—"),
        "prices": st.get("prices", {}),
        "at": st.get("at", "—"),
    }


def _mini_ticker_loop() -> None:
    """Anlık fiyatları WS'ten al, REST polling'i yedekte bırak."""
    import websocket

    from ui import tr_scalper as t

    retries = 0
    while not _stop.is_set():
        try:
            ws = websocket.create_connection(WS_MARKET, timeout=10)
            ws.settimeout(15)
            if retries:
                log("WS yeniden bağlandı — canlı fiyat WebSocket'ten geliyor")
            else:
                log("WS BAĞLANDI — canlı fiyat WebSocket'ten geliyor (REST yedek)")
            retries = 0
            while not _stop.is_set():
                raw = ws.recv()
                started = time.time()
                rows = json.loads(raw)
                if not isinstance(rows, list):
                    continue
                prices = {}
                for r in rows:
                    sym = str(r.get("s", ""))
                    if sym.endswith("TRY") and sym[:-3]:
                        prices[f"{sym[:-3]}_TRY"] = float(r.get("c", 0) or 0)
                latency = int((time.time() - started) * 1000)
                st = _load()
                st.update(connected=True, prices=prices, latency_ms=latency,
                          event_at=time.time(), last_event="WS: fiyat güncellendi",
                          at=time.strftime("%Y-%m-%d %H:%M:%S"))
                _save(st)
                # Panelin mevcut canlı fiyat alanı da WS'ten beslenir
                from ui import live_feed
                if prices:
                    first = next(iter(prices.values()))
                    live_feed.update(price=first, connected=True)
            ws.close()
        except Exception as exc:
            if status()["connected"]:
                log(f"WS koptu ({type(exc).__name__}), REST yedeğe geçildi")
            st = _load()
            st.update(connected=False, last_event="WS koptu, REST'e geçildi",
                      at=time.strftime("%Y-%m-%d %H:%M:%S"))
            _save(st)
            retries += 1
            if retries > MAX_RETRIES:
                log("WS 3 denemede bağlanamadı — REST yedekte kalındı, bot çalışmaya devam ediyor")
                retries = 0
            _stop.wait(RECONNECT_SEC)


def _user_stream_loop() -> None:
    """ExecutionReport push — NEW / PARTIAL / FILLED / CANCEL anında loglanır."""
    import websocket

    from ui import tr_scalper as t

    while not _stop.is_set():
        try:
            ok, data = t._request("/open/v1/user-listen-token", signed=True, method="POST")
            token = ((data or {}).get("data") or {}).get("listenToken") if isinstance(data, dict) else None
            if not ok or not token:
                _stop.wait(30)
                continue
            ws = websocket.create_connection(WS_USER, timeout=10)
            ws.settimeout(20)
            ws.send(json.dumps({"method": "SUBSCRIBE", "params": [token], "id": 1}))
            log("WS user data BAĞLANDI — ExecutionReport push aktif")
            while not _stop.is_set():
                msg = json.loads(ws.recv())
                if msg.get("e") == "executionReport":
                    st_status = msg.get("X")
                    st = _load()
                    st.update(last_user_event=st_status, user_at=time.time(),
                              at=time.strftime("%Y-%m-%d %H:%M:%S"))
                    _save(st)
                    log(f"WS ExecutionReport: {st_status} · orderId={msg.get('i')} "
                        f"· filled={msg.get('z')}/{msg.get('q')}")
            ws.close()
        except Exception as exc:
            log(f"WS user stream koptu ({type(exc).__name__}) — clientId + REST sorgu yedekte")
            _stop.wait(RECONNECT_SEC * MAX_RETRIES)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_mini_ticker_loop, name="hsc-ws-market", daemon=True)
    _thread.start()
    threading.Thread(target=_user_stream_loop, name="hsc-ws-user", daemon=True).start()
