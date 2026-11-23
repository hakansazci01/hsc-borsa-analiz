"""HIZLI MAKER ALTERNATİFİ — BTC/ETH, post-only, BNB indirimli komisyon.

Mevcut sistemi BOZMAZ: ayrı state, ayrı emirler, sadece 2 likit coin.
  - Tur: 8 sn (WS fiyat + depth5, REST'e sormaz)
  - Giriş: spread <%0.10 ve OBI dengeli → en iyi bid'e POST-ONLY alış
  - 5 sn dolmazsa iptal, yeni fiyata koy
  - Dolarsa +%0.40 satış limiti (komisyon %0.15 sonrası ~%0.25 net)
  - Envanter max 15 dk → market çıkış
  - Korunanlar: hard stop, TP kilidi, R/R, net TL eşiği, SMA200, CUSUM, stale
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth, tr_scalper as t

STATE = auth.USERS_DIR / "fast_maker.json"
SYMBOLS = ("BTC_TRY", "ETH_TRY")
CYCLE_SEC = 8
QUOTE_TTL_SEC = 5
INVENTORY_MAX_SEC = 900
SPREAD_MAX_PCT = 0.10
MAKER_FEE_PCT = 0.10
BNB_MAKER_FEE_PCT = 0.075
ROUND_TRIP_BNB = 0.15
TARGET_PCT = 0.004
MIN_NET_TRY = 0.15


def _log(msg: str) -> None:
    try:
        from ui import autonomous_ops
        autonomous_ops._log(msg)
    except Exception:
        pass


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def fee_info() -> dict[str, Any]:
    bnb = float(t.asset_balance("BNB") or 0)
    if bnb > 0:
        return {"round_trip_pct": ROUND_TRIP_BNB, "bnb": True,
                "msg": f"KOMİSYON: maker+BNB %{ROUND_TRIP_BNB:.2f} (BNB {bnb:.4f})"}
    return {"round_trip_pct": MAKER_FEE_PCT * 2, "bnb": False,
            "msg": f"KOMİSYON: maker %{MAKER_FEE_PCT*2:.2f} (BNB yok — indirim yok)"}


def depth(symbol: str) -> dict[str, Any]:
    from ui import ws_feed
    return ((ws_feed._load().get("depth_obi") or {}).get(symbol) or {})


def ws_price(symbol: str) -> float:
    from ui import ws_feed
    st = ws_feed._load()
    prices = st.get("prices") or {}
    # miniTicker@arr TRY sembollerini XLM_TRY gibi key'ler
    px = prices.get(symbol) or 0.0
    if px <= 0:
        px = float(t.price(symbol) or 0)
    return float(px)


def preflight(symbol: str, cap_try: float) -> tuple[bool, str]:
    from ui import safety_guards as sg, tp_proof, tiered_brakes as tb, risk_brakes as rb

    if t._load().get("position") or (t._load().get("positions") or []):
        return False, "TP kilidi: aktif pozisyon var — yeni emir yok"
    if not sg.buy_allowed()[0]:
        return False, "CUSUM alım freni"
    if not sg.stale_check()[0]:
        return False, "stale veri"
    br = rb.status()
    if br.get("daily_breached") or br.get("dd_breached"):
        return False, "günlük/drawdown freni"
    if tb.status(0)["tier"] >= 2:
        return False, "kademeli fren"
    # Günlük SMA200 trend kapısı
    try:
        k = t.klines(symbol, "1d", 210)
        s200 = float(k["Close"].rolling(200).mean().iloc[-1])
        px = ws_price(symbol)
        if px <= s200:
            return False, f"SMA200 altı ({px:.8f} ≤ {s200:.8f})"
    except Exception:
        return False, "SMA200 verisi yok"
    # OBI ≤2 sn tazelik
    d = depth(symbol)
    if not d:
        return False, "depth verisi yok"
    age = d.get("age_ms")
    if not isinstance(age, (int, float)) or float(age) > 2000:
        return False, "OBI depth verisi bayat (>2 sn)"
    # R/R kapısı (5 sn TTL ≈ 0.2% risk kabulü)
    from ui import risk_reward as rr
    rrv = rr.check(0.2, tp=TARGET_PCT * 100, fee=fee_info()["round_trip_pct"])
    if not rrv["ok"]:
        return False, f"R/R: {rrv['msg']}"
    fee = fee_info()["round_trip_pct"]
    net = cap_try * (TARGET_PCT * 100 - fee) / 100
    if net < MIN_NET_TRY:
        return False, f"net kâr {net:.3f} TL < {MIN_NET_TRY} TL"
    return True, "preflight OK"


def step() -> list[str]:
    logs: list[str] = []
    fi = fee_info()
    logs.append(fi["msg"])
    st = _load()
    quotes = st.get("quotes", {}) if isinstance(st.get("quotes"), dict) else {}

    # 1) bekleyen emirleri yönet (5 sn TTL)
    for key, q in list(quotes.items()):
        age = time.time() - float(q.get("at", time.time()))
        res = t.order_status(q.get("order_id"))
        body = res.get("data") or {}
        filled = float(body.get("executedQty") or 0)
        if filled > 0:
            # dolum → +%0.40 maker satış
            px = float(body.get("executedPrice") or q.get("price") or 0)
            target = px * (1 + TARGET_PCT)
            sr = t.sell(q["symbol"], filled, "FAST_MAKER TP", price_limit=target,
                        post_only=True)
            sb = ((sr.get("data") or {}).get("data") or {}) if isinstance(sr.get("data"), dict) else {}
            inv = {"symbol": q["symbol"], "qty": filled, "entry": px,
                   "entry_ts": time.time(), "sell_order_id": sb.get("orderId") or sb.get("id")}
            st["inventory"] = inv
            quotes.pop(key, None)
            msg = (f"FAST_MAKER DOLDU ID {q.get('order_id')} · {q['symbol']} {filled} @ {px:.8f} "
                   f"· satış limiti ID {inv['sell_order_id']} @ {target:.8f}")
            _log(msg); logs.append(msg)
        elif age >= QUOTE_TTL_SEC:
            c = t.cancel_order(q.get("order_id"))
            quotes.pop(key, None)
            msg = (f"FAST_MAKER 5 sn iptal ID {q.get('order_id')} · "
                   f"{'OK' if c.get('ok') else 'HATA'} — yeni fiyata koyulacak")
            _log(msg); logs.append(msg)

    # 2) envanter süresi (15 dk)
    inv = st.get("inventory")
    if inv and time.time() - float(inv.get("entry_ts", time.time())) >= INVENTORY_MAX_SEC:
        sr = t.sell(inv["symbol"], float(inv["qty"]), "FAST_MAKER 15 dk envanter çıkışı")
        release = f"FAST_MAKER 15 dk envanter çıkışı · {inv['symbol']} · {'OK' if sr.get('ok') else 'HATA'}"
        _log(release); logs.append(release)
        st["inventory"] = None

    # 3) yeni quote
    if not st.get("inventory") and len(quotes) < 2:
        for sym in SYMBOLS:
            d = depth(sym)
            px = ws_price(sym)
            bid = float(d.get("best_bid") or 0) or px
            ask = float(d.get("best_ask") or 0) or px
            spread = ((ask - bid) / ((ask + bid) / 2) * 100) if ask > bid else 99
            ratio = float(d.get("ratio") or 0)
            obi_value = (ratio - 1) / (ratio + 1) if ratio > 0 else 0.0  # -1..+1
            if px <= 0 or spread > SPREAD_MAX_PCT or abs(obi_value) > 0.5:
                logs.append(f"FAST_MAKER {sym}: spread %{spread:.3f} / OBI {obi_value:+.2f} "
                            f"(bid/ask {ratio:.2f}) — uygun değil")
                continue
            cap = min(t.available_try() * 0.05, 250.0)
            ok, why = preflight(sym, cap)
            if not ok:
                logs.append(f"FAST_MAKER {sym}: {why}")
                continue
            flt = t._filters(sym)
            stepq = flt.get("step") or 0.00000001
            qty = round(int((cap / bid) / stepq + 1e-12) * stepq, 8)
            res = t._order(sym, 0, qty, price_limit=bid, post_only=True)
            _d0 = res.get("data") if isinstance(res, dict) else None
            body = ((_d0.get("data") or {}) if isinstance(_d0.get("data"), dict) else _d0) if isinstance(_d0, dict) else {}
            oid = body.get("orderId") or body.get("id")
            if isinstance(res, dict) and res.get("ok"):
                quotes[sym] = {"order_id": oid, "symbol": sym, "price": bid,
                               "qty": qty, "at": time.time()}
                msg = (f"FAST_MAKER POST-ONLY alış emri atıldı ID {oid} · {sym} {qty} @ {bid:.8f} "
                       f"· spread %{spread:.3f} · {fi['msg']}")
                _log(msg); logs.append(msg)
            else:
                logs.append(f"FAST_MAKER {sym} emir reddedildi: "
                            f"{str(res.get('reason') if isinstance(res, dict) else res)[:100]}")

    st["quotes"] = quotes
    _save(st)
    return logs
