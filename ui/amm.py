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
BUDGET_TRY = 3000.0        # Motor 1 — ayrı kasa
TRADE_MIN_TRY = 50.0
TRADE_MAX_TRY = 80.0
GAMMA = 0.5
KAPPA = 1.5
TAU = 15.0 / (24 * 60)          # 15 dakika, gün cinsinden
SPREAD_MIN = 0.0016             # %0.16 — komisyon %0.15'in üstünde olmalı
SPREAD_MAX = 0.0030             # %0.30
FEE_PCT = 0.15                  # maker + BNB (gidiş-dönüş)
QUOTE_TTL = 5.0
INVENTORY_TTL = 900.0           # 15 dk
MIN_NET_TRY = 0.20
TARGET_INV = 0.50               # %50 coin / %50 nakit
INV_BUY_CAP = 0.70              # %70 üstü → alış yok
INV_SELL_FLOOR = 0.30           # %30 altı → satış yok
TICK_START = time.time()
_FILTER_CACHE: dict[str, tuple[float, dict[str, float]]] = {}
_SIGMA_CACHE: dict[str, tuple[float, float]] = {}


def cached_filters(symbol: str) -> dict[str, float]:
    now = time.time()
    hit = _FILTER_CACHE.get(symbol)
    if hit and now - hit[0] < 300:
        return hit[1]
    f = t._filters(symbol)
    _FILTER_CACHE[symbol] = (now, f)
    return f


def cached_sigma(symbol: str) -> float:
    now = time.time()
    hit = _SIGMA_CACHE.get(symbol)
    if hit and now - hit[0] < 30:
        return hit[1]
    s = sigma(symbol)
    _SIGMA_CACHE[symbol] = (now, s)
    return s


def _log(msg: str) -> None:
    try:
        from ui import autonomous_ops
        autonomous_ops._log("HSC-AMM: " + msg)
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


def on_ws_fill(ev: dict[str, Any]) -> None:
    """WS ExecutionReport FILLED → AMM defteri, ID'YE BAKMADAN.

    Binance TR WS ve REST orderId alanları farklı numara aralığında;
    bu yüzden eşleştirme sembol + yön (S) + miktar (z) ile yapılır.
    """
    sym_raw = str(ev.get("s") or "")
    sym = sym_raw if "_" in sym_raw else ""
    if not sym:
        # örn. BTCUSDT / ETHUSDT -> BTC_TRY
        for base in ("BTC", "ETH"):
            if sym_raw.startswith(base):
                sym = f"{base}_TRY"
                break
    if sym not in SYMBOLS:
        return
    ws_id = str(ev.get("i") or "")
    side = str(ev.get("S") or "").upper()          # BUY / SELL
    qty = float(ev.get("z") or ev.get("q") or 0)
    px = float(ev.get("L") or ev.get("p") or 0)   # last executed price
    if qty <= 0 or px <= 0 or side not in ("BUY", "SELL"):
        return
    # REST tarafındaki gerçek emir/fiyatı işlem geçmişinden bul (WS ID = bOrderId).
    # Böylece K/Z, botun kendi emir fiyatıyla değil GERÇEK dolumla hesaplanır.
    try:
        ok, data = t._request("/open/v1/orders/trades",
                              {"symbol": sym, "limit": 100}, signed=True)
        if ok and isinstance(data, dict):
            for tr in ((data.get("data") or {}).get("list") or []):
                if str(tr.get("bOrderId") or "") == ws_id:
                    px = float(tr.get("price") or px)
                    qty = float(tr.get("qty") or qty)
                    break
    except Exception:
        pass
    st = _load()
    invs = st.get("inventories") if isinstance(st.get("inventories"), dict) else {}
    old = invs.get(sym) or {}
    entry = float(old.get("entry") or px)
    # Gerçek dolumu deftere işle
    if side == "SELL":
        _record_trade(sym, "SELL", qty, px, entry)
        new_qty = float(old.get("qty") or 0) - qty
        if new_qty <= 0:
            invs.pop(sym, None)
            from ui import motor_guard
            motor_guard.release(sym, "AMM")
        else:
            old["qty"] = round(new_qty, 8)
            invs[sym] = old
    else:
        old_qty = float(old.get("qty") or 0)
        new_qty = old_qty + qty
        avg = ((entry * old_qty + px * qty) / new_qty) if new_qty > 0 else px
        invs[sym] = {"symbol": sym, "qty": round(new_qty, 8),
                     "entry": round(avg, 8), "entry_ts": old.get("entry_ts", time.time()),
                     "notional": float(old.get("notional") or 80.0), "motor": "AMM"}
    st["inventories"] = invs
    # WS dolumundan sonra defteri GERÇEK API bakiyesiyle eşitle (kayma kalmasın)
    for s2 in SYMBOLS:
        actual = float(t.asset_balance(s2.split("_")[0]) or 0)
        if actual <= 0:
            st["inventories"].pop(s2, None)
        else:
            rec = st["inventories"].get(s2)
            if rec:
                rec["qty"] = actual
            else:
                mid2, _, _ = mid_and_spread(s2)
                st["inventories"][s2] = {"symbol": s2, "qty": actual,
                                         "entry": mid2 or px, "entry_ts": time.time(),
                                         "notional": 80.0, "motor": "AMM"}
    _save(st)
    _log(f"WS dolum deftere işlendi · {sym} {side} {qty} @ {px:.8f} · "
         f"envanter={st['inventories'].get(sym, {}).get('qty', 0):.8f}")


def reconcile_from_exchange() -> list[str]:
    """Geçmişte kaçan dolumları işlem geçmişinden deftere işle.

    Her dolumun `bOrderId` alanı WS orderId'sidir — alım/satım ayrımı
    gerçek bakiye ve state karşılaştırmasıyla yapılır. K/Z 'net_kar_zarar'
    trades.csv'ye yazılır.
    """
    logs: list[str] = []
    try:
        ok, data = t._request("/open/v1/orders/trades",
                              {"symbol": "BTC_TRY", "limit": 100}, signed=True)
        ok2, data2 = t._request("/open/v1/orders/trades",
                                {"symbol": "ETH_TRY", "limit": 100}, signed=True)
    except Exception:
        return logs
    # trades.csv'de kayıtlı AMM tradeId'leri (strateji adıyla)
    import csv as _csv
    done = set()
    if t.TRADES_CSV.exists():
        with t.TRADES_CSV.open(encoding="utf-8-sig", newline="") as fh:
            for r in _csv.DictReader(fh):
                if "HSC-AMM" in str(r.get("strateji_adı", "")):
                    done.add(str(r.get("işlem_süresi", "")))
    for okd, dd, sym in ((ok, data, "BTC_TRY"), (ok2, data2, "ETH_TRY")):
        if not okd or not isinstance(dd, dict):
            continue
        for tr in ((dd.get("data") or {}).get("list") or []):
            tid = str(tr.get("tradeId") or "")
            ws_id = str(tr.get("bOrderId") or "")
            px = float(tr.get("price") or 0)
            qty = float(tr.get("qty") or 0)
            if tid in done or px <= 0 or qty <= 0:
                continue
            # Bu dolum AMM'nin mi? REST orderId'si bizim state/quotes'da var mı?
            oid = str(tr.get("orderId") or "")
            st = _load()
            known = any(str(v.get("order_id")) == oid
                        for v in (st.get("quotes") or {}).values())
            if not known:
                continue
            # Yön: emir state'de SATIŞ olarak işaretliyse satış, yoksa alım.
            side = "SELL" if any(str(v.get("order_id")) == oid and v.get("side") == "SELL"
                                 for v in (st.get("quotes") or {}).values()) else "BUY"
            entry = px
            net = 0.0
            if side == "SELL":
                # giriş fiyatı: aynı sembolun son alımı
                for tr2 in ((dd.get("data") or {}).get("list") or []):
                    if str(tr2.get("orderId")) == oid:
                        break
                    if str(tr2.get("bOrderId")).startswith("2568" if sym == "ETH_TRY" else "3533"):
                        entry = px  # conservative
                net = (px - entry) * qty - qty * px * 0.00075
            _record_trade(sym, side, qty, px, entry)
            logs.append(f"GEÇMİŞ DOLUM deftere işlendi · {sym} {side} {qty} @ {px:.4f} net={net:+.4f} (WS ID {ws_id})")
    # Envanteri GERÇEK bakiyeye eşitle
    st = _load()
    invs = st.get("inventories") if isinstance(st.get("inventories"), dict) else {}
    for s2 in SYMBOLS:
        actual = float(t.asset_balance(s2.split("_")[0]) or 0)
        if actual > 0:
            old = invs.get(s2) or {}
            old["qty"] = actual
            invs[s2] = old
        else:
            invs.pop(s2, None)
    st["inventories"] = invs
    _save(st)
    return logs


def reservation_price(mid: float, q: float, sig: float) -> float:
    return mid - q * GAMMA * (sig ** 2) * TAU


def dynamic_spread(sig: float) -> float:
    # Komisyon tabanı + gerçek sigma primi. (2/gamma)*ln(...) terimi sabit
    # ~%1.15 olduğu için her zaman tavana çıkıyordu — kaldırıldı.
    raw = (FEE_PCT + GAMMA * (sig ** 2) * TAU * 100 + sig * 100) / 100.0
    return max(SPREAD_MIN, min(SPREAD_MAX, raw))


def inventory_ratio(symbol: str, st: dict[str, Any]) -> float:
    """0 = tam nakit, 1 = tam coin. Hedef 0.50."""
    inv = (st.get("inventories") or {}).get(symbol) or {}
    if float(inv.get("qty") or 0) <= 0:
        return 0.0
    mid, _, _ = mid_and_spread(symbol)
    coin_value = float(inv["qty"]) * (mid or float(inv.get("entry") or 0))
    # Sembol başına kasa: ₺3000 / 2 coin = ₺1500; hedef %50 → ₺750.
    budget = BUDGET_TRY / len(SYMBOLS)
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
    # HSC-AMM trend TAHMİNİ YAPMAZ → SMA200 kapası yok (kullanıcı kararı).
    # Çakışma engeli: YÖNLÜ motoru aynı coin'de işlemdeyse AMM girmez.
    from ui import motor_guard
    conflict = motor_guard.conflict(symbol, "AMM")
    if conflict:
        return False, f"çakışma engeli: {conflict}"
    # ORTAK max 5 pozisyon (yönlü + AMM)
    _core = t._load()
    total = len(_core.get("positions") or []) + (1 if _core.get("position") else 0)
    total += sum(1 for v in (_load().get("inventories") or {}).values()
                 if float((v or {}).get("qty") or 0) > 0)
    if total >= 5:
        return False, f"ortak max 5 pozisyon dolu ({total}/5)"
    # Ayrı kasa bütçesi
    used = float(st_budget_used())
    if used >= BUDGET_TRY:
        return False, f"AMM kasası dolu ({used:.0f}/{BUDGET_TRY:.0f} TL)"
    return True, "OK"


def _record_trade(symbol: str, side: str, qty: float, px: float,
                  entry: float) -> None:
    """AMM gerçek dolumunu trades.csv'ye yazar (motor bazlı defter)."""
    import time as _t

    fee = qty * px * 0.00075
    net = ((px - entry) * qty - fee) if side == "SELL" else -fee
    t._write_trade_csv({
        "tarih": _t.strftime("%Y-%m-%d %H:%M:%S"), "sembol": symbol,
        "alış_fiyatı": round(entry if side == "SELL" else px, 8),
        "satış_fiyatı": round(px if side == "SELL" else 0, 8),
        "adet": qty, "komisyon": round(fee, 6), "komisyon_oranı": 0.00075,
        "net_kar_zarar": round(net, 4), "işlem_süresi": "—",
        "strateji_adı": "HSC-AMM (maker+BNB)",
    })


def st_budget_used() -> float:
    s = _load()
    invs = s.get("inventories") or {}
    return sum(float(v.get("notional", 0) or 0) for v in invs.values()) + sum(
        float(q.get("notional", 0) or 0) for q in (s.get("quotes") or {}).values())


def step() -> list[str]:
    logs: list[str] = []
    t0 = time.time()
    st = _load()
    logs.append(fee_msg())
    _old = st.pop("inventory", None)
    if isinstance(_old, dict) and _old.get("symbol"):
        _invs0 = st.get("inventories") if isinstance(st.get("inventories"), dict) else {}
        _invs0.setdefault(_old["symbol"], _old)
        st["inventories"] = _invs0

    # 0) RECONCILE — defter ile gerçek bakiye uyuşmuyorsa gerçeği esas al.
    invs = st.get("inventories", {}) if isinstance(st.get("inventories"), dict) else {}
    for sym_i, inv_i in list(invs.items()):
        actual = float(t.asset_balance(sym_i.split("_")[0]) or 0)
        book = float((inv_i or {}).get("qty") or 0)
        if actual <= 0:
            invs.pop(sym_i, None)
            from ui import motor_guard
            motor_guard.release(sym_i, "AMM")
        elif actual < book * 0.999:
            invs[sym_i]["qty"] = actual
            logs.append(f"RECONCILE {sym_i}: defter {book:.8f} → gerçek {actual:.8f}")
    st["inventories"] = invs

    # 1) envanter süresi (15 dk) — sembol başına ayrı
    for sym_i, inv in list(invs.items()):
        if not inv or float(inv.get("qty") or 0) <= 0:
            invs.pop(sym_i, None); continue
        age = time.time() - float(inv.get("entry_ts", time.time()))
        if age >= INVENTORY_TTL:
            r = t.sell(sym_i, float(inv["qty"]), "HSC-AMM 15 dk envanter çıkışı")
            ok = isinstance(r, dict) and bool(r.get("ok"))
            msg = (f"ENVANTER ÇIKIŞI · {sym_i} · "
                   f"{'OK' if ok else 'HATA'} · {'kârda' if float(inv.get('entry',0)) < float(t.price(sym_i) or 0) else 'zararda'}")
            _log(msg); logs.append(msg)
            invs.pop(sym_i, None)
            from ui import motor_guard
            motor_guard.release(sym_i, "AMM")
    st["inventories"] = invs

    # 2) bekleyen emirleri kontrol et / 5 sn TTL
    quotes = st.get("quotes", {}) if isinstance(st.get("quotes"), dict) else {}
    for key, q in list(quotes.items()):
        age = time.time() - float(q.get("at", time.time()))
        rs = t.order_status(q.get("order_id"))
        body = rs.get("data") or {}
        filled = float(body.get("executedQty") or 0)
        if filled > 0:
            px = float(body.get("executedPrice") or q.get("price") or 0)
            _is = st.get("inventories") if isinstance(st.get("inventories"), dict) else {}
            old = _is.get(q["symbol"]) or {}
            old_qty = float(old.get("qty") or 0)
            if q["side"] == "SELL":
                _record_trade(q["symbol"], "SELL", float(filled), px,
                              float(old.get("entry") or px))
            new_qty = old_qty + (float(filled) if q["side"] == "BUY" else -float(filled))
            if new_qty <= 0:
                _is.pop(q["symbol"], None)
                from ui import motor_guard
                motor_guard.release(q["symbol"], "AMM")
            else:
                avg = ((float(old.get("entry") or px) * old_qty + px * float(filled)) / new_qty
                       if q["side"] == "BUY" else float(old.get("entry") or px))
                _is[q["symbol"]] = {"symbol": q["symbol"], "qty": new_qty,
                                    "entry": round(avg, 8), "entry_ts": old.get("entry_ts", time.time()),
                                    "notional": float(q.get("notional") or 0), "motor": "AMM"}
            st["inventories"] = _is
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
        sig = cached_sigma(sym)
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
        flt = cached_filters(sym)
        stepq = flt.get("step") or 0.00000001
        cap = min(BUDGET_TRY - st_budget_used(), TRADE_MAX_TRY)
        if cap < TRADE_MIN_TRY:
            logs.append(f"HSC-AMM {sym}: kasa limiti — işlem ₺{cap:.0f} < ₺{TRADE_MIN_TRY:.0f}")
            continue
        for side in sides:
            px = (r - sp / 2) if side == "BUY" else (r + sp / 2)
            for existing in list(quotes.values()):
                if existing.get("symbol") == sym and existing.get("side") == side:
                    if abs(float(existing.get("price") or 0) - px) < stepq:
                        break   # aynı fiyat — emir güncellemeye gerek yok
                    t.cancel_order(existing.get("order_id"))
                    quotes.pop(f"{sym}:{side}", None)
            else:
                # Hedef 50-80 TL = cap/px (önceden 0.02 çarpanı ETH'de ₺0.87 emir üretiyordu)
                raw_qty = cap / px
                min_notional = float(flt.get("min_notional") or 10)
                need = max(raw_qty, min_notional / px, float(flt.get("min_qty") or stepq))
                # step katına YUKARI yuvarla — aşağı yuvarlarsak min notional altına düşer
                qty = round(int(need / stepq + 1e-9) * stepq, 8)
                if qty * px < min_notional:
                    qty = round((int(need / stepq) + 1) * stepq, 8)
                _my_inv = (st.get("inventories") or {}).get(sym) or {}
                if side == "SELL" and float(_my_inv.get("qty") or 0) <= 0:
                    continue   # satacak coin yok
                if side == "SELL":
                    qty = min(qty, float(_my_inv["qty"]))
                res = (t._order(sym, 0, qty, price_limit=px, post_only=True)
                       if side == "BUY" else
                       t.sell(sym, qty, "HSC-AMM maker satış", price_limit=px, post_only=True))
                body2 = ((res.get("data") or {}).get("data") or {}) if isinstance(res.get("data"), dict) else {}
                oid = body2.get("orderId") or body2.get("id")
                if side == "SELL" and isinstance(res, dict) and res.get("ok") and not oid:
                    # Limit satış anında doldu —ID yok, envanteri hemen kapat, deftere yaz.
                    if qty > 0:
                        _record_trade(sym, "SELL", qty, px, float(_my_inv.get("entry") or px))
                    _isx = st.get("inventories") if isinstance(st.get("inventories"), dict) else {}
                    _isx.pop(sym, None)
                    st["inventories"] = _isx
                    from ui import motor_guard
                    motor_guard.release(sym, "AMM")
                    logs.append(f"HSC-AMM SATIŞ anında doldu · {sym} {qty} @ {px:.8f} — defter güncellendi")
                    continue
                if isinstance(res, dict) and res.get("ok") and oid:
                    quotes[f"{sym}:{side}"] = {"order_id": oid, "symbol": sym,
                                                "side": side, "price": px,
                                                "qty": qty, "at": time.time(),
                                                "notional": cap, "motor": "AMM"}
                    from ui import motor_guard
                    motor_guard.claim(sym, "AMM")
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
    return ["HSC-AMM: " + x for x in logs]
