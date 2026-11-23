"""NET KÂR MOTORU — almadan önce net kârı hesaplar, yoksa ALMAZ.

Önceki HSC-AMM hatası: 'spread var' diye alıp, satışta alıştan düşük
fiyatla doluyordu (adverse selection) → 17/18 işlem zararlı.

Bu motorun TEK kuralı:
  alış_fiyat + komisyon + beklenen_kayma + HEDEF_NET_KÂR <= satış_fiyatı
  değilse emir atılmaz.

Dahası: ALIMLAR SADECE YÜKSELİŞ BAŞLADIKTAN SONRA (reversal onayı) yapılır.
Düşen bıçak yakalanmaz. Duruş: 15dk, hedef %1.5, stop %0.8, max 30dk.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth, tr_scalper as t

STATE = auth.USERS_DIR / "net_profit_engine.json"
SYMBOLS = ("BTC_TRY", "ETH_TRY")
CAPITAL = 500.0           # kullanıcı onayı: çok küçük sermaye
PER_TRADE = 50.0          # işlem başına ₺50
COMMISSION_PCT = 0.15     # maker+BNB gidiş-dönüş
EXPECTED_SLIP_PCT = 0.05  # gerçekçi kayma payı
MIN_NET_TRY = 0.30        # işlem başına en az 30 kuruş net kâr
TARGET_GAIN_PCT = 1.5     # satış hedefi
STOP_LOSS_PCT = 0.8       # stop
MAX_HOLD_SEC = 1800       # 30 dk


def _log(msg: str) -> None:
    try:
        from ui import autonomous_ops
        autonomous_ops._log("NET_KAR: " + msg)
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


def gate(buy_px: float, target_px: float) -> tuple[bool, str]:
    """Net kâr kapısı — almadan ÖNCE çağrılır."""
    gross = (target_px - buy_px) / buy_px * 100
    net_pct = gross - COMMISSION_PCT - EXPECTED_SLIP_PCT
    net_try = PER_TRADE * net_pct / 100
    ok = net_try >= MIN_NET_TRY
    msg = (f"NET KÂR KAPISI: alış {buy_px:.2f} → hedef {target_px:.2f} "
           f"(brüt %{gross:.2f} - komisyon %{COMMISSION_PCT:.2f} - kayma "
           f"%{EXPECTED_SLIP_PCT:.2f}) = net %{net_pct:.2f} ≈ {net_try:+.2f} TL "
           f"→ {'EMİR AT' if ok else 'ALIM YOK'}")
    return ok, msg


def reversal_ok(symbol: str) -> tuple[bool, str]:
    """Düşüş sonrası yukarı dönüş var mı? (15dk, SMA20 üstü + son 2 mum yeşil)"""
    try:
        k = t.klines(symbol, "15m", 30)
        c = [float(x) for x in k["Close"].tolist()]
        if len(c) < 22:
            return False, "veri yetersiz"
        sma20 = sum(c[-20:]) / 20
        son_yukari = c[-1] > c[-2] and c[-2] > c[-3]
        fiyat_ustunde = c[-1] > sma20
        ok = son_yukari and fiyat_ustunde
        return ok, (f"15dk reversal: son2 mum {'YEŞİL' if son_yukari else 'KIRMIZI'}, "
                    f"fiyat {c[-1]:.2f} {'>' if fiyat_ustunde else '<'} SMA20 {sma20:.2f}")
    except Exception as exc:
        return False, f"reversal veri hatası: {exc}"


def step() -> list[str]:
    logs: list[str] = []
    st = _load()
    inv = st.get("position")
    if inv:
        px = t.price(inv["symbol"]) or 0
        if px >= inv["target"]:
            res = t.sell(inv["symbol"], inv["qty"], "NET_KAR TP")
            net = res.get("net") if isinstance(res, dict) else None
            logs.append(f"SATIŞ (hedef): {inv['symbol']} {inv['qty']} @ {px:.2f} net={net}")
            st["position"] = None; _save(st)
            return logs
        if px <= inv["stop"] or time.time() - float(inv["at"]) > MAX_HOLD_SEC:
            res = t.sell(inv["symbol"], inv["qty"], "NET_KAR stop/zaman")
            logs.append(f"SATIŞ (stop/zaman): {inv['symbol']} @ {px:.2f}")
            st["position"] = None; _save(st)
            return logs
        return logs

    if st.get("day_pnl", 0) <= -25:   # günlük ₺25 zarar durdur
        return ["GÜNLÜK ZARAR DURDURMA: -₺25 aşıldı, yeni alım yok"]

    for sym in SYMBOLS:
        ok_rev, why = reversal_ok(sym)
        if not ok_rev:
            logs.append(f"{sym}: {why} → alım yok")
            continue
        px = t.price(sym) or 0
        target = px * (1 + TARGET_GAIN_PCT / 100)
        ok_gate, gmsg = gate(px, target)
        logs.append(gmsg)
        if not ok_gate:
            continue
        bal = t.asset_balance("TRY") or 0
        if bal < PER_TRADE:
            return logs + ["bakiye yetersiz"]
        qty = round(PER_TRADE / px, 8)
        res = t._order(sym, 0, qty, price_limit=px, post_only=True)
        if isinstance(res, dict) and res.get("ok"):
            st["position"] = {"symbol": sym, "qty": qty, "entry": px,
                              "target": target, "stop": px * (1 - STOP_LOSS_PCT / 100),
                              "at": time.time()}
            _save(st)
            logs.append(f"ALIM: {sym} {qty} @ {px:.2f} · hedef {target:.2f} · stop {st['position']['stop']:.2f}")
        break
    return ["NET_KAR: " + x for x in logs]
