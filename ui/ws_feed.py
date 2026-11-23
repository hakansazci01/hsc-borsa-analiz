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
WS_DEPTH = "wss://stream-cloud.binance.tr/ws/{sym}@depth5@100ms"  # OBI için L2
RECONNECT_SEC = 5
MAX_RETRIES = 3
STATE = auth.USERS_DIR / "ws_state.json"

_thread: threading.Thread | None = None
_stop = threading.Event()
_market_stop = threading.Event()  # market WS yeniden başlatma — user stream'i etkilemez


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


def _market_halted() -> bool:
    return _stop.is_set() or _market_stop.is_set()


def _mini_ticker_loop() -> None:
    """Anlık fiyatları WS'ten al, REST polling'i yedekte bırak."""
    import websocket

    from ui import tr_scalper as t

    retries = 0
    while not _market_halted():
        try:
            ws = websocket.create_connection(WS_MARKET, timeout=10)
            ws.settimeout(15)
            if retries:
                log("WS yeniden bağlandı — canlı fiyat WebSocket'ten geliyor")
            else:
                log("WS BAĞLANDI — canlı fiyat WebSocket'ten geliyor (REST yedek)")
            retries = 0
            while not _market_halted():
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


def handle_user_message(msg: dict[str, Any]) -> str | None:
    """ExecutionReport eventini loglar — test edilebilir tek nokta.

    Binance TR WS API user data event'leri sarılmış gelir:
        {"subscriptionId": 0, "event": {"e": "executionReport", ...}}
    Eski/çıplak format da desteklenir: {"e": "executionReport", ...}
    """
    if not isinstance(msg, dict):
        return None
    ev = msg.get("event") if isinstance(msg.get("event"), dict) else msg
    if not isinstance(ev, dict) or ev.get("e") != "executionReport":
        return None
    status = str(ev.get("X") or "")
    st = _load()
    st.update(last_user_event=status, user_at=time.time(),
              at=time.strftime("%Y-%m-%d %H:%M:%S"))
    _save(st)
    log(f"WS ExecutionReport: {status} · orderId={ev.get('i')} "
        f"· filled={ev.get('z')}/{ev.get('q')}")
    return status


def _get_user_token() -> tuple[str | None, float]:
    """POST /open/v1/user-listen-token → (token, expirationTime ms)."""
    from ui import tr_scalper as t

    ok, data = t._request("/open/v1/user-listen-token", signed=True, method="POST")
    body = ((data or {}).get("data") or {}) if isinstance(data, dict) else {}
    token = body.get("token") or body.get("listenToken")  # TR API 'token' döndürür
    expires = float(body.get("expirationTime", 0) or 0)
    return (token if ok else None), expires


def _subscribe_message(token: str) -> dict[str, Any]:
    """Binance TR docs: userDataStream.subscribe.listenToken + params.listenToken."""
    import uuid

    return {
        "id": uuid.uuid4().hex,
        "method": "userDataStream.subscribe.listenToken",
        "params": {"listenToken": token},
    }


def _subscribe_response_ok(resp: dict[str, Any]) -> tuple[bool, float]:
    """Subscribe yanıtını doğrula → (ok, subscription expiration ms).

    Kabul edilen iki docs formatı:
      {"subscriptionId": 1, "expirationTime": 1749094553955907}
      {"id":"...", "status": 200, "result": {"subscriptionId": 0}}
    """
    if not isinstance(resp, dict):
        return False, 0.0
    result = resp.get("result") if isinstance(resp.get("result"), dict) else {}
    sub_id = resp.get("subscriptionId", result.get("subscriptionId"))
    exp = float(resp.get("expirationTime") or result.get("expirationTime") or 0)
    error = resp.get("error")
    code = resp.get("code")
    status = resp.get("status")
    if isinstance(error, dict) or (code is not None and code not in (0, 200)):
        return False, 0.0
    if status is not None and status != 200:
        return False, 0.0
    if status == 200 or sub_id is not None:
        return True, exp
    return False, 0.0


def _subscribe_user(ws: Any, token: str) -> tuple[bool, float]:
    """Docs formatında subscribe gönder, yanıtını oku ve doğrula."""
    from websocket import WebSocketTimeoutException

    req = _subscribe_message(token)
    ws.send(json.dumps(req))
    end = time.time() + 10
    while time.time() < end:
        try:
            raw = ws.recv()
        except WebSocketTimeoutException:
            continue
        try:
            resp = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(resp, dict):
            continue
        # Subscribe cevabından önce gelebilen eventleri kaçırma
        if "e" in resp or "event" in resp:
            handle_user_message(resp)
            continue
        # Başka bir isteğe ait cevapsa atla
        if resp.get("id") and str(resp["id"]) != str(req["id"]):
            continue
        ok, exp = _subscribe_response_ok(resp)
        if ok:
            return True, exp
        log(f"WS user subscribe reddedildi: {str(resp)[:180]}")
        return False, 0.0
    return False, 0.0


def _user_heartbeat(stop_evt: threading.Event) -> None:
    """Bağlantı açıkken her 60 sn kanıt logu — recv bloklansa bile çalışır."""
    while not stop_evt.wait(60):
        log("WS user data BAĞLI, 60 sn")


def _user_stream_loop() -> None:
    """ExecutionReport push — docs: userDataStream.subscribe.listenToken."""
    import websocket
    from websocket import WebSocketTimeoutException

    while not _stop.is_set():
        token, expires = _get_user_token()
        if not token:
            _stop.wait(30)
            continue
        for _attempt in range(1, MAX_RETRIES + 1):
            if _stop.is_set():
                break
            ws = None
            beat = None
            try:
                ws = websocket.create_connection(WS_USER, timeout=10)
                ws.settimeout(20)
                ok, sub_exp = _subscribe_user(ws, token)
                if not ok:
                    raise RuntimeError("subscribe yanıtı doğrulanamadı")
                if sub_exp:
                    expires = sub_exp
                log("WS user data BAĞLANDI — ExecutionReport push aktif")
                beat = threading.Event()
                threading.Thread(target=_user_heartbeat, args=(beat,), daemon=True,
                                 name="hsc-ws-user-beat").start()
                while not _stop.is_set():
                    # Token 24 sn, otomatik yenilenmez — 30 dk kala yeni token + subscribe
                    if expires and time.time() * 1000 > expires - 30 * 60 * 1000:
                        new_token, new_exp = _get_user_token()
                        if new_token:
                            renewed, _ = _subscribe_user(ws, new_token)
                            if renewed:
                                token, expires = new_token, new_exp or expires
                                log("WS user stream yeni token ile yeniden abone oldu")
                        continue
                    try:
                        raw = ws.recv()
                    except WebSocketTimeoutException:
                        # docs: ~20 sn ping/pong — sessizlikte ping gönder, koparma
                        try:
                            ws.ping()
                        except Exception:
                            raise
                        raw = None
                    if raw is not None:
                        try:
                            msg = json.loads(raw)
                        except (ValueError, json.JSONDecodeError):
                            msg = None
                        if msg is not None:
                            handle_user_message(msg)
                break
            except Exception as exc:
                log(f"WS user stream koptu, yeniden bağlanılıyor "
                    f"({type(exc).__name__}) — clientId + REST sorgu yedekte")
                _stop.wait(RECONNECT_SEC)  # 5 sn bekle, 3 kez dene
            finally:
                if beat is not None:
                    beat.set()
                try:
                    if ws:
                        ws.close()
                except Exception:
                    pass
        else:
            log("WS user stream 3 denemede bağlanamadı — clientId + REST yedekte, "
                "bot çalışmaya devam ediyor")
        if not _stop.is_set():
            _stop.wait(30)


def _depth_loop() -> None:
    """depth5@100ms — OBI (alis/satis hacmi) icin anlik L2. REST yedek kalir."""
    import websocket

    from ui import micro_engine as me

    symbols = ["BTC_TRY", "XLM_TRY", "SHIB_TRY"]
    while not _stop.is_set():
        for sym in symbols:
            if _stop.is_set():
                break
            ws = None
            try:
                plain = sym.replace("_", "").lower()
                ws = websocket.create_connection(WS_DEPTH.format(sym=plain), timeout=10)
                ws.settimeout(20)
                last_write = 0.0
                while not _stop.is_set():
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    try:
                        d = json.loads(raw)
                    except (ValueError, json.JSONDecodeError):
                        continue
                    if not isinstance(d, dict):
                        continue
                    if time.time() - last_write < 1.0:
                        continue
                    obi = me.obi_ratio(d.get("bids") or [], d.get("asks") or [])
                    st = _load()
                    depth = st.get("depth_obi", {}) if isinstance(st.get("depth_obi"), dict) else {}
                    # Binance partial depth5@100ms sunucu zamanı 'T' taşır —
                    # sinyal yaşını ölçüp 2 sn üzeri OBI'ları reddediyoruz.
                    srv_ms = d.get("T")
                    age_ms = (int(time.time() * 1000 - float(srv_ms))
                              if srv_ms else None)
                    bids = d.get("bids") or []
                    asks = d.get("asks") or []
                    best_bid = float(bids[0][0]) if bids else 0.0
                    best_ask = float(asks[0][0]) if asks else 0.0
                    depth[sym] = {"ratio": obi["ratio"], "ok": obi["ok"],
                                  "best_bid": best_bid, "best_ask": best_ask,
                                  "age_ms": age_ms,
                                  "at": time.strftime("%Y-%m-%d %H:%M:%S")}
                    st["depth_obi"] = depth
                    _save(st)
                    last_write = time.time()
                try:
                    ws.close()
                except Exception:
                    pass
            except Exception:
                try:
                    if ws:
                        ws.close()
                except Exception:
                    pass
                _stop.wait(RECONNECT_SEC)
        _stop.wait(RECONNECT_SEC)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _market_stop.clear()
    _thread = threading.Thread(target=_mini_ticker_loop, name="hsc-ws-market", daemon=True)
    _thread.start()
    threading.Thread(target=_user_stream_loop, name="hsc-ws-user", daemon=True).start()
    threading.Thread(target=_depth_loop, name="hsc-ws-depth", daemon=True).start()


def health_check() -> bool:
    """Watchdog'dan çağrılır — 120 sn sessizse WS'i yeniden başlat.

    Dönen değer: yeniden bağlatma yapıldıysa True.
    """
    global _thread
    s = status()
    if s["connected"]:
        return False
    if not (s["connected"] is False):
        return False
    age = s.get("age")
    if age is not None and age < 120:
        return False
    # Sadece market döngüsünü yeniden başlat — user stream'i koparma
    log(f"WS sessiz ({age} sn) — yeniden bağlanılıyor")
    _market_stop.set()
    time.sleep(1)
    _market_stop.clear()
    _thread = threading.Thread(target=_mini_ticker_loop, name="hsc-ws-market", daemon=True)
    _thread.start()
    return True
