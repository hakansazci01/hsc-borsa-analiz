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
import streamlit as st

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
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    rsi = quant_lab.rsi(c, 14)
    mid = c.rolling(BB_PERIOD).mean()
    sd = c.rolling(BB_PERIOD).std()
    lower = mid - BB_STD * sd
    # ATR(14) — volatilite filtresi için (yüzde)
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    price = float(c.iloc[-1])
    ref = float(c.iloc[-25]) if len(c) > 25 else float(c.iloc[0])
    return {
        "df": df,
        "price": price,
        "rsi": float(rsi.iloc[-1]),
        "lower": float(lower.iloc[-1]),
        "low1h": float(l.tail(24).min()),
        "atr": atr,
        "atr_pct": round(atr / price * 100, 3) if price else 0.0,
        "drop_pct": round(max(0.0, (ref - price) / ref * 100), 3) if ref else 0.0,
        "vol_ratio": round(float(v.iloc[-1]) / float(v.tail(20).mean()), 2)
                     if float(v.tail(20).mean()) else 0.0,
    }


def rsi_points(rsi: float) -> float:
    """RSI 20→30, 35→10, 50→0 puan (lineer)."""
    if rsi <= 20:
        return 30.0
    if rsi <= 35:
        return 30.0 - (rsi - 20) * (20.0 / 15.0)
    if rsi <= 50:
        return 10.0 - (rsi - 35) * (10.0 / 15.0)
    return 0.0


def drop_points(drop_pct: float) -> float:
    """Son 1s %3 düşüş→30, %1 düşüş→10 puan (lineer)."""
    if drop_pct <= 0:
        return 0.0
    if drop_pct <= 1:
        return drop_pct * 10.0
    if drop_pct <= 3:
        return 10.0 + (drop_pct - 1) * 10.0
    return 30.0


def volatility_position(atr_pct: float) -> tuple[float, str]:
    """ATR% filtresi — hareketsiz/çok oynak alma, orta riskte pozisyon küçült."""
    if atr_pct < 0.5:
        return 0.0, f"ATR %{atr_pct:.2f} < %0.5 — HAREKETSİZ, ALMA"
    if atr_pct <= 2.0:
        return 0.10, f"ATR %{atr_pct:.2f} — NORMAL %10"
    if atr_pct <= 4.0:
        return 0.07, f"ATR %{atr_pct:.2f} — YÜKSEK RİSK, %7'ye küçült"
    return 0.0, f"ATR %{atr_pct:.2f} > %4 — ÇOK OYNAK, ALMA"


@st.cache_data(ttl=60, show_spinner=False)
def scan(symbols: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    """8 coin'e 0-100 puan — en yüksek seçilir, en düşük asla alınmaz (60 sn cache)."""
    rows: list[dict[str, Any]] = []
    for s in symbols:
        ind = indicators(s)
        if not ind:
            continue
        rp = rsi_points(ind["rsi"])
        dp = drop_points(ind["drop_pct"])
        vp = 20.0 if ind["vol_ratio"] > 1.0 else 0.0
        bp = 20.0 if ind["price"] <= ind["lower"] * 1.001 else 0.0
        score = round(rp + dp + vp + bp, 1)
        pos_pct, vol_reason = volatility_position(ind["atr_pct"])
        rows.append({
            "symbol": s, "score": score,
            "rsi_puan": round(rp, 1), "dusur_puan": round(dp, 1),
            "hacim_puan": vp, "bb_puan": bp,
            "rsi": round(ind["rsi"], 1), "dus_pct": ind["drop_pct"],
            "vol_oran": ind["vol_ratio"], "atr_pct": ind["atr_pct"],
            "pozisyon_pct": pos_pct, "vol_not": vol_reason,
            "price": ind["price"], "lower": round(ind["lower"], 2),
            "low1h": ind["low1h"],
        })
    rows.sort(key=lambda r: (r["score"], r["vol_oran"]), reverse=True)
    return rows


def buy_signal(ind: dict[str, Any]) -> tuple[bool, str]:
    near_low = ind["price"] <= ind["low1h"] * 1.005
    oversold = ind["rsi"] < RSI_BUY
    bb = ind["price"] <= ind["lower"] * 1.01
    why = (f"1s dip={ind['low1h']:.2f} şu an={ind['price']:.2f} "
           f"RSI={ind['rsi']:.1f} BBalt={ind['lower']:.2f}")
    return (near_low and oversold and bb), why


def sell_signal(ind: dict[str, Any], entry: float, atr_stop: float | None = None) -> str | None:
    """Geriye uyumlu basit kontrol (backtest/eskiler). Canlıda sell_decision kullanılır."""
    gain = (ind["price"] - entry) / entry if entry else 0.0
    if gain >= TAKE_PCT:
        return f"hedef kâr %{gain*100:.2f} ≥ %{TAKE_PCT*100:.1f}"
    if ind["rsi"] > RSI_SELL:
        return f"RSI {ind['rsi']:.1f} > {RSI_SELL:.0f} aşırı alınmış"
    if atr_stop and ind["price"] <= atr_stop:
        return f"ATR stop {atr_stop:.2f} değdi"
    return None


# --- AKILLI SATIŞ: kademeli + trailing + zaman stopu ---
FIRST_TAKE_PCT = 0.008       # %0.8 → yarısı
FIRST_TAKE_RATIO = 0.5
TRAIL_BE_GAIN = 0.008        # %0.8 → stop girişe (breakeven)
TRAIL_LOCK_GAIN = 0.012      # %1.2 → stop %0.5 kara
TRAIL_LOCK_PCT = 0.005
TIME_STOP_H = 4.0            # 4 saatte kâr yoksa kapat
TIME_EXT_H = 6.0             # 4 saatte %0.5+ varsa 2 saat daha
TIME_MIN_GAIN = 0.005


def sell_decision(pos: dict[str, Any], ind: dict[str, Any],
                  atr_stop: float | None = None,
                  now_ts: float | None = None) -> tuple[str, float, str, float]:
    """(aksiyon, oran, neden, yeni_locked_sl) — kademeli/trailing/zaman stopu."""
    import time as _t

    entry = float(pos.get("entry", 0) or 0)
    price = float(ind["price"])
    gain = (price - entry) / entry if entry else 0.0
    now = now_ts if now_ts is not None else _t.time()
    hours = (now - float(pos.get("entry_ts", now))) / 3600.0
    locked = float(pos.get("locked_sl", 0) or 0)

    eps = 1e-9  # 100.8/100 gibi tam eşiklerde floating point kaybını önle
    if gain >= TRAIL_LOCK_GAIN - eps:
        locked = max(locked, round(entry * (1 + TRAIL_LOCK_PCT), 8))
    elif gain >= TRAIL_BE_GAIN - eps:
        locked = max(locked, entry)

    if gain >= TAKE_PCT - eps:  # %1.5 → kalan %50
        return "FULL", 1.0, f"kademeli 2/2: kâr %{gain*100:.2f} ≥ %1.5 — tam kapanış", locked
    if gain >= FIRST_TAKE_PCT - eps and not pos.get("first_take_done"):
        return "PARTIAL", FIRST_TAKE_RATIO, \
            f"kademeli 1/2: kâr %{gain*100:.2f} ≥ %0.8 — yarısat", locked
    if locked and price <= locked:
        return "FULL", 1.0, f"trailing stop {locked:.4f} değdi (kâr %{gain*100:.2f})", locked
    if ind["rsi"] > RSI_SELL:
        return "FULL", 1.0, f"RSI {ind['rsi']:.1f} > 70", locked
    if atr_stop and price <= atr_stop:
        return "FULL", 1.0, f"ATR stop {atr_stop:.4f} değdi", locked
    if hours >= TIME_STOP_H and gain <= 0:
        return "FULL", 1.0, f"zaman stopu: {hours:.1f}s açık, kâr yok — sermaye boşa bağlı", locked
    if hours >= TIME_EXT_H and 0 < gain < TIME_MIN_GAIN:
        return "FULL", 1.0, \
            f"zaman stopu (uzatma): {hours:.1f}s, kâr %{gain*100:.2f} <%0.5", locked
    return "HOLD", 0.0, "", locked


def _qty(cap_try: float, px: float, step: float) -> float:
    raw = cap_try / px
    return round(int(raw / step + 0.999999) * step, 8) if step else round(raw, 8)


def cycle() -> list[str]:
    """Tek tarama turu — mevcut emir/fren modüllerini kullanır, EMA50'ye dokunmaz."""
    from ui import market_regime, tr_scalper as t

    from ui import strategy_mode as sm

    logs: list[str] = []
    t._beat(int(t._load().get("cycle_count", 0)) + 1)
    _st = t._load()
    t._save({**_st, "cycle_count": int(_st.get("cycle_count", 0)) + 1})
    if t.kill_switch():
        return ["KILL SWITCH: yeni işlem yok"]
    _guard = sm.day_guard()
    if _guard:
        return [_guard]
    _mode, _reg = sm.current_auto()
    _bear_cap, _rsi_max = sm.bear_params(_reg)
    logs.append(f"REJİM: {_reg} — MOD: {sm.LABELS[_mode]}"
                + (f" (AYI: %{_bear_cap*100:.0f} pozisyon, RSI<{_rsi_max:.0f})"
                   if _bear_cap else ""))

    st = t._load()
    pos = st.get("position")
    if pos:
        sym = pos["symbol"]
        ind = indicators(sym)
        if not ind:
            return [f"{sym}: 1s veri yok — pozisyon korunuyor"]
        entry = float(pos.get("entry", 0))
        atr = market_regime.atr_stop(ind["price"], sym)
        action, ratio, why, locked = sell_decision(pos, ind, atr["stop"])
        if locked > float(pos.get("locked_sl", 0) or 0):
            pos["locked_sl"] = locked
            logs.append(f"TRAILING STOP YÜKSELTİLDİ: {locked:.4f} "
                        f"(giriş {entry:.4f}) — zarar yok, kâr korunuyor")
        if action == "PARTIAL":
            flt = t._filters(sym)
            half = max(_qty(float(pos["qty"]) * ratio, ind["price"],
                            flt["step"] or 0.00000001), flt["min_qty"])
            res = t.sell(sym, half, f"{MOD_ADI}: {why}", partial=True)
            if res.get("ok"):
                np = t._load().get("position") or pos
                np["first_take_done"] = True
                if locked:
                    np["locked_sl"] = locked
                t._save({**t._load(), "position": np})
                sm.day_record(float(res.get("net", 0) or 0))
            logs.append(f"KDEMELİ SATIŞ 1/2 {sym} {'OK' if res.get('ok') else 'HATA'} "
                        f"· {half} adet · {why}")
            return logs
        if action == "FULL":
            res = t.sell(sym, float(pos["qty"]), f"{MOD_ADI}: {why}")
            if res.get("ok"):
                sm.day_record(float(res.get("net", 0) or 0))
            logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} — {why}")
            return logs
        # DCA: %1 düşüşte bir %10 kademe daha (en fazla 3)
        last = float(pos.get("last_buy", entry) or entry)
        ladder = int(pos.get("ladders", 0) or 0)
        if ladder < MAX_LADDERS and ind["price"] <= last * (1 - DCA_DROP):
            _vpct, _vnot = volatility_position(ind["atr_pct"])
            _bal = t.available_try()
            cap = min(t.position_size_try(_bal, sym), _bal * _vpct) if _vpct > 0 else 0
            if cap <= 0:
                return logs + [f"DCA ALINMADI: {_vnot}"]
            logs.append(f"VOLATİLİTE FİLTRESİ (DCA): {sym} — {_vnot}")
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

    # KORELASYON: aynı anda en fazla 1 pozisyon — 1. kapanmadan 2. açılmaz
    extra = t._load().get("positions", [])
    if extra:
        return logs + [f"KORELASYON: {len(extra)} açık pozisyon var — "
                       "1. pozisyon kapanmadan yeni coin açılmaz"]
    rows = scan(list(t.SYMBOLS))
    if not rows:
        return ["1s veri yok — fırsat taraması yapılamadı"]
    logs.append("SKOR TABLOSU (0-100): " + " | ".join(
        f"{r['symbol']} {r['score']} (RSI {r['rsi_puan']}+düşüş {r['dusur_puan']}"
        f"+hacim {r['hacim_puan']}+BB {r['bb_puan']}) ATR%{r['atr_pct']}"
        for r in rows[:8]))
    best = rows[0]
    logs.append(f"VOLATİLİTE FİLTRESİ: {best['symbol']} — {best['vol_not']}")
    if best["pozisyon_pct"] <= 0:
        return logs + [f"ALIM YOK: {best['vol_not']}"]
    ok, why = buy_signal(best)
    if _bear_cap and best["rsi"] >= _rsi_max:
        ok = False
        why += (f" · AYI rejiminde RSI<{_rsi_max:.0f} gerekli "
                f"(şu an {best['rsi']:.1f}) — az işlem")
    if not ok:
        return logs + [f"ALIM KOŞULU YOK: {best['symbol']} — {why}"]
    sym = best["symbol"]
    brake = t.brakes_block(sym)
    if brake:
        return logs + [f"FREN ({sym}): {brake}"]
    bal = t.available_try()
    cap = min(t.position_size_try(bal, sym), bal * best["pozisyon_pct"])
    if _bear_cap:
        cap = min(cap, bal * _bear_cap)
    logs.append(f"POZİSYON: {cap / bal * 100:.0f}% · ₺{cap:.2f} "
                f"(bakiye ₺{bal:.2f}{', AYI %7 üst sınır' if _bear_cap else ''})")
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
        c, h, l = df["Close"], df["High"], df["Low"]
        rsi = quant_lab.rsi(c, 14)
        mid = c.rolling(BB_PERIOD).mean()
        sd = c.rolling(BB_PERIOD).std()
        lower = mid - BB_STD * sd
        tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr_pct_series = tr.rolling(14).mean() / c * 100
        pos: dict[str, Any] | None = None
        for i in range(BB_PERIOD + 5, len(c) - 1):
            px = float(c.iloc[i])
            r = float(rsi.iloc[i])
            lo = float(lower.iloc[i])
            low24 = float(df["Low"].iloc[max(0, i - 23):i + 1].min())
            ap = float(atr_pct_series.iloc[i]) if atr_pct_series.iloc[i] == atr_pct_series.iloc[i] else 0.0
            if pos is None:
                # VOLATİLİTE FİLTRESİ backtest'te de aktif: %0.5 altı / %4 üstü alınmaz
                if 0.5 <= ap <= 4.0 and px <= low24 * 1.005 and r < RSI_BUY and px <= lo * 1.01:
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
