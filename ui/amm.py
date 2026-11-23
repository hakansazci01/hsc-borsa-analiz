"""HSC-AMM — Avellaneda-Stoikov + Hummingbot envanter skew (sadeleştirilmiş).

Yeni strateji icadı DEĞİL; literatürdeki market making mantığının küçük
sermayeye (BTC_TRY + ETH_TRY) uyarlanmış hâli.

  r  = mid - q * gamma * sigma^2 * tau
  q  = normalize envanter (-1 tam nakit .. +1 tam coin), hedef 0
  bid = r - spread/2 , ask = r + spread/2
  spread = clamp(gamma*sigma^2*tau + 2/gamma*ln(1+gamma/k), 0.10%, 0.30%)

Envanter %70 coin üstü → sadece SAT; %30 altı → sadece AL (bıçak yakalama yok).
Post-only (LIMIT_MAKER) emirler, 5 sn TTL, 15 dk envanter süresi.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

from ui import auth, tr_scalper as t

STATE = auth.USERS_DIR / "amm_state.json"
SYMBOLS = ("BTC_TRY", "ETH_TRY")
GAMMA = 0.5
KAPPA = 1.5
TAU = 15.0 / (24 * 60)          # 15 dakika, gün cinsinden
SPREAD_MIN = 0.0010             # %0.10
SPREAD_MAX = 0.0030             # %0.30
FEE_PCT = 0.15                  # maker + BNB (gidiş-dönüş)
QUOTE_TTL = 5.0
INVENTORY_TTL = 900.0           # 15 dk
MIN_NET_TRY = 0.20
TARGET_INV = 0.50               # %50 coin / %50 nakit
INV_BUY_CAP = 0.70              # %70 üstü → alış yok
INV_SELL_FLOOR = 0.30           # %30 altı → satış yok
TICK_START = time.time()


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


def fee_msg() -> str:
    bnb = float(t.asset_balance("BNB") or 0)
    if bnb > 0:
        return f"KOMİSYON: maker+BNB %{FEE_PCT:.2f} (BNB {bnb:.4f})"
    return f"UYARI: BNB YOK - KOMİSYON %0.20"


def sigma(symbol: str) -> float:
    """Son 60 dakikalık (1dk mum) getiri volatilitesi, günlük ölçekte."""
    try:
        k = t.klines(symbol, "1m", 60)
        c = [float(x) for x in k["Close"].tolist()]
        rets = [(c[i] - c[i-1]) / c[i-1] for i in range(1, len(c)) if c[i-1] > 0]
        if len(rets) < 10:
            return 0.0
        mu = sum(rets) / len(rets)
        var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
        return math.sqrt(max(0.0, var))
    except Exception:
        return 0.0


def mid_and_spread(symbol: str) -> tuple[float, float, float]:
    from ui import ws_feed
    d = ((ws_feed._load().get("depth_obi") or {}).get(symbol) or {})
    bid = float(d.get("best_bid") or 0)
    ask = float(d.get("best_ask") or 0)
    if bid <= 0 or ask <= 0:
        return 0.0, 0.0, 99.0
    mid = (bid + ask) / 2
    return mid, bid, ask


def reservation_price(mid: float, q: float, sig: float) -> float:
    return mid - q * GAMMA * (sig ** 2) * TAU


def dynamic_spread(sig: float) -> float:
    # A-S + Hummingbot sadeformül: taban komisyon + volatilite primi
    raw = GAMMA * (sig ** 2) * TAU + (2.0 / GAMMA) * math.log(1.0 + GAMMA / KAPPA)
    return max(SPREAD_MIN, min(SPREAD_MAX, raw))


def inventory_ratio(symbol: str, st: dict[str, Any]) -> float:
    """0 = tam nakit, 1 = tam coin. Hedef 0.50."""
    inv = st.get("inventory") or {}
    if inv.get("symbol") != symbol or float(inv.get("qty") or 0) <= 0:
        return 0.0
    mid, _, _ = mid_and_spread(symbol)
    coin_value = float(inv["qty"]) * (mid or float(inv.get("entry") or 0))
    budget = float(st.get("budget_try", 500.0) or 500.0)
    return round(min(1.0, max(0.0, coin_value / max(budget, 1.0))), 4)


def preflight(symbol: str) -> tuple[bool, str]:
    from ui import safety_guards as sg, risk_brakes as rb, tiered_brakes as tb, tp_proof
    # TP kilidi ORİJİNAL anlamı: açık pozisyon varsa yeni emir yok.
    # Pozisyon yoksa kilit yeni girişi engellemez (mevcut davranış aynen).
    if t._load().get("position") or (t._load().get("positions") or []):
        return False, "TP kilidi: aktif pozisyon var — yeni emir yok"
    if not sg.buy_allowed()[0]:
        return False, "CUSUM freni"
    if not sg.stale_check()[0]:
        return False, "stale veri"
    br = rb.status()
    if br.get("daily_breached") or br.get("dd_breached"):
        return False, "portföy freni"
    if tb.status(0)["tier"] >= 2:
        return False, "kademeli fren"
    # günlük SMA200
    try:
        k = t.klines(symbol, "1d", 210)
        s200 = float(k["Close"].rolling(200).mean().iloc[-1])
        mid, _, _ = mid_and_spread(symbol)
        if mid <= 0 or mid <= s200:
            return False, f"SMA200 altı ({mid:.2f} ≤ {s200:.2f})"
    except Exception:
        return False, "SMA200 verisi yok"
    return True, "OK"


def step() -> list[str]:
    logs: list[str] = []
    t0 = time.time()
    st = _load()
    logs.append(fee_msg())

    # 1) envanter süresi (15 dk)
    inv = st.get("inventory")
    if inv and inv.get("symbol") and float(inv.get("qty") or 0) > 0:
        age = time.time() - float(inv.get("entry_ts", time.time()))
        if age >= INVENTORY_TTL:
            r = t.sell(inv["symbol"], float(inv["qty"]), "HSC-AMM 15 dk envanter çıkışı")
            ok = isinstance(r, dict) and bool(r.get("ok"))
            msg = (f"HSC-AMM ENVANTER ÇIKIŞI · {inv['symbol']} · "
                   f"{'OK' if ok else 'HATA'} · {'kârda' if float(inv.get('entry',0)) < float(t.price(inv['symbol']) or 0) else 'zararda'}")
            _log(msg); logs.append(msg)
            st["inventory"] = None

    # 2) bekleyen emirleri kontrol et / 5 sn TTL
    quotes = st.get("quotes", {}) if isinstance(st.get("quotes"), dict) else {}
    for key, q in list(quotes.items()):
        age = time.time() - float(q.get("at", time.time()))
        rs = t.order_status(q.get("order_id"))
        body = rs.get("data") or {}
        filled = float(body.get("executedQty") or 0)
        if filled > 0:
            px = float(body.get("executedPrice") or q.get("price") or 0)
            inv = {"symbol": q["symbol"], "qty": filled, "entry": px,
                   "entry_ts": time.time()}
            st["inventory"] = inv
            quotes.pop(key, None)
            msg = (f"HSC-AMM DOLUM ID {q.get('order_id')} · {q['symbol']} "
                   f"{filled} @ {px:.8f} ({q['side']})")
            _log(msg); logs.append(msg)
        elif age >= QUOTE_TTL:
            c = t.cancel_order(q.get("order_id"))
            quotes.pop(key, None)
            logs.append(f"HSC-AMM 5 sn iptal ID {q.get('order_id')} · "
                        f"{'OK' if c.get('ok') else 'HATA'}")

    # 3) her sembol için rezervasyon fiyatı + emir
    for sym in SYMBOLS:
        ok, why = preflight(sym)
        mid, bid, ask = mid_and_spread(sym)
        sig = sigma(sym)
        q = inventory_ratio(sym, st) * 2 - 1     # -1..+1
        r = reservation_price(mid, q, sig) if mid > 0 else 0.0
        sp = dynamic_spread(sig) if mid > 0 else 0.0
        spread_pct = sp * 100
        logs.append(f"REZERVASYON: {sym} mid={mid:.8f}, r={r:.8f}, "
                    f"spread={spread_pct:.3f}%, envanter={q:+.2f}, sigma={sig:.6f}")
        if not ok:
            logs.append(f"HSC-AMM {sym}: {why}")
            continue
        if mid <= 0 or sp * 100 < FEE_PCT:
            logs.append(f"HSC-AMM {sym}: spread %{spread_pct:.3f} < komisyon %{FEE_PCT:.2f} — emir yok")
            continue
        invr = inventory_ratio(sym, st)
        sides: list[str] = []
        if invr <= INV_BUY_CAP:
            sides.append("BUY")
        if invr >= INV_SELL_FLOOR:
            sides.append("SELL")
        flt = t._filters(sym)
        stepq = flt.get("step") or 0.00000001
        cap = float(st.get("budget_try", 500.0) or 500.0)
        for side in sides:
            px = (r - sp / 2) if side == "BUY" else (r + sp / 2)
            for existing in list(quotes.values()):
                if existing.get("symbol") == sym and existing.get("side") == side:
                    if abs(float(existing.get("price") or 0) - px) < stepq:
                        break   # aynı fiyat — emir güncellemeye gerek yok
                    t.cancel_order(existing.get("order_id"))
                    quotes.pop(f"{sym}:{side}", None)
            else:
                qty = round(max((cap / px) * 0.02, (flt.get("min_qty") or stepq)), 8)
                if side == "SELL" and not (st.get("inventory") or {}).get("qty"):
                    continue   # satacak coin yok
                if side == "SELL":
                    qty = min(qty, float(st["inventory"]["qty"]))
                res = (t._order(sym, 0, qty, price_limit=px, post_only=True)
                       if side == "BUY" else
                       t.sell(sym, qty, "HSC-AMM maker satış", price_limit=px, post_only=True))
                body2 = ((res.get("data") or {}).get("data") or {}) if isinstance(res.get("data"), dict) else {}
                oid = body2.get("orderId") or body2.get("id")
                if isinstance(res, dict) and res.get("ok"):
                    quotes[f"{sym}:{side}"] = {"order_id": oid, "symbol": sym,
                                                "side": side, "price": px,
                                                "qty": qty, "at": time.time()}
                    msg = (f"HSC-AMM {'ALIŞ' if side=='BUY' else 'SATIŞ'} emri ID {oid} · "
                           f"{sym} {qty} @ {px:.8f} · r={r:.8f} · spread=%{spread_pct:.3f}")
                    _log(msg); logs.append(msg)
                else:
                    logs.append(f"HSC-AMM {side} emir reddedildi: "
                                f"{str(res.get('reason') if isinstance(res, dict) else res)[:100]}")

    st["quotes"] = quotes
    _save(st)
    dt = time.time() - t0
    logs.append(f"TUR: {dt:.1f} sn hesaplama / 5 sn periyot · "
                f"mid/r/spread/envanter güncellendi · {fee_msg()}")
    return logs
