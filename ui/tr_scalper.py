"""
Binance TR canlı mikro-alsat motoru (1 dakikalık gerçek veri).

Kurallar (kasıtlı olarak sıkı):
- Yalnızca TRY çiftleri, tek seferde en fazla MAX_ORDER_TRY tutar.
- Açık pozisyon tek; TP'ye (varsayılan %0,45) veya SL'ye (%0,35) erişince satar.
- Günlük/net kayıp MAX_LOSS_TRY'yi (varsayılan ₺3) geçerse motor durur (kill switch).
- En fazla MAX_TRADES işlem; emirler idempotency ile korunur.
- Tüm emirler ui.binance_tr_bot._request ile imzalanır; anahtarlar görünmez.

Bu bir deneydir; kâr garantisi YOKTUR. Gerçek para kullanılır.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from ui import auth
from ui.binance_tr_bot import _request
from ui.secrets_access import get


PAIRS = ("XRP_TRY", "DOGE_TRY", "ADA_TRY", "TRX_TRY", "LTC_TRY", "LINK_TRY", "FORM_TRY")
STATE = auth.USERS_DIR / "tr_scalper_state.json"
STOP_FILE = auth.USERS_DIR / "TR_SCALPER_STOP"

MAX_ORDER_TRY = 50.0       # taban emir boyutu (buyuk sermayeye gore)
MAX_ORDER_GROW = 100.0     # ust sinir: bakiyenin %15'i veya 100 TL
MAX_LOSS_TRY = 15.0        # toplam zarar kilidi (sermayenin ~%3'u)
MAX_TRADES = 50            # surekli calisma: islem sayisi siniri yok (zarar siniri yeterli)
MAX_HOLD_SEC = 900        # 15 dk'dan uzun suren durgun pozisyonu serbest birak
TAKE_PROFIT = 0.0080       # kazananlari kos: hedef %0.80
STOP_LOSS = 0.0035
TRAIL_ACTIVATE = 0.0040    # %0.40 ustunde trailing baslar
TRAIL_DISTANCE = 0.0035    # zirveden %0.35 geri cekilince sat
BREAKEVEN = 0.0022         # komisyonu kurtaran kilit seviyesi


def _load() -> dict[str, Any]:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def klines(symbol: str, interval: str = "1m", limit: int = 60) -> pd.DataFrame | None:
    plain = symbol.replace("_", "")
    url = f"https://api.binance.me/api/v1/klines?symbol={plain}&interval={interval}&limit={limit}"
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            rows = json.loads(r.read().decode())
        return pd.DataFrame([{
            "Open": float(x[1]), "High": float(x[2]), "Low": float(x[3]),
            "Close": float(x[4]), "Volume": float(x[5]),
        } for x in rows])
    except Exception:
        return None


def _filters(symbol: str) -> dict[str, float]:
    import urllib.request

    try:
        with urllib.request.urlopen("https://www.binance.tr/open/v1/common/symbols", timeout=12) as r:
            data = json.loads(r.read().decode())
        for s in data.get("data", {}).get("list", []):
            if s.get("symbol") == symbol:
                out: dict[str, float] = {}
                for f in s.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        out["min_qty"] = float(f["minQty"])
                        out["step"] = float(f["stepSize"])
                    if f.get("filterType") == "NOTIONAL":
                        out["min_notional"] = float(f["minNotional"])
                return out
    except Exception:
        pass
    return {"min_qty": 0.0, "step": 0.0, "min_notional": 10.0}


def _round_qty(qty: float, step: float, minimum: float) -> float:
    if step <= 0:
        return round(qty, 6)
    n = int(qty / step)
    val = round(n * step, 8)
    if val < minimum:
        val = round((n + 1) * step, 8)
    return val


def price(symbol: str) -> float | None:
    ok, data = _request("/open/v1/ticker/price", {"symbol": symbol.replace("_", "")})
    if ok and isinstance(data, dict):
        try:
            return float(data.get("price"))
        except (TypeError, ValueError):
            pass
    frame = klines(symbol, "1m", 1)
    return float(frame["Close"].iloc[-1]) if frame is not None and not frame.empty else None


def signal(symbol: str) -> dict[str, Any]:
    """1 dk momentum: EMA9/20 + RSI7 + hacim teyidi + 10 mum kırılımı."""
    f = klines(symbol, "1m", 60)
    if f is None or len(f) < 30:
        return {"decision": "BEKLE", "reason": "veri yok"}
    c = f["Close"]
    ema9 = c.ewm(span=9, adjust=False).mean()
    ema20 = c.ewm(span=20, adjust=False).mean()
    d = c.diff()
    gain = d.clip(lower=0).ewm(alpha=1 / 7, adjust=False).mean()
    loss = (-d.clip(upper=0)).ewm(alpha=1 / 7, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    r = float(rsi.iloc[-1])
    vol_avg = float(f["Volume"].iloc[-20:].mean())
    vol_last = float(f["Volume"].iloc[-1])
    up = ema9.iloc[-1] > ema20.iloc[-1]
    breakout = float(c.iloc[-1]) > float(c.iloc[-11:-1].max())
    breakdown = float(c.iloc[-1]) < float(c.iloc[-11:-1].min())
    if up and r < 72 and breakout and vol_last > vol_avg * 1.15:
        return {"decision": "AL", "rsi": round(r, 1), "price": float(c.iloc[-1]),
                "reason": "1dk EMA yukari + kirilim + hacim"}
    # Asiri satimdan ilk yukselis (mean-reversion scalp): sıkı stop ile.
    if r < 34 and float(c.iloc[-1]) > float(c.iloc[-2]) and vol_last > vol_avg * 0.7:
        return {"decision": "AL", "rsi": round(r, 1), "price": float(c.iloc[-1]),
                "reason": "1dk asiri satim (RSI<34) + ilk yukselis"}
    if (not up and r > 55 and breakdown) or r > 78:
        return {"decision": "SAT", "rsi": round(r, 1), "price": float(c.iloc[-1]),
                "reason": "1dk EMA asagi / asiri alim"}
    return {"decision": "BEKLE", "rsi": round(r, 1), "price": float(c.iloc[-1]), "reason": "net yok"}


def _order(symbol: str, side: int, qty: float) -> dict[str, Any]:
    payload = {"symbol": symbol, "side": side, "type": 2, "quantity": str(qty)}
    ok, data = _request("/open/v1/orders", payload, signed=True, method="POST")
    if not ok:
        res = {"ok": False, "reason": str(data)[:200]}
    elif isinstance(data, dict) and data.get("code") not in (0, None):
        res = {"ok": False, "reason": f"{data.get('code')}: {data.get('msg')}"}
    else:
        res = {"ok": True, "data": data}
    try:
        from ui.trade_notify import order_alert

        side_name = "AL" if side == 0 else "SAT"
        body = (res.get("data") or {}).get("data") or {} if isinstance(res.get("data"), dict) else {}
        detail = f"orderId={body.get('orderId') or body.get('id')}" if body else str(res.get("reason", ""))[:160]
        order_alert(symbol, side_name, qty, payload.get("price", 0) or 0, bool(res.get("ok")), detail)
    except Exception:
        pass
    return res


def asset_balance(asset: str) -> float:
    """Gercek kullanilabilir bakiye (komisyon dusulmus)."""
    ok, data = _request("/open/v1/account/spot", signed=True)
    if ok and isinstance(data, dict) and data.get("code") in (0, None):
        for a in (data.get("data", {}).get("accountAssets") or []):
            if a.get("asset") == asset:
                try:
                    return float(a.get("free", 0) or 0)
                except (TypeError, ValueError):
                    return 0.0
    return 0.0


def available_try() -> float:
    return asset_balance("TRY")


def buy(symbol: str, qty_override: float | None = None) -> dict[str, Any]:
    # ADIM 1: 1-dk scalper kapatıldı. Doğrudan çağrı engellenir.
    # Tek giriş yolu ui.daily_engine.buy() (günlük EMA50 pullback).
    return {"ok": False, "reason": "1dk scalper KAPALI — ui.daily_engine kullanılmalı"}


def _buy_legacy(symbol: str, qty_override: float | None = None) -> dict[str, Any]:
    px = price(symbol)
    if not px:
        return {"ok": False, "reason": "fiyat yok"}
    flt = _filters(symbol)
    step = flt["step"] or 0.00000001
    if qty_override is not None:
        qty = qty_override
    else:
        # Kar odakli buyume: bakiyenin %15'i, taban 50 TL, ust sinir 100 TL.
        bal = available_try()
        budget = min(MAX_ORDER_GROW, max(MAX_ORDER_TRY, bal * 0.15))
        need = max(budget, flt["min_notional"] + 0.5) / px
        qty = round(int(need / step + 0.999999) * step, 8)
    qty = max(qty, flt["min_qty"])
    res = _order(symbol, 0, qty)  # 0 = AL
    if res.get("ok"):
        st = _load()
        body = (res.get("data") or {}).get("data") or {}
        # Komisyon base varliktan kesilir: gercek alinan miktari oku.
        actual = asset_balance(symbol.split("_")[0]) or qty
        st["position"] = {
            "symbol": symbol, "qty": actual, "entry": px,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "entry_ts": time.time(),
            "tp": round(px * (1 + TAKE_PROFIT), 6),
            "sl": round(px * (1 - STOP_LOSS), 6),
            "order_id": body.get("orderId") or body.get("id"),
            "cost": round(px * qty, 4),
        }
        st["fees_paid"] = round(float(st.get("fees_paid", 0)) + px * qty * 0.001, 4)
        _save(st)
    return {**res, "qty": qty, "price": px}


def sell(symbol: str, qty: float, reason: str = "manuel") -> dict[str, Any]:
    # Komisyon ve stepSize nedeniyle adet ile satis reddedilebilir.
    # quoteOrderQty (TL tutari ile piyasa satis) her zaman calisir.
    px = price(symbol) or 0
    actual = asset_balance(symbol.split("_")[0])
    if actual > 0:
        qty = min(qty, actual)
    res: dict[str, Any]
    if px and qty > 0:
        quote = round(px * qty * 0.9995, 4)
        payload = {"symbol": symbol, "side": 1, "type": 2, "quoteOrderQty": str(quote)}
        ok, data = _request("/open/v1/orders", payload, signed=True, method="POST")
        if ok and isinstance(data, dict) and data.get("code") in (0, None):
            res = {"ok": True, "data": data}
        else:
            res = {"ok": False, "reason": f"quoteOrderQty: {str(data)[:150]}"}
    else:
        res = {"ok": False, "reason": "fiyat veya bakiye yok"}
    if res.get("ok"):
        st = _load()
        hist = st.get("history", [])
        pos = st.get("position") or {}
        if pos:
            now_px = price(symbol) or float(pos.get("entry", 0))
            entry = float(pos.get("entry", 0))
            gross = (now_px - entry) * qty
            fee = now_px * qty * 0.001 + entry * qty * 0.001
            net = gross - fee
            st["fees_paid"] = round(float(st.get("fees_paid", 0)) + now_px * qty * 0.001, 4)
            hist.append({
                **pos,
                "exit": now_px, "gross_pnl": round(gross, 4),
                "fee": round(fee, 4), "net_pnl": round(net, 4),
                "pnl": round(net, 4),
                "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_sec": round(time.time() - float(pos.get("entry_ts", time.time())), 0),
                "reason": reason,
            })
            st["history"] = hist[-20:]
            st["realized_pnl"] = round(sum(float(h.get("net_pnl", 0)) for h in hist), 4)
        st.pop("position", None)
        _save(st)
    return res


def kill_switch() -> bool:
    if STOP_FILE.exists():
        return True
    st = _load()
    if (float(st.get("realized_pnl", 0)) <= -MAX_LOSS_TRY or
            len(st.get("history", [])) >= MAX_TRADES):
        return True
    # ADIM 2 frenleri
    try:
        from ui import risk_brakes

        risk_brakes.update_from_history(st.get("history", []))
        daily, _ = risk_brakes.daily_loss_breached()
        dd, _ = risk_brakes.drawdown_breached(available_try())
        if daily or dd:
            return True
    except Exception:
        pass
    return False


def brakes_block(symbol: str) -> str:
    """Yeni giriş öncesi fren kontrolü. Sebep dönür, yoksa ''. """
    try:
        from ui import risk_brakes

        st = _load()
        risk_brakes.update_from_history(st.get("history", []))
        daily, dmsg = risk_brakes.daily_loss_breached()
        if daily:
            return dmsg
        dd, dmsg2 = risk_brakes.drawdown_breached(available_try())
        if dd:
            return dmsg2
        crash, cmsg = risk_brakes.crash_detected(symbol)
        if crash:
            return cmsg
    except Exception:
        pass
    return ""


def tradeable_pairs() -> tuple[str, ...]:
    """Bakiyeye uygun (minNotional <= bakiye) tum TRY ciftlerini keşfet."""
    import urllib.request

    bal = available_try()
    try:
        with urllib.request.urlopen(
            "https://www.binance.tr/open/v1/common/symbols", timeout=12
        ) as r:
            data = json.loads(r.read().decode())
        out: list[str] = []
        for s in data.get("data", {}).get("list", []):
            sym = s.get("symbol", "")
            if not sym.endswith("_TRY") or sym == "FORM_TRY":
                continue
            for f in s.get("filters", []):
                if f.get("filterType") == "NOTIONAL":
                    if float(f.get("minNotional", 999)) <= bal + 0.5:
                        out.append(sym)
                    break
        return tuple(out[:40]) or PAIRS
    except Exception:
        return PAIRS


def _snapshot(pos: dict[str, Any] | None) -> None:
    """Anlık fiyat/kâr görüntüsünü JSONL'e yaz (grafik + denetim için)."""
    try:
        from ui.tr_monitor import append_snapshot

        if not pos:
            append_snapshot({"ts": time.time(), "event": "izleme",
                             "pnl": 0.0, "pct": 0.0, "price": None})
            return
        sym = pos.get("symbol")
        px = price(sym)
        entry = float(pos.get("entry", 0) or 0)
        qty = float(pos.get("qty", 0) or 0)
        if px and entry:
            append_snapshot({
                "ts": time.time(), "event": "pozisyon", "symbol": sym,
                "price": px, "entry": entry,
                "pnl": round((px - entry) * qty, 4),
                "pct": round((px / entry - 1) * 100, 3),
                "elapsed": round(time.time() - float(pos.get("entry_ts", time.time())), 0),
            })
    except Exception:
        pass


def cycle() -> list[str]:
    """Tek tarama turu. Yaptığı aksiyonları döndürür (değer sızdırmaz)."""
    logs: list[str] = []
    if kill_switch():
        return ["KILL SWITCH: kayıp/sayı sınırı aşıldı, duruyorum"]
    st = _load()
    pos = st.get("position")
    if pos:
        sym = pos["symbol"]
        px = price(sym)
        if px:
            entry = float(pos["entry"])
            ret = (px - entry) / entry
            peak = max(float(pos.get("peak", entry)), px)
            pos["peak"] = peak
            peak_ret = (peak - entry) / entry
            base_sl = float(pos.get("sl", entry * (1 - STOP_LOSS)))
            # Kar kilitleri: once komisyonu kurtar, sonra zirveden trail et.
            if peak_ret >= BREAKEVEN:
                effective_sl = max(base_sl, entry * (1 + BREAKEVEN))
            else:
                effective_sl = base_sl
            if peak_ret >= TRAIL_ACTIVATE:
                effective_sl = max(effective_sl, peak * (1 - TRAIL_DISTANCE))
            pos["effective_sl"] = round(effective_sl, 8)
            st["position"] = pos
            _save(st)
            _snapshot(pos)
            if ret >= TAKE_PROFIT:
                res = sell(sym, float(pos["qty"]), "kar hedefi")
                logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} "
                            f"getiri={ret*100:+.2f}% neden=kar hedefi")
                return logs
            if ret <= STOP_LOSS * -1 and peak_ret < BREAKEVEN:
                res = sell(sym, float(pos["qty"]), "stop loss")
                logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} "
                            f"getiri={ret*100:+.2f}% neden=stop loss")
                return logs
            if px <= effective_sl and peak_ret >= BREAKEVEN:
                res = sell(sym, float(pos["qty"]), "trailing/breakeven")
                logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} "
                            f"getiri={ret*100:+.2f}% neden=trailing/breakeven")
                return logs
            held = time.time() - float(pos.get("entry_ts", time.time()))
            if held >= MAX_HOLD_SEC:
                res = sell(sym, float(pos["qty"]), "zaman/sermaye serbest")
                logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} "
                            f"getiri={ret*100:+.2f}% neden=zaman ({int(held//60)} dk)")
                return logs
            logs.append(
                f"Pozisyon {sym}: {ret*100:+.2f}% · zirve {peak_ret*100:+.2f}% · "
                f"kilit stop {effective_sl:,.5f} · hedef +{TAKE_PROFIT*100:.2f}%"
            )
            return logs
    _snapshot(None)
    best = None
    for sym in tradeable_pairs():
        s = signal(sym)
        if s.get("decision") == "AL":
            best = (sym, s)
            break
        logs.append(f"{sym}: {s.get('decision')} RSI={s.get('rsi', '—')}")
    if best:
        sym, s = best
        brake = brakes_block(sym)
        if brake:
            logs.append(f"AL ENGELLENDİ — FREN: {brake}")
            return logs
        res = buy(sym)
        logs.append(f"AL {sym} {'OK' if res.get('ok') else 'HATA'} rsi={s.get('rsi')} "
                    f"fiyat={s.get('price')} miktar={res.get('qty')}")
    return logs
