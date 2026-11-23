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
# 30 coin — 3 kademe (ZEC_TRY Binance TR'de listeli değil -> XLM_TRY)
TIERS: dict[str, tuple[tuple[str, ...], float]] = {
    "Güvenli": (("BTC_TRY", "ETH_TRY", "BNB_TRY", "SOL_TRY", "ADA_TRY",
                 "XRP_TRY", "DOGE_TRY", "LINK_TRY"), 0.10),
    "Hacimli": (("AVAX_TRY", "DOT_TRY", "LTC_TRY", "ATOM_TRY", "NEAR_TRY",
                 "ARB_TRY", "OP_TRY", "TRX_TRY", "TON_TRY", "SUI_TRY",
                 "APT_TRY", "INJ_TRY"), 0.10),
    "Fırsatçı": (("AAVE_TRY", "HYPE_TRY", "PEPE_TRY", "SHIB_TRY", "XLM_TRY",
                  "DASH_TRY", "APE_TRY", "MANA_TRY", "SAND_TRY", "GALA_TRY"), 0.05),
}
SYMBOLS: tuple[str, ...] = tuple(s for coins, _ in TIERS.values() for s in coins)


def should_buy(r: dict[str, Any]) -> tuple[bool, str]:
    """CANLI alım kararı — SÜREKLİ GRID.

    BB alt bandı artık ALIM ENGELİ DEĞİL; sadece skor bileşeni (scan -> bb_puan).
    Giriş: skor + RSI<45 + 1s dip + ATR aralığı. Katman 1 için %0.5 pullback
    ayrıca grid_anchor üzerinden control edilir (cycle içinde).
    """
    checks = {
        "skor": float(r.get("score", 0)) >= MIN_SCORE,
        "RSI<45": float(r.get("rsi", 100)) < 45.0,
        "1s dip": float(r.get("price", 0)) <= float(r.get("low1h", 0)) * 1.01,
        "ATR aralığı": 0.5 <= float(r.get("atr_pct", 0)) <= 4.0,
    }
    failed = [k for k, ok in checks.items() if not ok]
    detail = " · ".join(f"{k} {'OK' if ok else 'X'}" for k, ok in checks.items())
    return not failed, detail


# --------------------------------------------------------- SÜREKLİ GRID
GRID_LAYERS = 3                       # coin başına en fazla 3 alım katmanı
GRID_STEPS = (0.005, 0.010, 0.015)    # katman 1/2/3 — anchor'dan düşüş
GRID_BUY_PCT = 0.05                   # her katmanın HEDEF büyüklüğü (bakiye %5)
COIN_HARD_CAP = 0.07                  # coin başına SABİT üst limit %7 (değişmez)


def grid_anchor_update(st: dict[str, Any], symbol: str, price: float) -> tuple[dict[str, Any], float]:
    """Coin'in grid referansını (izleyen zirve) güncelle."""
    anchors = dict(st.get("grid_anchors", {}) or {})
    old = float(anchors.get(symbol, price) or price)
    anchor = max(old, float(price))   # fiyat yükselirse referans yukarı kayar
    anchors[symbol] = round(anchor, 8)
    st["grid_anchors"] = anchors
    return st, anchor


def grid_decision(pos: dict[str, Any], price: float) -> tuple[str, str]:
    """Mevcut pozisyonda yeni katman açılabilir mi? → (HOLD|ADD, neden)."""
    anchor = float(pos.get("grid_anchor") or pos.get("entry") or 0)
    layers = int(pos.get("grid_layers", 1) or 1)
    if anchor <= 0:
        return "HOLD", "grid referansı yok"
    if layers >= GRID_LAYERS:
        return "HOLD", f"{GRID_LAYERS} katman dolu — 4. alım yok, TP satışı bekleniyor"
    threshold = GRID_STEPS[layers]
    drop = (anchor - float(price)) / anchor
    if drop >= threshold:
        return ("ADD", f"KATMAN {layers+1}: fiyat {float(price):.4f} / referans "
                       f"{anchor:.8f} · düşüş %{drop*100:.2f} ≥ %{threshold*100:.1f}")
    return ("HOLD", f"KATMAN {layers+1} için %{threshold*100:.1f} düşüş gerekli "
                    f"(şu an %{drop*100:.2f})")


def _active_position(st: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Aktif pozisyonu tekil alandan veya positions listesinden oku → (pos, listede_mi)."""
    p = st.get("position")
    if p:
        return p, False
    lp = st.get("positions") or []
    return (lp[0], True) if lp else ({}, False)


def _save_active_position(pos: dict[str, Any], in_list: bool) -> None:
    """Pozisyonu hangi kapta tutuluyorsa oraya geri yaz (çift kayıt olmasın)."""
    from ui import tr_scalper as t

    cur = t._load()
    if in_list:
        lp = cur.get("positions") or []
        if lp:
            lp[0] = pos
        cur["positions"] = lp
    else:
        cur["position"] = pos
    t._save(cur)


def confidence_pct(score: float) -> float:
    """Sinyal güveniyle pozisyon: 35-50 → %5, 50-70 → %6, 70+ → %7. Üst sınır %7."""
    if score >= 70.0:
        return 0.07
    if score >= 50.0:
        return 0.06
    return 0.05


@st.cache_data(ttl=3600, show_spinner=False)
def dynamic_watchlist() -> tuple[str, ...]:
    """30 coin içinden her saat: 24h hacim + 1h mutlak değişim + düşük RSI ile Top-10."""
    from ui import quant_lab

    ranked = []
    for s in SYMBOLS:
        df = quant_lab.fetch(s, "1h", 25)
        if df is None or len(df) < 25:
            continue
        c = df["Close"]
        vol24 = float(df["Volume"].tail(24).sum())
        change1h = abs(float(c.iloc[-1]) - float(c.iloc[-2])) / float(c.iloc[-2]) * 100
        rsi = float(quant_lab.rsi(c, 14).iloc[-1])
        score = vol24 / 1e6 + change1h * 10 + max(0.0, 25 - rsi)
        ranked.append((score, s))
    ranked.sort(reverse=True)
    out = tuple(s for _, s in ranked[:10])
    return out if len(out) >= 5 else SYMBOLS[:10]


def tier_of(symbol: str) -> tuple[str, float]:
    for name, (coins, pct) in TIERS.items():
        if symbol in coins:
            return name, pct
    return "Güvenli", 0.10
RSI_BUY = 35.0
RSI_SELL = 70.0
TAKE_PCT = 0.015        # %1.5 — komisyonun 7.5 katı
BB_PERIOD, BB_STD = 20, 2.0
DCA_DROP = 0.01         # %1 düşüşte kademe (mevcut grid kademesi)
MAX_LADDERS = 3
# YENİ PORTFÖY MODU — sınırsız işlem, 5 eşzamanlı pozisyon, %5 boyut
MAX_POSITIONS = 5
POS_PCT = 0.05
MIN_SCORE = 30.0     # backtest'te kârlı bölgeyle uyumlu skor eşiği
RESCUE_DROP = 0.02      # %2 düşüşte DCA kurtarma (yarı miktar)
RESCUE_EXIT = 0.01      # ortalamanın %1 üstünde kara geçiş
RESCUE_MAX = 2          # en fazla 2 kurtarma kademesi
STOP_DROP = 0.05        # %5+ düşüşte ATR stop — inatlaşma yok
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
    # Akıllı bot göstergeleri: momentum (ROC), VWAP mesafesi, EMA9/21 kesişimi
    mom = (price - float(c.iloc[-5])) / float(c.iloc[-5]) * 100 if len(c) > 5 else 0.0
    typical = (h + l + c) / 3
    vol_sum = float(v.tail(20).sum())
    vwap = float((typical * v).tail(20).sum() / vol_sum) if vol_sum else price
    e9, e21 = quant_lab.ema(c, 9), quant_lab.ema(c, 21)
    ema_cross = bool(len(c) > 2 and e9.iloc[-1] > e21.iloc[-1] and e9.iloc[-2] <= e21.iloc[-2])
    return {
        "df": df,
        "mom": round(mom, 3),
        "vwap": round(vwap, 4),
        "vwap_dist": round((price - vwap) / vwap * 100, 3) if vwap else 0.0,
        "ema_cross": ema_cross,
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
        mp = 15.0 if ind["mom"] >= 1.0 else (10.0 if ind["mom"] >= 0.5 else 0.0)
        wp = 10.0 if ind["vwap_dist"] <= -0.2 else 0.0
        ep = 10.0 if ind["ema_cross"] else 0.0
        score = min(100.0, round(rp + dp + vp + bp + mp + wp + ep, 1))
        pos_pct, vol_reason = volatility_position(ind["atr_pct"])
        tier, tier_pct = tier_of(s)
        rows.append({
            "symbol": s, "score": score, "kademe": tier, "tier_pct": tier_pct,
            "rsi_puan": round(rp, 1), "dusur_puan": round(dp, 1),
            "hacim_puan": vp, "bb_puan": bp,
            "mom_puan": mp, "vwap_puan": wp, "ema_puan": ep,
            "mom": ind["mom"], "vwap_dist": ind["vwap_dist"],
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


def rescue_decision(avg_entry: float, price: float, rescues: int) -> tuple[str, str]:
    """DCA kurtarma: %2 düşüşte yarı kademe ekle, ortalamanın %1 üstünde çık.

    %5+ düşüşte inatlaşma yok — ATR stop. En fazla 2 kademe.
    """
    if avg_entry <= 0:
        return "HOLD", "giriş fiyatı yok"
    drop = (avg_entry - price) / avg_entry
    if drop >= STOP_DROP:
        return "STOP", f"%{drop*100:.2f} düşüş ≥ %5 — ATR stop, inatlaşma yok"
    if rescues > 0 and price >= avg_entry * (1 + RESCUE_EXIT):
        return "EXIT", f"ortalamanın %{RESCUE_EXIT*100:.0f} üstünde — kara geçildi"
    if drop >= RESCUE_DROP and rescues < RESCUE_MAX:
        return "ADD", f"%{drop*100:.2f} düşüş ≥ %2 — kurtarma kademesi {rescues+1}/{RESCUE_MAX}"
    return "HOLD", ""


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
TP1_PCT = 0.008              # %0.8 → ilk %40
TP1_RATIO = 0.40
TP2_PCT = 0.015              # %1.5 → ikinci %40 (orijinal pozisyondan)
TP2_RATIO = 0.40
TP3_PCT = 0.025              # %2.5 → kalan %20 trailing moda
TRAIL_PULLBACK = 0.005       # zirveden %0.5 geri çekilmede sat
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

    stage = int(pos.get("tp_stage", 0))
    peak = max(float(pos.get("peak_tp", entry) or 0), price)
    if stage >= 3 and price <= peak * (1 - TRAIL_PULLBACK) + eps:
        return "FULL", 1.0, \
            f"TP3 trailing: zirve {peak:.4f}'den %{TRAIL_PULLBACK*100:.1f} geri çekildi", locked
    if gain >= TP3_PCT - eps and stage < 3:
        return "TRAIL", 1.0, \
            f"TP3: kâr %{gain*100:.2f} ≥ %2.5 — kalan %20 trailing moda", locked
    if gain >= TP2_PCT - eps and stage < 2:
        return "PARTIAL2", TP2_RATIO, \
            f"TP2: kâr %{gain*100:.2f} ≥ %1.5 — %40 daha sat", locked
    if gain >= TP1_PCT - eps and stage < 1:
        return "PARTIAL", TP1_RATIO, \
            f"TP1: kâr %{gain*100:.2f} ≥ %0.8 — %40 sat + breakeven", locked
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


def _scan_new() -> list[str]:
    """YENİ TARAMA — açık pozisyonlardan BAĞIMSIZ, her turda çalışır.

    Açık coin'ler aday listesinden çıkarılır; aynı coine çift emir atılmaz.
    Crash Bid / OBI+VWAP / Mikro / Fırsat sinyalleri burada üretilir.
    """
    from ui import (connors as _cn, crash_bid as _cb, engine as _eng,
                    market_regime, micro_engine as _me, risk_brakes as _rb,
                    safety_guards, tiered_brakes as _tb, tr_scalper as t,
                    vwap_obi as _vo)
    from ui import order_flow

    logs: list[str] = ["YENİ TARAMA: başlatıldı"]
    _open = t._load().get("positions") or []
    open_syms = {str(p.get("symbol")) for p in _open if isinstance(p, dict)}
    # GEÇİCİ KİLİT: ilk gerçek TP satışına kadar yeni pozisyon açma.
    from ui import tp_proof
    if _open and not tp_proof.unlocked():
        return logs + [f"TP KİLİDİ: açık pozisyon var ve gerçek TP kanıtı yok "
                       f"({tp_proof.count()} satış) — yeni pozisyon açılmadı, "
                       f"sadece mevcut pozisyon yönetiliyor"]
    watch = dynamic_watchlist()
    logs.append(f"DİNAMİK TOP-10 (saatlik): {', '.join(watch)}")
    rows = [r for r in scan(list(watch)) if r["symbol"] not in open_syms]
    if open_syms:
        logs.append(f"YENİ TARAMA: açık coin'ler dışlandı ({', '.join(sorted(open_syms))})")
    if not rows:
        return logs + ["YENİ TARAMA: uygun aday yok (1s veri yok veya hepsi açık)"]
    logs.append("SKOR TABLOSU (0-100): " + " | ".join(
        f"{r['symbol']} {r['score']} (RSI {r['rsi_puan']}+düşüş {r['dusur_puan']}"
        f"+hacim {r['hacim_puan']}+BB {r['bb_puan']}) ATR%{r['atr_pct']}"
        for r in rows[:8]))
    best = rows[0]
    # REJİM KAPISI — araştırma: grid trendde kaybettirir, yatay/ayıda çalışır
    _reg = market_regime.regime("BTC_TRY")
    _grid_off = bool(_reg.get("bull")) and float(_reg.get("adx", 0) or 0) >= 25
    if _grid_off:
        logs.append("REJİM KAPISI: BOĞA + ADX≥25 — mikro grid yeni alımı kapalı "
                    "(fırsat/crash/OBI sinyalleri açık)")

    # SİNYALLER — karar modülleri skor tablosunu BOZMAZ
    _crash_ok, _last_close, _vo_ok, _cok = False, 0.0, False, False
    try:
        _k = t.klines(best["symbol"], "1m", 3)
        if _k is not None and len(_k) >= 2:
            _prev, _cur = float(_k["Close"].iloc[-2]), float(_k["Close"].iloc[-1])
            _last_close = _cur
            _cr = _cb.detect_drop(_prev, _cur)
            _crash_ok = bool(_cr["ok"])
            if _crash_ok:
                _pl = _cb.plan(_cur)
                logs.append(f"CRASH BID SİNYALİ: {_cr['reason']} · limit alış {_pl['bid_px']:.4f} "
                            f"· hedef +%2 · 4 sa · %5-7 tek seferlik (skor bypass)")
    except Exception:
        pass
    ofi = order_flow.check(best["symbol"])
    if _vo.is_deep(best["symbol"]):
        try:
            _kd = t.klines(best["symbol"], "1m", 1440)
            _vw = _vo.session_vwap(_kd.tail(1440).values.tolist()) if _kd is not None else {}
            if _vw.get("ok"):
                _obi_f = _vo.obi_formula(
                    [["b", float(ofi.get("bid_pct", 50)) / 100.0]],
                    [["a", (100.0 - float(ofi.get("bid_pct", 50))) / 100.0]])
                from ui import ws_feed as _wsf
                _depth = (_wsf._load().get("depth_obi") or {}).get(best["symbol"], {})
                _age_ms = _depth.get("age_ms")
                _sig_age = (_age_ms / 1000.0) if isinstance(_age_ms, (int, float)) else 99.0
                _vo_ok, _vo_why = _vo.reclaim_check(
                    best["symbol"], best["price"], _vw["vwap"],
                    _vw["vwap"] - 0.01, _obi_f, min(_sig_age, 15.0), 65.0,
                    fresh_limit=2.0)
                logs.append(f"OBI+VWAP: {_vo_ok} | {_vo_why} · depth yaşı "
                            f"{_sig_age:.2f} sn (limit 2 sn), OBI={_depth.get('ratio', '—')}")
        except Exception as _ve:
            logs.append(f"OBI+VWAP kontrolü atlandı: {type(_ve).__name__}")
    _trend_ok = True
    _s200 = 0.0
    try:
        _c15 = t.klines(best["symbol"], "15m", 210)
        _cd1 = t.klines(best["symbol"], "1d", 210)
        _cok, _cwhy = _cn.entry(_c15["Close"].tolist(), _cd1["Close"].tolist())
        _s200 = float(_cd1["Close"].rolling(200).mean().iloc[-1])
        _trend_ok = float(best["price"]) > _s200
        logs.append(f"CONNORS RSI(2): {'AL sinyali' if _cok else 'sinyal yok'} · {_cwhy}")
        logs.append(f"TREND FİLTRESİ (günlük SMA200): fiyat {best['price']:.8f} "
                    f"{'>' if _trend_ok else '<'} {_s200:.8f} → "
                    f"{'uzun girişe izin' if _trend_ok else 'YENİ ALIM YOK (düşüş trendi)'}")
    except Exception:
        _cok = False
    logs.append(f"VOLATİLİTE FİLTRESİ: {best['symbol']} — ATR %{best['atr_pct']:.2f} "
                f"— kademe: {best['vol_not']}")
    if best["pozisyon_pct"] <= 0:
        return logs + [f"ALIM YOK: {best['vol_not']}"]
    fresh_ok, fresh_msg = safety_guards.stale_check()
    if not fresh_ok:
        return logs + [fresh_msg]
    buy_ok, buy_halt_msg = safety_guards.buy_allowed()
    if not buy_ok:
        return logs + [buy_halt_msg]
    wr_ok, wr_msg = safety_guards.win_rate_allowed()
    if not wr_ok:
        return logs + [wr_msg]
    logs.append(f"FİYAT TAZELİĞİ: {fresh_msg}")
    ok, why = should_buy(best)
    if not ok:
        return logs + [f"ALIM YOK: {best['symbol']} — {why}"]
    sym = best["symbol"]
    _cur = t._load()
    _cur, anchor = grid_anchor_update(_cur, sym, best["price"])
    t._save(_cur)
    _drop = (anchor - best["price"]) / anchor if anchor else 0.0
    if _drop < GRID_STEPS[0]:
        return logs + [f"GRID KATMAN 1: %{_drop*100:.2f} pullback < %{GRID_STEPS[0]*100:.1f} "
                       f"— referans {anchor:.8f}, alım bekleniyor"]
    _tier, _tier_pct = tier_of(sym)
    logs.append(f"KADEME: {sym} → {_tier} · POZİSYON: "
                f"%{confidence_pct(best['score'])*100:.0f} (skora göre)")
    logs.append(f"OFI: {ofi['state']} · bid %{ofi['bid_pct']} · "
                f"spread %{ofi['spread_pct']:.2f}" + (f" · {ofi['reason']}" if ofi["reason"] else ""))
    if not ofi["ok"]:
        return logs + ["OFI: Toxic flow, alım atlandı"]
    _bp = float(ofi.get("bid_pct", 50.0) or 50.0)
    _obi = {"ok": (_bp / max(1.0, 100.0 - _bp)) >= 2.0,
            "ratio": round(_bp / max(1.0, 100.0 - _bp), 2),
            "reason": f"OBI {_bp / max(1.0, 100.0 - _bp):.2f}:1"}
    _cvdd = _me.fetch_cvd(sym)
    _opp_ok, _opp_why = _me.opportunity_entry(best, _obi, _cvdd, best["score"])
    _motor = "FIRSAT" if _opp_ok else "MIKRO"
    _split = _me.capital_split(t.available_try())
    logs.append(f"MOTOR {_motor}: {_opp_why} | sermaye mikro ₺{_split['micro']:.2f} "
                f"/ fırsat ₺{_split['opportunity']:.2f} · CVD {_cvdd.get('delta', 0)}")
    brake = t.brakes_block(sym)
    if brake and "AYI REJİMİ - NAKİTTE KALMA" not in brake:
        return logs + [f"FREN ({sym}): {brake}"]
    if _tier == "Fırsatçı":
        if float(best.get("dus_pct", 0) or 0) >= 3.0:
            return logs + ["KADEME 3: son 1s %3+ düşüş — 60 dk bekleme, alım yok"]
        try:
            from ui import order_guard
            sp_ok, sp_msg = order_guard.check_slippage(
                best["price"], t.price(sym) or best["price"])
            if not sp_ok:
                return logs + [f"KADEME 3 spread %0.5 filtresi: {sp_msg}"]
        except Exception:
            pass
    bal = t.available_try()
    _conf = confidence_pct(best["score"])
    _brs = _rb.status()
    _open_bal = float(_brs.get("day_open_balance", 0) or 0)
    _day_dd = (abs(float(_brs.get("day_realized_pnl", 0) or 0)) / _open_bal * 100
               if _open_bal > 0 else 0.0)
    _tbs = _tb.status(_day_dd)
    logs.append(f"KADEMELİ FREN: {_tbs['msg']} (çarpan {_tbs['size_multiplier']:.2f})")
    if not _tbs["trade_allowed"]:
        return logs + [_tbs["msg"]]
    cap = min(t.position_size_try(bal, sym), bal * _conf,
              _tb.position_cap(bal, _day_dd, _conf))
    if cap <= 0:
        return logs + ["bakiye yetersiz"]
    if not _trend_ok:
        return logs + ["TREND KAPISI: fiyat günlük SMA200 altında — yeni uzun pozisyon açılmadı"]
    # EKONOMİ KAPISI — komisyonu yenmeyen işlem hiç gönderilmez
    from ui import economics as _econ
    _worth, _wmsg = _econ.worth_it(cap, _econ.MICRO_TP_PCT, _econ.ROUND_TRIP_MAKER)
    logs.append(f"EKONOMİ: {_wmsg}")
    if not _worth:
        return logs + ["Net kâr eşiği altında — emir atılmadı"]

    _sigs = {"CRASH_BID": bool(_crash_ok), "OBI_VWAP": bool(_vo_ok),
             "MICRO_GRID": False, "FIRSAT": bool(_opp_ok or _cok)}
    _chosen = _eng.pick_motor(_sigs)
    logs.append(f"KARAR MOTORU: sinyaller={_sigs} → seçilen={_chosen or 'standart alım'}")
    _pf_ok, _pf_why = _eng.preflight(sym, 0.9, _day_dd)
    if not _pf_ok:
        return logs + [_pf_why]
    if _chosen == "CRASH_BID":
        _er = _eng.crash_bid_entry(sym, _last_close, cap, _day_dd)
        return logs + [f"CRASH BID: {'emir atıldı ID ' + str(_er.get('order_id')) if _er.get('ok') else _er.get('reason')}"]
    if _chosen == "OBI_VWAP":
        _er = _eng.obi_vwap_entry(sym, best["price"], cap, _day_dd)
        return logs + [f"OBI+VWAP: {'emir atıldı ID ' + str(_er.get('order_id')) if _er.get('ok') else _er.get('reason')}"]
    if _grid_off:
        return logs + ["REJİM KAPISI: trendde mikro grid alımı yapılmadı"]
    # R/R KAPISI — TP %0.6 + komisyon %0.25 ile mikro alımın matematiksel
    # beklentisi negatifse emir ATMA. (TP %1.5'e çıkarsa %1 stop geçerli olur.)
    from ui import risk_reward as _rr_gate
    _rr_g = _rr_gate.check(1.0, tp=_econ.MICRO_TP_PCT, fee=_econ.ROUND_TRIP_MAKER)
    logs.append("R/R KAPISI: " + _rr_g["msg"])
    if not _rr_g["ok"]:
        return logs + ["R/R KAPISI: mikro alımın net beklentisi negatif — "
                       "emir atılmadı (TP ≥ %1.5 gerekir)"]
    _flt = t._filters(sym)
    qty = max(_qty(cap, best["price"], _flt["step"] or 0.00000001), _flt["min_qty"])
    res = _eng.place_buy(sym, _chosen or _motor, cap, price_limit=None)
    qty = float(res.get("qty") or qty)
    if not res.get("ok"):
        return logs + [f"ALIM HATA ({sym}): {str(res.get('reason'))[:120]}"]
    body = ((res.get("data") or {}).get("data") or {})
    _cur = t._load()
    _poss = _cur.get("positions", [])
    if len(_poss) >= MAX_POSITIONS:
        return logs + [f"PORTFÖY DOLU: {len(_poss)}/{MAX_POSITIONS} — yeni pozisyon açılmadı"]
    _poss.append({
        "symbol": sym, "qty": qty, "entry": best["price"], "avg_entry": best["price"],
        "entry_ts": __import__("time").time(),
        "time": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
        "order_id": body.get("orderId") or body.get("id"),
        "cost": round(best["price"] * qty, 4), "strategy": MOD_ADI,
        "rescues": 0, "ladders": 0, "last_buy": best["price"],
        "grid_anchor": anchor, "grid_layers": 1, "micro_layers": 0,
        "micro_tp_stage": 0, "motor": _motor, "micro_stop_pct": 1.0,
        "atr_stop": market_regime.atr_stop(best["price"], sym)["stop"],
    })
    t._save({**_cur, "positions": _poss, "mode": MOD_ADI})
    logs.append(f"PORTFÖY: {len(_poss)}/{MAX_POSITIONS} açık pozisyon")
    try:
        from ui import disaster_recovery
        disaster_recovery.backup("hızlı kâr alımı")
    except Exception:
        pass
    logs.append(f"ALIM {sym} OK · {qty} adet @ {best['price']:.2f} · {why}")
    return logs


def cycle() -> list[str]:
    """Tek tarama turu — mevcut emir/fren modüllerini kullanır, EMA50'ye dokunmaz."""
    from ui import market_regime, tr_scalper as t

    from ui import micro_engine as _me
    from ui import strategy_mode as sm

    logs: list[str] = []
    t._beat(int(t._load().get("cycle_count", 0)) + 1)
    _st = t._load()
    t._save({**_st, "cycle_count": int(_st.get("cycle_count", 0)) + 1})
    # Aktif limit emirlerini yönet: Crash Bid kaydır/dolum/+%2 sat, OBI 15 sn TTL
    try:
        from ui import engine as _eng, vwap_obi as _vo_mgr
        _eng.crash_bid_manage()
        _kb = t.klines("BTC_TRY", "1m", 1440)
        _kv = _vo_mgr.session_vwap(_kb.tail(1440).values.tolist()) if _kb is not None else {}
        if _kv.get("ok"):
            _eng.obi_vwap_manage(_kv["vwap"])
    except Exception as _mexc:
        logs.append(f"Motor yönetimi hatası: {type(_mexc).__name__}")
    if t.kill_switch():
        return ["KILL SWITCH: yeni işlem yok"]
    _guard = sm.day_guard()
    if _guard:
        return [_guard]
    _mode, _reg = sm.current_auto()
    _bear_cap, _rsi_max = sm.bear_params(_reg)
    logs.append(f"REJİM: {_reg} — MOD: {sm.LABELS[_mode]}"
                + (f" (AYI: %{POS_PCT*100:.0f} pozisyon, RSI<{_rsi_max:.0f})"
                   if _bear_cap else ""))
    # 1) YENİ TARAMA — açık pozisyondan BAĞIMSIZ her turda çalışır
    logs += _scan_new()

    st = t._load()
    # RECONCILIATION: state'deki pozisyonlar ile gerçek API bakiyesini doğrula.
    # API bakiyesi yoksa hayalet pozisyonu temizle (fill olmadı / elle satıldı).
    _poss = st.get("positions", [])
    if _poss:
        _alive = []
        for _p in _poss:
            _bal = t.asset_balance(_p["symbol"].split("_")[0]) or 0
            if _bal >= float(_p.get("qty", 0)) * 0.5:
                _alive.append(_p)
            else:
                logs.append(f"RECONCILE: {_p['symbol']} API bakiyesi {_bal:.6f} < "
                            f"pozisyon {float(_p.get('qty',0)):.6f} — hayalet pozisyon temizlendi")
        if len(_alive) != len(_poss):
            t._save({**st, "positions": _alive})
            st = t._load()
    # 5 eşzamanlı pozisyon: listeden yönetilecek olanı seç (eskiler tekil alanla uyumlu)
    pos, _in_list = _active_position(st)
    logs.append(f"POZİSYON YÖNETİMİ: "
                f"{pos['symbol'] + ' · ' + str(pos.get('qty')) + ' adet' if pos else 'açık pozisyon yok'}"
                f" — TP/DCA/breakeven kontrol edildi")
    if pos:
        # STALE >120 sn: TP dahil hiçbir satış yapma, sadece izle
        from ui import safety_guards
        sell_ok, stale_msg = safety_guards.stale_check(sell=True)
        if not sell_ok:
            return logs + [stale_msg]
        sym = pos["symbol"]
        ind = indicators(sym)
        if not ind:
            return [f"{sym}: 1s veri yok — pozisyon korunuyor"]
        entry = float(pos.get("entry", 0))
        # HARD STOP — DCA ve TP'lerden ÖNCE, tam satış. Zarar durdurucu.
        from ui import hard_stop
        _hs, _hs_msg = hard_stop.decision(pos, ind["price"])
        logs.append(f"HARD STOP hedefi: {sym} {hard_stop.stop_price(pos):.8f} "
                    f"(%{hard_stop.stop_pct(pos)*100:.0f}, katman "
                    f"{int(pos.get('grid_layers', 0) or 0)}/3) — şu an {ind['price']:.8f}")
        from ui import risk_reward as _rr
        _rrv = _rr.check(hard_stop.stop_pct(pos) * 100.0)
        logs.append("R/R KAPISI: " + _rrv["msg"]
                    + (" (mevcut pozisyon: felaket stop'u, yeni giriş değil)"
                       if not pos.get("micro_stop_pct") else ""))
        if _hs:
            _hsres = t.sell(sym, float(pos["qty"]), f"{MOD_ADI}: {_hs_msg}")
            logs.append(f"HARD STOP {'OK' if _hsres.get('ok') else 'HATA'} · {_hs_msg}")
            if _hsres.get("ok"):
                sm.day_record(float(_hsres.get("net", 0) or 0))
            return logs
        atr = market_regime.atr_stop(ind["price"], sym)
        # TP3 trailing zirvesini her turda yukarı güncelle
        if int(pos.get("tp_stage", 0)) >= 3 and ind["price"] > float(pos.get("peak_tp", 0) or 0):
            pos["peak_tp"] = ind["price"]
            _save_active_position(pos, _in_list)
        # MİKRO TP — TP1'in ALTINA eklenir (%0.4 / %0.8). Net kâr şart.
        from ui import micro_engine as _me
        _mact, _mratio, _mwhy = _me.micro_tp_decision(pos, ind["price"])
        if _mact == "MICRO_TP":
            _mflt = t._filters(sym)
            _mqty = max(_qty(float(pos["qty"]) * _mratio, ind["price"],
                             _mflt["step"] or 0.00000001), _mflt["min_qty"])
            # MAKER ÇIKIŞ — limit satış, komisyon %0.15 → %0.10
            _pend_id = pos.get("tp_limit_order_id")
            if _pend_id and time.time() - float(pos.get("tp_limit_at", time.time())) > 3600:
                t.cancel_order(_pend_id)
                _cur = t._load()
                _np, _nl = _active_position(_cur)
                if _np:
                    _np.pop("tp_limit_order_id", None)
                    _save_active_position(_np, _nl)
                logs.append(f"MİKRO TP maker limit 1 saatte dolmadı — ID {_pend_id} iptal edildi")
                _pend_id = None
            if _pend_id:
                _cf = t.confirm_limit_fill(_pend_id, sym, float(pos.get("tp_limit_qty", _mqty)),
                                           pos.get("tp_limit_reason", _mwhy), partial=True)
                if _cf.get("pending"):
                    logs.append(f"MİKRO TP maker limit bekliyor ID {_pend_id} — pozisyon korundu")
                    return logs
                _mres, _mqty = _cf, float(pos.get("tp_limit_qty", _mqty))
                _cur = t._load()
                _np, _nl = _active_position(_cur)
                if _np:
                    _np.pop("tp_limit_order_id", None)
                    _np["micro_tp_stage"] = int(_np.get("micro_tp_stage", 0)) + 1
                    _np["grid_layers"] = max(1, int(_np.get("grid_layers", 1)) - 1)
                    _np["grid_anchor"] = ind["price"]
                    _save_active_position(_np, _nl)
            else:
                _target = float(pos.get("entry", ind["price"])) * (1 + _me.MICRO_TP[0][0])
                _mres = t.sell(sym, _mqty, f"{MOD_ADI}: {_mwhy}",
                               partial=True, price_limit=_target)
                if _mres.get("pending"):
                    _cur = t._load()
                    _np, _nl = _active_position(_cur)
                    if _np:
                        _np["tp_limit_order_id"] = _mres.get("order_id")
                        _np["tp_limit_qty"] = _mqty
                        _np["tp_limit_reason"] = _mwhy
                        _np["tp_limit_at"] = time.time()
                        _save_active_position(_np, _nl)
                    logs.append(f"MİKRO TP maker limit emri atıldı ID {_mres.get('order_id')} "
                                f"@ {_target:.8f} · komisyon %0.10 — dolum bekleniyor")
                    return logs
            if _mres.get("ok"):
                # Mikro TP %1.5, TP2 ile aynı seviye — tp_stage=2 yapıp
                # TP2'nin aynı pozisyonu ikinci kez satmasını engelle.
                _cur = t._load()
                _np, _nl = _active_position(_cur)
                if _np:
                    _np["tp_stage"] = 2
                    _save_active_position(_np, _nl)
                sm.day_record(float(_mres.get("net", 0) or 0))
                from ui import tp_proof as _tpproof
                _n = _tpproof.record_real_tp(sym, _mwhy, float(_mres.get("net", 0) or 0))
                logs.append(f"GERÇEK TP KANITI {_n}: {_mwhy} · {_mqty} adet satıldı (MAKER)")
            else:
                logs.append(f"MİKRO TP emri reddedildi: {str(_mres.get('reason'))[:80]}")
            return logs
        if _mact == "SKIP":
            logs.append(f"MİKRO TP atlandı: {_mwhy}")

        action, ratio, why, locked = sell_decision(pos, ind, atr["stop"])
        # Mikro TP %1.5 iken TP1 %0.8 erken satış yapmasın — tek çıkış noktası.
        if action == "PARTIAL" and _me.MICRO_TP[0][0] >= 0.015:
            logs.append("TP1 %0.8 atlandı: mikro TP %1.5 tek çıkış noktası (çift satış yok)")
            action, ratio, why = "HOLD", 0.0, ""
        if locked > float(pos.get("locked_sl", 0) or 0):
            pos["locked_sl"] = locked
            _gain = (ind["price"] - entry) / entry if entry else 0.0
            _msg = (f"Trailing: Stop %0.5 kara çekildi ({locked:.4f})"
                    if _gain >= TRAIL_LOCK_GAIN else
                    f"Trailing: Stop giriş fiyatına çekildi ({locked:.4f})")
            logs.append(_msg)
            try:
                from ui import autonomous_ops as _ao
                _ao._log(_msg)
            except Exception:
                pass
        if action in ("PARTIAL", "PARTIAL2"):
            flt = t._filters(sym)
            # TP2 orijinal pozisyonun %40'ı — kalan qty'nin 2/3'ü (0.4/0.6)
            factor = ratio if action == "PARTIAL" else ratio / (1 - TP1_RATIO)
            sell_qty = max(_qty(float(pos["qty"]) * factor, ind["price"],
                                flt["step"] or 0.00000001), flt["min_qty"])
            res = t.sell(sym, sell_qty, f"{MOD_ADI}: {why}", partial=True)
            if res.get("ok"):
                np, np_in_list = _active_position(t._load())
                if not np:
                    np, np_in_list = pos, _in_list
                np["tp_stage"] = 1 if action == "PARTIAL" else 2
                if locked:
                    np["locked_sl"] = locked
                # GRID: TP satışı bir katman slotunu boşaltır, referansı yeniler
                _freed = max(1, int(np.get("grid_layers", 1) or 1) - 1)
                np["grid_layers"] = _freed
                np["grid_anchor"] = ind["price"]
                _save_active_position(np, np_in_list)
                sm.day_record(float(res.get("net", 0) or 0))
                from ui import tp_proof as _tpproof
                _n = _tpproof.record_real_tp(sym, why, float(res.get("net", 0) or 0))
                logs.append(f"GERÇEK TP KANITI {_n}: {why} · net {float(res.get('net', 0) or 0):+.2f} TL")
                logs.append(f"GRID: TP satışı sonrası katman {int(pos.get('grid_layers',1))}→{_freed}, "
                            f"yeni referans {ind['price']:.8f}")
            logs.append(f"KDEMELİ SATIŞ {'TP1' if action == 'PARTIAL' else 'TP2'} {sym} "
                        f"{'OK' if res.get('ok') else 'HATA'} · {sell_qty} adet · {why}")
            return logs
        if action == "TRAIL":
            np, np_in_list = _active_position(t._load())
            if not np:
                np, np_in_list = pos, _in_list
            np["tp_stage"] = 3
            np["peak_tp"] = ind["price"]
            if locked:
                np["locked_sl"] = locked
            _save_active_position(np, np_in_list)
            logs.append(f"TP3 TRAILING AKTİF {sym} · zirve {ind['price']:.8f} "
                        f"· kalan %{100*(1-TP1_RATIO-TP2_RATIO):.0f} · {why}")
            return logs
        if action == "FULL":
            res = t.sell(sym, float(pos["qty"]), f"{MOD_ADI}: {why}")
            if res.get("ok"):
                sm.day_record(float(res.get("net", 0) or 0))
                if "trailing" in str(why).lower() or "tp3" in str(why).lower():
                    from ui import tp_proof as _tpproof
                    _n = _tpproof.record_real_tp(sym, why, float(res.get("net", 0) or 0))
                    logs.append(f"GERÇEK TP KANITI {_n}: TP3 trailing satışı · "
                                f"net {float(res.get('net', 0) or 0):+.2f} TL")
            logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} — {why}")
            return logs
        # SÜREKLİ GRID — katman 2/3: fiyat referanstan %1 / %1.5 düştüğünde ek alım
        gdec, gnote = _me.micro_grid_decision(pos, ind["price"])
        logs.append(f"GRID: {sym} — {gnote}")
        if gdec == "ADD":
            _wr_ok, _wr_msg = safety_guards.win_rate_allowed()
            if not _wr_ok:
                return logs + [_wr_msg]
            _bal = t.available_try()
            avg = float(pos.get("avg_entry", entry) or entry)
            exposure = avg * float(pos.get("qty", 0) or 0)
            remaining = max(0.0, _bal * COIN_HARD_CAP - exposure)
            target = _bal * GRID_BUY_PCT
            spend = min(target, remaining)
            _layers = int(pos.get("grid_layers", 1) or 1)
            if spend <= 0:
                return logs + [f"GRID KATMAN {_layers+1} ALINMADI: coin üst limiti "
                               f"%{COIN_HARD_CAP*100:.0f} dolu (₺{exposure:.2f})"]
            flt = t._filters(sym)
            gqty = max(_qty(spend, ind["price"], flt["step"] or 0.00000001), flt["min_qty"])
            gres = t._order(sym, 0, gqty)
            if gres.get("ok"):
                old_qty = float(pos.get("qty", 0) or 0)
                new_qty = old_qty + gqty
                pos["avg_entry"] = round((avg * old_qty + ind["price"] * gqty) / new_qty, 8)
                pos["qty"] = round(new_qty, 8)
                pos["cost"] = round(exposure + spend, 4)
                pos["grid_layers"] = _layers + 1
                _save_active_position(pos, _in_list)
                _cap_note = (" · coin %7 üst limiti nedeniyle hedef %5'ten küçültüldü"
                             if spend < target - 0.01 else "")
                logs.append(f"GRID ALIM KATMAN {_layers+1}/{GRID_LAYERS} {sym} OK · "
                            f"{gqty} adet @ {ind['price']:.8f} · ₺{spend:.2f} "
                            f"(hedef ₺{target:.2f}){_cap_note} · yeni ort. {pos['avg_entry']:.4f}")
            else:
                logs.append(f"GRID KATMAN {_layers+1} emri reddedildi: "
                            f"{str(gres.get('reason'))[:100]}")
            return logs

        # DCA KURTARMA — %2 düşüşte yarı kademe, ortalamanın %1 üstünde çık, %5'te stop
        avg = float(pos.get("avg_entry", entry) or entry)
        rescues = int(pos.get("rescues", 0) or 0)
        act, note = rescue_decision(avg, ind["price"], rescues)
        logs.append(f"DCA KURTARMA: {sym} — {note}")
        if act in ("STOP", "EXIT"):
            res = t.sell(sym, float(pos["qty"]), f"{MOD_ADI}: {note}")
            logs.append(f"SAT ({'ATR stop' if act == 'STOP' else 'kurtarma kârı'}) {sym} "
                        f"{'OK' if res.get('ok') else 'HATA'} — {note}")
            return logs
        if act == "ADD" and int(pos.get("grid_layers", 1) or 1) >= GRID_LAYERS:
            logs.append(f"KURTARMA ATLANDI: 3 grid katmanı dolu — 4. alım yok, TP bekleniyor")
        elif act == "ADD":
            _vpct, _vnot = volatility_position(ind["atr_pct"])
            _bal = t.available_try()
            cap = min(t.position_size_try(_bal, sym), _bal * _vpct, _bal * POS_PCT / 2) \
                if _vpct > 0 else 0
            if cap <= 0:
                return logs + [f"KURTARMA ALINMADI: {_vnot}"]
            flt = t._filters(sym)
            qty = max(_qty(cap, ind["price"], flt["step"] or 0.00000001), flt["min_qty"])
            res = t._order(sym, 0, qty)
            if res.get("ok"):
                old_qty = float(pos.get("qty", 0))
                pos["avg_entry"] = round((avg * old_qty + ind["price"] * qty) / (old_qty + qty), 8)
                pos["qty"] = round(old_qty + qty, 8)
                pos["rescues"] = rescues + 1
                _save_active_position(pos, _in_list)
                logs.append(f"KURTARMA {rescues+1}/{RESCUE_MAX}: {sym} +{qty} adet "
                            f"@ {ind['price']:.2f} · yeni ortalama {pos['avg_entry']:.2f}")
            else:
                logs.append(f"KURTARMA emri reddedildi: {str(res.get('reason'))[:100]}")
        else:
            gain = (ind["price"] - entry) / entry if entry else 0.0
            age_h = (__import__("time").time() - float(pos.get("entry_ts", __import__("time").time()))) / 3600.0
            if age_h >= 2.0 and gain <= 0:
                _rows = scan(list(t.SYMBOLS))
                if len(_rows) > 1 and _rows[1]["score"] >= 80:
                    _msg = (f"FIRSAT ÖNERİSİ: 1. pozisyon {sym} {age_h:.1f} saattir kârsız; "
                            f"2. coin {_rows[1]['symbol']} skoru {_rows[1]['score']} — "
                            f"zaman stopu ile kapatıp 2.'ye geçmek ister misin? "
                            f"(OTOMATİK DEĞİŞTİRİLMEDİ)")
                    logs.append(_msg)
                    try:
                        from ui import autonomous_ops as _ao
                        _ao._log(_msg)
                    except Exception:
                        pass
            _kademe = int(pos.get("grid_layers", pos.get("ladders", 0)) or 0)
            logs.append(f"Pozisyon {sym}: fiyat {ind['price']:.2f} / giriş {entry:.2f} · "
                        f"RSI {ind['rsi']:.1f} · kademe {_kademe}/{GRID_LAYERS} — bekleniyor")
        return logs

    return logs


@st.cache_data(ttl=3600, show_spinner=False)
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
                if (0.5 <= ap <= 4.0 and px <= low24 * 1.01
                        and r < 45 and px <= lo * 1.05):
                    pos = {"entry": px * (1 + SLIPPAGE), "units": 1,
                           "ladders": 0, "last": px, "stage": 0, "peak": px, "realized": 0.0}
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
    worst = round(min([x["ret"] for x in trades] or [0]), 2)
    return {
        "gun": days, "islem": len(trades), "karli": len(wins),
        "zararli": len(trades) - len(wins),
        "kazanma_pct": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "toplam_kar_pct": total,
        "en_buyuk_zarar_pct": worst,
        "komisyon_toplam_pct": round(len(trades) * 2 * FEE * 100, 2),
        "hedef": f"%{TAKE_PCT*100:.1f}", "komisyon": "çift yön %0.2",
        "slippage": f"%{SLIPPAGE*100:.1f}",
    }
