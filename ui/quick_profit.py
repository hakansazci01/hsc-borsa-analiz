"""SÜREKLİ KÜÇÜK KAR — Grid + DCA + Mean Reversion (EMA50'nin YANINDA).

Yeni strateji EMA50 Pullback'i SİLMİYOR; strategy_mode ile seçilir.
Kurallar:
  AL  : 1s en düşüğe yakın + RSI(1s)<35 + Bollinger alt bandına yakın/altında
  SAT : kâr %1.5  |  RSI>70  |  ATR stop
  DCA : %1 düşüşte %10'luk ek alım, en fazla 3 kademe
  KORUMA: günlük %10, trailing %15, kâr kilidi +50 TL, 3 ardışık zarar (ortak modüller)
  KOMİSYON: %1.5 hedef = çift yön %0.2 komisyonun 7.5 katı, asla %0.5 altına inmez
"""

from __future__ import annotations

from typing import Any

import pandas as pd

MOD_ADI = "SÜREKLİ KÜÇÜK KAR"
RSI_BUY = 35.0
RSI_SELL = 70.0
TAKE_PCT = 0.015        # %1.5 — komisyonun 7.5 katı
BB_PERIOD, BB_STD = 20, 2.0
DCA_DROP = 0.01         # %1 düşüşte kademe
MAX_LADDERS = 3
MIN_TAKE_PCT = 0.005    # komisyona giriş yok
SLIPPAGE = 0.005
FEE = 0.001


def indicators(symbol: str, tf: str = "1h", limit: int = 120) -> dict[str, Any] | None:
    from ui import quant_lab

    df = quant_lab.fetch(symbol, tf, limit)
    if df is None or len(df) < BB_PERIOD + 10:
        return None
    c = df["Close"]
    rsi = quant_lab.rsi(c, 14)
    mid = c.rolling(BB_PERIOD).mean()
    sd = c.rolling(BB_PERIOD).std()
    lower = mid - BB_STD * sd
    return {
        "df": df,
        "price": float(c.iloc[-1]),
        "rsi": float(rsi.iloc[-1]),
        "lower": float(lower.iloc[-1]),
        "low1h": float(df["Low"].tail(24).min()),
    }


def scan(symbols: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    """8 coin'i tara — en fırsatlı (en çok düşmüş / RSI en düşük / BB altı) ilk sırada."""
    rows: list[dict[str, Any]] = []
    for s in symbols:
        ind = indicators(s)
        if not ind:
            continue
        bb_gap = (ind["price"] - ind["lower"]) / ind["price"]
        score = 100.0 - ind["rsi"] - bb_gap * 500.0
        rows.append({
            "symbol": s, "score": round(score, 1),
            "price": ind["price"], "rsi": round(ind["rsi"], 1),
            "lower": round(ind["lower"], 2), "low1h": ind["low1h"],
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def buy_signal(ind: dict[str, Any]) -> tuple[bool, str]:
    near_low = ind["price"] <= ind["low1h"] * 1.005
    oversold = ind["rsi"] < RSI_BUY
    bb = ind["price"] <= ind["lower"] * 1.01
    why = (f"1s dip={ind['low1h']:.2f} şu an={ind['price']:.2f} "
           f"RSI={ind['rsi']:.1f} BBalt={ind['lower']:.2f}")
    return (near_low and oversold and bb), why


def sell_signal(ind: dict[str, Any], entry: float, atr_stop: float | None = None) -> str | None:
    gain = (ind["price"] - entry) / entry if entry else 0.0
    if gain >= TAKE_PCT:
        return f"hedef kâr %{gain*100:.2f} ≥ %{TAKE_PCT*100:.1f}"
    if ind["rsi"] > RSI_SELL:
        return f"RSI {ind['rsi']:.1f} > {RSI_SELL:.0f} aşırı alınmış"
    if atr_stop and ind["price"] <= atr_stop:
        return f"ATR stop {atr_stop:.2f} değdi"
    return None


def _qty(cap_try: float, px: float, step: float) -> float:
    raw = cap_try / px
    return round(int(raw / step + 0.999999) * step, 8) if step else round(raw, 8)


def cycle() -> list[str]:
    """Tek tarama turu — mevcut emir/fren modüllerini kullanır, EMA50'ye dokunmaz."""
    from ui import market_regime, tr_scalper as t

    logs: list[str] = []
    t._beat(int(t._load().get("cycle_count", 0)) + 1)
    _st = t._load()
    t._save({**_st, "cycle_count": int(_st.get("cycle_count", 0)) + 1})
    if t.kill_switch():
        return ["KILL SWITCH: yeni işlem yok"]

    st = t._load()
    pos = st.get("position")
    if pos:
        sym = pos["symbol"]
        ind = indicators(sym)
        if not ind:
            return [f"{sym}: 1s veri yok — pozisyon korunuyor"]
        entry = float(pos.get("entry", 0))
        atr = market_regime.atr_stop(ind["price"], sym)
        why = sell_signal(ind, entry, atr["stop"])
        if why:
            res = t.sell(sym, float(pos["qty"]), f"{MOD_ADI}: {why}")
            logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} — {why}")
            return logs
        # DCA: %1 düşüşte bir %10 kademe daha (en fazla 3)
        last = float(pos.get("last_buy", entry) or entry)
        ladder = int(pos.get("ladders", 0) or 0)
        if ladder < MAX_LADDERS and ind["price"] <= last * (1 - DCA_DROP):
            cap = t.position_size_try(t.available_try(), sym)
            flt = t._filters(sym)
            qty = _qty(cap, ind["price"], flt["step"] or 0.00000001)
            qty = max(qty, flt["min_qty"])
            res = t._order(sym, 0, qty)
            if res.get("ok"):
                old_qty = float(pos.get("qty", 0))
                pos["entry"] = round((entry * old_qty + ind["price"] * qty) / (old_qty + qty), 8)
                pos["qty"] = round(old_qty + qty, 8)
                pos["ladders"] = ladder + 1
                pos["last_buy"] = ind["price"]
                t._save({**t._load(), "position": pos})
                logs.append(f"DCA {ladder+1}/{MAX_LADDERS}: {sym} +{qty} adet @ {ind['price']:.2f}")
            else:
                logs.append(f"DCA emri reddedildi: {str(res.get('reason'))[:100]}")
        else:
            logs.append(f"Pozisyon {sym}: fiyat {ind['price']:.2f} / giriş {entry:.2f} · "
                        f"RSI {ind['rsi']:.1f} · kademe {ladder}/{MAX_LADDERS} — bekleniyor")
        return logs

    rows = scan(list(t.SYMBOLS))
    if not rows:
        return ["1s veri yok — fırsat taraması yapılamadı"]
    logs.append("TARAMA (en fırsatlı →): " + " | ".join(
        f"{r['symbol']} skor {r['score']} RSI {r['rsi']}" for r in rows[:8]))
    best = rows[0]
    ok, why = buy_signal(best)
    if not ok:
        return logs + [f"ALIM KOŞULU YOK: {best['symbol']} — {why}"]
    sym = best["symbol"]
    brake = t.brakes_block(sym)
    if brake:
        return logs + [f"FREN ({sym}): {brake}"]
    cap = t.position_size_try(t.available_try(), sym)   # dinamik %10 — limit değişmedi
    if cap <= 0:
        return logs + ["bakiye yetersiz"]
    flt = t._filters(sym)
    qty = _qty(cap, best["price"], flt["step"] or 0.00000001)
    qty = max(qty, flt["min_qty"])
    res = t._order(sym, 0, qty)
    if not res.get("ok"):
        return logs + [f"ALIM HATA ({sym}): {str(res.get('reason'))[:120]}"]
    body = ((res.get("data") or {}).get("data") or {})
    t._save({**t._load(), "position": {
        "symbol": sym, "qty": qty, "entry": best["price"],
        "entry_ts": __import__("time").time(),
        "time": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "order_id": body.get("orderId") or body.get("id"),
        "cost": round(best["price"] * qty, 4), "strategy": MOD_ADI,
        "ladders": 0, "last_buy": best["price"],
        "atr_stop": market_regime.atr_stop(best["price"], sym)["stop"],
    }, "mode": MOD_ADI})
    try:
        from ui import disaster_recovery
        disaster_recovery.backup("hızlı kâr alımı")
    except Exception:
        pass
    try:
        from ui.autonomous_ops import _send
        _send("HSC ALIM YAPILDI", f"{MOD_ADI} ALIM — {sym}\nFiyat: {best['price']}\nAdet: {qty}")
    except Exception:
        pass
    logs.append(f"ALIM {sym} OK · {qty} adet @ {best['price']:.2f} · {why}")
    return logs


def backtest(days: int = 30, symbols: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    """Geçmiş 30 gün, 1s mumlar — slippage %0.5 + çift yön komisyon %0.2 dahil."""
    from ui import quant_lab, tr_scalper as t

    syms = list(symbols) if symbols else list(t.SYMBOLS)
    trades: list[dict[str, Any]] = []
    for sym in syms:
        df = quant_lab.fetch(sym, "1h", days * 24 + 40)
        if df is None or len(df) < BB_PERIOD + 10:
            continue
        c = df["Close"]
        rsi = quant_lab.rsi(c, 14)
        mid = c.rolling(BB_PERIOD).mean()
        sd = c.rolling(BB_PERIOD).std()
        lower = mid - BB_STD * sd
        pos: dict[str, Any] | None = None
        for i in range(BB_PERIOD + 5, len(c) - 1):
            px = float(c.iloc[i])
            r = float(rsi.iloc[i])
            lo = float(lower.iloc[i])
            low24 = float(df["Low"].iloc[max(0, i - 23):i + 1].min())
            if pos is None:
                if px <= low24 * 1.005 and r < RSI_BUY and px <= lo * 1.01:
                    pos = {"entry": px * (1 + SLIPPAGE), "units": 1,
                           "ladders": 0, "last": px}
                continue
            gain = (px - pos["entry"]) / pos["entry"]
            if gain >= TAKE_PCT or r > RSI_SELL:
                ret = (px * (1 - SLIPPAGE) - pos["entry"]) / pos["entry"] - 2 * FEE
                trades.append({"symbol": sym, "ret": round(ret * 100, 3), "bar": i,
                               "ladders": pos["ladders"]})
                pos = None
                continue
            if pos["ladders"] < MAX_LADDERS and px <= pos["last"] * (1 - DCA_DROP):
                e = pos["entry"] * pos["units"] + px * (1 + SLIPPAGE)
                pos["units"] += 1
                pos["entry"] = e / pos["units"]
                pos["ladders"] += 1
                pos["last"] = px
    wins = [x for x in trades if x["ret"] > 0]
    total = round(sum(x["ret"] for x in trades), 2)
    return {
        "gun": days, "islem": len(trades), "karli": len(wins),
        "zararli": len(trades) - len(wins),
        "kazanma_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "toplam_kar_pct": total,
        "hedef": f"%{TAKE_PCT*100:.1f}", "komisyon": "çift yön %0.2",
        "slippage": f"%{SLIPPAGE*100:.1f}",
    }
