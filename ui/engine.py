"""TEK KARAR MOTORU — 4 motoru birleştirir, sırayla kontrol eder, emri ATAR.

Karar sırası:
  1) Kademeli fren (%6 DD → hiç alma)
  2) Komisyon net kontrolü (net ≤ 0 → alma)
  3) Max 5 pozisyon + aynı coin'de çift motor engeli
  4) Sinyal sırası: CRASH_BID → OBI_VWAP → MICRO_GRID → FIRSAT(Connors)
     İlk sinyal kazanır, emir atılır, ID loglanır.

Hiçbir motor "sinyalde kalıp emir atmış" olarak bırakılmaz: atamazsa nedeni loglanır.
Spot long-only. Limit/market emirler ui.tr_scalper üzerinden gider.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth, tr_scalper as t

STATE = auth.USERS_DIR / "engine_state.json"
MAX_POSITIONS = 5
MIN_NET_PCT = 0.0
MOTOR_ORDER = ("CRASH_BID", "OBI_VWAP", "MICRO_GRID", "FIRSAT")


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


def _active() -> dict[str, Any]:
    return _load().get("active", {}) if isinstance(_load().get("active"), dict) else {}


def preflight(symbol: str, gross_gain_pct: float, day_dd_pct: float,
              open_positions: list[dict[str, Any]] | None = None,
              net_fn=None) -> tuple[bool, str]:
    """1-3. adım: fren, komisyon, pozisyon sayısı, çift motor."""
    from ui import tiered_brakes as tb

    s = tb.status(day_dd_pct)
    if not s["trade_allowed"]:
        return False, f"KADEMELİ FREN: {s['msg']} — emir atılmadı"
    if net_fn is None:
        from ui import micro_engine as me
        net_fn = me.net_profit_pct
    net = net_fn(gross_gain_pct)
    if not net["ok"] or net["net_pct"] <= MIN_NET_PCT:
        return (False, f"Net kâr yok (%{net['gross_pct']:.3f} - komisyon "
                       f"%{net['commission_pct']:.3f} = %{net['net_pct']:.3f}) — emir atılmadı")
    poss = open_positions if open_positions is not None else (t._load().get("positions") or [])
    if len(poss) >= MAX_POSITIONS:
        return False, f"MAX 5 POZİSYON: {len(poss)}/{MAX_POSITIONS} — emir atılmadı"
    active = _active()
    for motor in MOTOR_ORDER:
        key = f"{symbol}:{motor}"
        if active.get(key):
            return False, f"ÇİFT MOTOR ENGELLENDİ: {key} zaten açık — ikinci emir atılmadı"
    return True, "preflight OK"


def pick_motor(signals: dict[str, bool]) -> str | None:
    """İlk gelen kazanır — sıra sabit."""
    for motor in MOTOR_ORDER:
        if signals.get(motor):
            return motor
    return None


def _size(balance: float, day_dd_pct: float, score_pct: float = 0.05) -> tuple[float, float]:
    from ui import tiered_brakes as tb
    cap = tb.position_cap(balance, day_dd_pct, score_pct)
    return cap, cap / max(float(t.price("BTC_TRY") or 1), 1)


def place_buy(symbol: str, motor: str, cap_try: float,
              price_limit: float | None = None) -> dict[str, Any]:
    """Ortak emir atma — emri atar, ID'yi loglar ve state'e kaydeder."""
    px = price_limit or (t.price(symbol) or 0)
    if px <= 0 or cap_try <= 0:
        msg = f"{motor} emri atılamadı: fiyat={px} bakiye={cap_try:.2f}"
        _log(msg)
        return {"ok": False, "reason": msg}
    flt = t._filters(symbol)
    step = flt.get("step", 0) or 0.00000001
    qty = round(int((cap_try / px) / step + 1e-12) * step, 8)
    if qty <= 0:
        _log(f"{motor} emri atılamadı: qty={qty} step={step}")
        return {"ok": False, "reason": "step altı miktar"}
    res = t._order(symbol, 0, qty, price_limit=price_limit)
    body = ((res.get("data") or {}).get("data") or {}) if isinstance(res.get("data"), dict) else {}
    oid = body.get("orderId") or body.get("id")
    if res.get("ok"):
        st = _load()
        active = st.get("active") if isinstance(st.get("active"), dict) else {}
        active[f"{symbol}:{motor}"] = {
            "order_id": oid, "symbol": symbol, "motor": motor,
            "qty": qty, "price_limit": price_limit, "placed_at": time.time(),
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        st["active"] = active
        _save(st)
        _log(f"{motor} emri atıldı, ID {oid} · {symbol} {qty} adet "
             f"@ {px:.4f} · ₺{cap_try:.2f}")
    else:
        _log(f"{motor} emri atılamadı: {str(res.get('reason'))[:150]}")
    return {**res, "order_id": oid, "qty": qty}


def release(symbol: str, motor: str) -> None:
    st = _load()
    active = st.get("active") if isinstance(st.get("active"), dict) else {}
    active.pop(f"{symbol}:{motor}", None)
    st["active"] = active
    _save(st)


def active_for(symbol: str, motor: str) -> dict[str, Any]:
    return _active().get(f"{symbol}:{motor}", {})


def crash_bid_entry(symbol: str, last_close: float, cap_try: float,
                    day_dd_pct: float) -> dict[str, Any]:
    """Crash Bid: son kapanışın %2 altına LIMIT alış."""
    from ui import crash_bid as cb
    p = cb.plan(last_close)
    ok, why = preflight(symbol, 2.0, day_dd_pct)
    if not ok:
        _log(f"Crash Bid emri atılmadı: {why}")
        return {"ok": False, "reason": why}
    return place_buy(symbol, "CRASH_BID", cap_try, price_limit=p["bid_px"])


def obi_vwap_entry(symbol: str, price: float, cap_try: float,
                   day_dd_pct: float, gross_pct: float = 0.8) -> dict[str, Any]:
    """OBI+VWAP: onay gelince MARKET alış (15 sn TTL engine tarafından izlenir)."""
    ok, why = preflight(symbol, gross_pct, day_dd_pct)
    if not ok:
        _log(f"OBI+VWAP emri atılmadı: {why}")
        return {"ok": False, "reason": why}
    return place_buy(symbol, "OBI_VWAP", cap_try, price_limit=None)


def crash_bid_manage() -> list[str]:
    """Her dakika: limiti kaydır / dolumu tespit et / +%2 sat / 4 sa çık."""
    logs: list[str] = []
    from ui import crash_bid as cb
    st = _active()
    for key, a in list(st.items()):
        if a.get("motor") != "CRASH_BID" or a.get("filled"):
            continue
        sym, oid = a.get("symbol"), a.get("order_id")
        px = t.price(sym) or 0
        q = t.order_status(oid)
        body = (q.get("data") or {}) if q.get("ok") else {}
        filled = float(body.get("executedQty") or 0)
        if filled > 0:
            cb.mark_filled(body.get("executedPrice") or px, filled)
            a["filled"] = True
            a["fill_price"] = float(body.get("executedPrice") or px)
            a["filled_at"] = time.time()
            # +%2 satış limiti
            target = a["fill_price"] * 1.02
            sr = t._order(sym, 1, filled, price_limit=target)
            sb = ((sr.get("data") or {}).get("data") or {}) if isinstance(sr.get("data"), dict) else {}
            a["sell_order_id"] = sb.get("orderId") or sb.get("id")
            msg = (f"Crash Bid DOLDU ID {oid} · +%2 satış limiti ID {a['sell_order_id']} "
                   f"@ {target:.4f}")
            _log(msg); logs.append(msg)
            continue
        # Fiyat düştü → limiti aşağı kaydır; yükseldiyse sabit bırak
        new_limit = cb.slide_bid(px, (t._filters(sym).get("step") or 0.00000001))
        old = float(a.get("price_limit") or 0)
        if px > 0 and new_limit < old * 0.999:
            c = t.cancel_order(oid)
            if c.get("ok"):
                nr = place_buy(sym, "CRASH_BID", old * (a.get("qty") or 1), price_limit=new_limit)
                msg = f"Crash Bid limit kaydırıldı {old:.4f} → {new_limit:.4f} · yeni ID {nr.get('order_id')}"
            else:
                msg = f"Crash Bid limit kaydırılamadı (iptal hatası): {str(c.get('reason'))[:100]}"
            _log(msg); logs.append(msg)
        elif px > 0 and time.time() - float(a.get("placed_at", time.time())) > 4 * 3600:
            c = t.cancel_order(oid)
            release(sym, "CRASH_BID")
            msg = f"Crash Bid 4 saat doldu — limit iptal, ID {oid} · iptal={'OK' if c.get('ok') else 'HATA'}"
            _log(msg); logs.append(msg)
    return logs


def obi_vwap_manage(vwap: float, ttl_sec: float = 15.0) -> list[str]:
    """15 sn TTL: VWAP üstünde kalamazsa emri iptal/market sat."""
    logs: list[str] = []
    st = _active()
    for key, a in list(st.items()):
        if a.get("motor") != "OBI_VWAP":
            continue
        sym = a.get("symbol")
        px = t.price(sym) or 0
        age = time.time() - float(a.get("placed_at", time.time()))
        if px <= float(vwap) and age <= ttl_sec:
            continue
        if px <= float(vwap) and age > ttl_sec:
            sr = t.sell(sym, float(a.get("qty") or 0), "OBI+VWAP 15 sn TTL — VWAP üstünde kalamadı")
            release(sym, "OBI_VWAP")
            msg = (f"OBI+VWAP emri İPTAL (15 sn TTL) · {sym} · ID {a.get('order_id')} · "
                   f"satış={'OK' if sr.get('ok') else 'HATA'}")
            _log(msg); logs.append(msg)
        # TTL doldu ve hâlâ üstündeyse emri serbest bırak, pozisyon normal TP'ye devam eder
        elif age > ttl_sec:
            release(sym, "OBI_VWAP")
            msg = f"OBI+VWAP 15 sn doğrulandı · {sym} · ID {a.get('order_id')} — normal TP'ye devir"
            _log(msg); logs.append(msg)
    return logs
