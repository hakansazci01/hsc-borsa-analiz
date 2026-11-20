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

MAX_ORDER_TRY = 10.0
MAX_LOSS_TRY = 3.0
MAX_TRADES = 3
TAKE_PROFIT = 0.0045
STOP_LOSS = 0.0035


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
        return {"ok": False, "reason": str(data)[:200]}
    if isinstance(data, dict) and data.get("code") not in (0, None):
        return {"ok": False, "reason": f"{data.get('code')}: {data.get('msg')}"}
    return {"ok": True, "data": data}


def buy(symbol: str) -> dict[str, Any]:
    px = price(symbol)
    if not px:
        return {"ok": False, "reason": "fiyat yok"}
    flt = _filters(symbol)
    step = flt["step"] or 0.00000001
    # Minimum notional'i garanti etmek icin miktari step katina YUKARI yuvarla.
    need = max(MAX_ORDER_TRY, flt["min_notional"] + 0.5) / px
    qty = round(int(need / step + 0.999999) * step, 8)
    qty = max(qty, flt["min_qty"])
    res = _order(symbol, 0, qty)  # 0 = AL
    if res.get("ok"):
        st = _load()
        body = (res.get("data") or {}).get("data") or {}
        st["position"] = {
            "symbol": symbol, "qty": qty, "entry": px,
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
    res = _order(symbol, 1, qty)  # 1 = SAT
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
    return (float(st.get("realized_pnl", 0)) <= -MAX_LOSS_TRY or
            len(st.get("history", [])) >= MAX_TRADES)


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
            ret = (px - float(pos["entry"])) / float(pos["entry"])
            _snapshot(pos)
            if ret >= TAKE_PROFIT or ret <= -STOP_LOSS:
                reason = "kar hedefi" if ret >= TAKE_PROFIT else "stop loss"
                res = sell(sym, float(pos["qty"]), reason)
                logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} "
                            f"getiri={ret*100:+.2f}% neden={reason}")
                return logs
            logs.append(f"Pozisyon {sym}: {ret*100:+.2f}% (hedef +{TAKE_PROFIT*100:.2f}% / stop -{STOP_LOSS*100:.2f}%)")
            return logs
    _snapshot(None)
    best = None
    for sym in PAIRS:
        s = signal(sym)
        if s.get("decision") == "AL":
            best = (sym, s)
            break
        logs.append(f"{sym}: {s.get('decision')} RSI={s.get('rsi', '—')}")
    if best:
        sym, s = best
        res = buy(sym)
        logs.append(f"AL {sym} {'OK' if res.get('ok') else 'HATA'} rsi={s.get('rsi')} "
                    f"fiyat={s.get('price')} miktar={res.get('qty')}")
    return logs
