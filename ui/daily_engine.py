"""
ADIM 1 — Canlı motor, backtest'te kazanan GÜNLÜK EMA50 pullback stratejisini kullanır.
1 dakikalık scalper tamamen kapatıldı (bu modül onun yerine geçer).

Strateji (quant_lab.signals "pullback" ile BİRİK):
  EMA50 = 50 günlük üstel hareketli ortalama
  AL   : Close > EMA50  VE  Low <= EMA50  VE  önceki Close <= önceki EMA50
  SAT  : Close < EMA50 * 0.97  VEYA  90 günden fazla tutuldu
 pozisyon boyutu: bakiye %15 (₺50–100), tek pozisyon, sağlıklı frenler aktif.
"""

from __future__ import annotations

import json
import time
from typing import Any

from ui import quant_lab, tr_scalper, risk_brakes
from ui import auth

STATE = auth.USERS_DIR / "tr_daily_state.json"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
           "LINKUSDT", "BNBUSDT", "SOLUSDT")
MAX_HOLD_DAYS = 90
EXIT_BELOW_EMA = 0.97


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def ema50(symbol: str) -> tuple[float, float] | None:
    frame = quant_lab.fetch(symbol, "1d", 200)
    if frame is None or len(frame) < 60:
        return None
    c = frame["Close"]
    m = quant_lab.ema(c, 50)
    return float(c.iloc[-1]), float(m.iloc[-1])


def entry_signal(symbol: str) -> tuple[bool, str]:
    """quant_lab.signals('pullback',(50,)) ile AYNI kural — son mum."""
    frame = quant_lab.fetch(symbol, "1d", 200)
    if frame is None or len(frame) < 60:
        return False, "veri yok"
    ent, _ = quant_lab.signals(frame, "pullback", (50,))
    if ent.iloc[-1]:
        return True, "günlük EMA50 pullback (gerçek sinyal)"
    c, m = float(frame["Close"].iloc[-1]), float(quant_lab.ema(frame["Close"], 50).iloc[-1])
    return False, f"fiyat {c:.4f} / EMA50 {m:.4f} — kirilim yok"


def buy(symbol: str) -> dict[str, Any]:
    px = tr_scalper.price(symbol)
    if not px:
        return {"ok": False, "reason": "fiyat yok"}
    bal = tr_scalper.available_try()
    budget = min(100.0, max(50.0, bal * 0.15))
    flt = tr_scalper._filters(symbol)
    step = flt["step"] or 0.00000001
    need = max(budget, flt["min_notional"] + 0.5) / px
    qty = round(int(need / step + 0.999999) * step, 8)
    qty = max(qty, flt["min_qty"])
    res = tr_scalper._order(symbol, 0, qty)  # doğrudan imzalı emir (scalper.buy kapalı)
    if res.get("ok"):
        body = (res.get("data") or {}).get("data") or {}
        st = _load()
        st["position"] = {
            "symbol": symbol, "qty": qty, "entry": px,
            "entry_ts": time.time(), "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "order_id": body.get("orderId") or body.get("id"),
            "cost": round(px * qty, 4),
        }
        _save(st)
    return res


def sell(symbol: str, qty: float, reason: str) -> dict[str, Any]:
    res = tr_scalper.sell(symbol, qty, reason)  # quoteOrderQty ile güvenli satış (satış serbest)
    return res


def cycle() -> list[str]:
    logs: list[str] = []
    if tr_scalper.STOP_FILE.exists():
        return ["STOP dosyası var — motor kapalı"]
    st = _load()
    pos = st.get("position")
    if pos:
        sym = pos["symbol"]
        vals = ema50(sym)
        if vals:
            px, ma = vals
            ret = (px - float(pos["entry"])) / float(pos["entry"])
            held_days = (time.time() - float(pos["entry_ts"])) / 86400
            if px < ma * EXIT_BELOW_EMA:
                res = sell(sym, float(pos["qty"]), "günlük EMA50 altı (%-3)")
                logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} neden=EMA50 altı")
                return logs
            if held_days >= MAX_HOLD_DAYS:
                res = sell(sym, float(pos["qty"]), "90 gün zaman sınırı")
                logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} neden=zaman")
                return logs
            logs.append(f"Pozisyon {sym}: {ret*100:+.2f}% · EMA50 {ma:.4f} · {held_days:.0f} gün")
        return logs
    for sym in SYMBOLS:
        brake = tr_scalper.brakes_block(sym)
        if brake:
            logs.append(f"FREN ({sym}): {brake}")
            continue
        ok, why = entry_signal(sym)
        if ok:
            res = buy(sym)
            logs.append(f"AL {sym} {'OK' if res.get('ok') else 'HATA'} neden={why}")
            return logs
        logs.append(f"{sym}: giriş yok — {why}")
    return logs
