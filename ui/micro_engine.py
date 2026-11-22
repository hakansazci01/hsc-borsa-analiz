"""MİKRO + FIRSAT — iki motorlu, net kâr odaklı karar motoru.

Motor 1 MİKRO (%70): 3 katman grid %0.4/0.8/1.2 + mikro TP %0.4/%0.8.
                      Komisyon düşülünce net kâr <= 0 ise işlem YOK.
Motor 2 FIRSAT (%30): RSI<25 + 1s %3+ düşüş + VWAP altı + OBI 2:1 + CVD>0 + skor>=28.
                      %0.8-1.5 hedef, 1 saatte gelmezse breakeven kilidi.

TP1/TP2/TP3 (%0.8/1.5/2.5) AYNEN KALIR — mikro TP onların ALTINA eklenir.
Sadece karar üretir; emir vermez.限额 (risk) merkezi modüllerdedir.
"""

from __future__ import annotations

from typing import Any

MOTOR1_PCT = 0.70
MOTOR2_PCT = 0.30

# Motor 1 — mikro grid + mikro TP
MICRO_LAYERS = (0.004, 0.008, 0.012)
MICRO_TP = ((0.004, 0.50), (0.008, 0.50))
COMMISSION = 0.001          # Binance TR gerçek taker komisyonu (çift yön)

# Motor 2 — fırsat
OPP_RSI_MAX = 25.0
OPP_DROP_PCT = 3.0
OPP_SCORE_MIN = 28.0
OPB_RATIO = 2.0             # OBI 2:1
OPP_TARGET_MIN = 0.008
OPP_TARGET_MAX = 0.015
OPP_MAX_HOLD_SEC = 3600     # 1 saat


def capital_split(balance: float) -> dict[str, float]:
    """Sermayeyi iki motora ayır (ana para korunur, kârlarla büyür)."""
    bal = max(0.0, float(balance))
    return {"micro": round(bal * MOTOR1_PCT, 2),
            "opportunity": round(bal * MOTOR2_PCT, 2)}


def net_profit_pct(gain_pct: float, fee_rate: float = COMMISSION) -> dict[str, Any]:
    """Çift yön komisyonu düş, net kârı hesapla. <=0 ise işlem yapma."""
    gain = float(gain_pct)
    fee = 2.0 * float(fee_rate) * 100.0
    net = gain - fee
    return {"gross_pct": round(gain, 4), "commission_pct": round(fee, 4),
            "net_pct": round(net, 4), "ok": net > 0}


def micro_grid_decision(pos: dict[str, Any], price: float) -> tuple[str, str]:
    """Mikro grid katmanı: referanstan %0.4 / %0.8 / %1.2 düşüşte ek alım."""
    anchor = float(pos.get("grid_anchor") or pos.get("entry") or 0)
    layers = int(pos.get("micro_layers", pos.get("grid_layers", 0)) or 0)
    if anchor <= 0:
        return "HOLD", "referans yok"
    if layers >= len(MICRO_LAYERS):
        return "HOLD", "3 mikro katman dolu — TP bekleniyor"
    threshold = MICRO_LAYERS[layers]
    drop = (anchor - float(price)) / anchor
    if drop >= threshold:
        return ("ADD", f"MİKRO KATMAN {layers+1}/3: %{drop*100:.2f} ≥ %{threshold*100:.1f}")
    return ("HOLD", f"MİKRO KATMAN {layers+1} için %{threshold*100:.1f} düşüş gerekli "
                    f"(şu an %{drop*100:.2f})")


def micro_tp_decision(pos: dict[str, Any], price: float,
                      fee_rate: float = COMMISSION) -> tuple[str, float, str]:
    """Mikro TP: %0.4'te %50, %0.8'de kalanın %50'si — net kâr şartıyla."""
    entry = float(pos.get("entry", 0) or 0)
    stage = int(pos.get("micro_tp_stage", 0) or 0)
    if entry <= 0 or stage >= len(MICRO_TP):
        return "HOLD", 0.0, ""
    gain = (float(price) - entry) / entry
    threshold, ratio = MICRO_TP[stage]
    if gain + 1e-9 < threshold:
        return "HOLD", 0.0, ""
    chk = net_profit_pct(gain * 100, fee_rate)
    if not chk["ok"]:
        return ("SKIP", 0.0, f"Net kâr %{chk['net_pct']:.3f} ≤ 0 "
                             f"(brüt %{chk['gross_pct']:.3f}, komisyon %{chk['commission_pct']:.3f})")
    return ("MICRO_TP", ratio,
            f"MİKRO TP{stage+1}: kâr %{gain*100:.2f} · net %{chk['net_pct']:.3f} "
            f"(komisyon %{chk['commission_pct']:.3f}) → %{ratio*100:.0f} sat")


def obi_ratio(bids: list[list[Any]], asks: list[list[Any]]) -> dict[str, Any]:
    """Order Book Imbalance — alış hacmi satışın 2 katı mı?"""
    try:
        bid_sum = sum(float(x[1]) for x in (bids or [])[:5])
        ask_sum = sum(float(x[1]) for x in (asks or [])[:5])
    except (TypeError, ValueError, IndexError):
        return {"ok": False, "ratio": 0.0, "reason": "depth verisi okunamadı"}
    if ask_sum <= 0:
        return {"ok": False, "ratio": 0.0, "reason": "ask hacmi yok"}
    ratio = round(bid_sum / ask_sum, 3)
    return {"ok": ratio >= OPB_RATIO, "ratio": ratio,
            "reason": f"OBI {ratio:.2f}:1 {'≥' if ratio >= OPB_RATIO else '<'} 2:1"}


def fetch_cvd(symbol: str, limit: int = 100) -> dict[str, Any]:
    """Binance TR gerçek aggTrades'den CVD çek (hata olursa nötr döner)."""
    import json as _json
    import urllib.request as _url

    plain = symbol.replace("_", "")
    try:
        with _url.urlopen(
            f"https://api.binance.me/api/v1/aggTrades?symbol={plain}&limit={limit}",
            timeout=5,
        ) as r:
            rows = _json.loads(r.read().decode())
        return cvd(rows if isinstance(rows, list) else [])
    except Exception:
        return {"ok": False, "delta": 0.0, "reason": "CVD verisi alınamadı — fırsat motoru bekler"}


def cvd(aggtrades: list[dict[str, Any]]) -> dict[str, Any]:
    """Cumulative Volume Delta — gerçek alım baskısı (m - buyer is maker)."""
    buy = sell = 0.0
    for t in aggtrades or []:
        try:
            q = float(t.get("q", 0) or 0)
            if bool(t.get("m", False)):
                sell += q      # buyer maker → satıcı agresif
            else:
                buy += q       # alıcı agresif
        except (TypeError, ValueError):
            continue
    delta = round(buy - sell, 4)
    return {"ok": delta > 0, "delta": delta, "buy": round(buy, 4), "sell": round(sell, 4)}


def opportunity_entry(ind: dict[str, Any], obi: dict[str, Any],
                      cvd_data: dict[str, Any], score: float) -> tuple[bool, str]:
    """Motor 2 giriş koşulları — hepsi birlikte olmalı."""
    checks = {
        "RSI<25": float(ind.get("rsi", 100)) < OPP_RSI_MAX,
        "1s %3+ düşüş": float(ind.get("drop_pct", 0)) >= OPP_DROP_PCT,
        "VWAP altı": float(ind.get("vwap_dist", 0)) < 0,
        "OBI 2:1": bool(obi.get("ok")),
        "CVD pozitif": bool(cvd_data.get("ok")),
        "skor>=28": float(score) >= OPP_SCORE_MIN,
    }
    bad = [k for k, ok in checks.items() if not ok]
    detail = " · ".join(f"{k} {'OK' if ok else 'X'}" for k, ok in checks.items())
    return (not bad), detail


def opportunity_exit(pos: dict[str, Any], price: float, now_ts: float,
                     fee_rate: float = COMMISSION) -> tuple[str, str]:
    """Motor 2 çıkış: %0.8-1.5 hedef, 1 saatte gelmezse breakeven kilidi."""
    entry = float(pos.get("entry", 0) or 0)
    if entry <= 0:
        return "HOLD", "giriş yok"
    gain = (float(price) - entry) / entry
    held = now_ts - float(pos.get("entry_ts", now_ts))
    if OPP_TARGET_MIN <= gain <= OPP_TARGET_MAX:
        chk = net_profit_pct(gain * 100, fee_rate)
        if chk["ok"]:
            return ("SELL", f"FIRSAT hedefi %{gain*100:.2f} · net %{chk['net_pct']:.3f}")
    if gain > OPP_TARGET_MAX:
        return ("SELL", f"FIRSAT hedef aşıldı %{gain*100:.2f} — kârı al")
    if held >= OPP_MAX_HOLD_SEC and gain <= 0:
        return ("LOCK_BE", f"1 saat doldu, kâr yok — stop girişe ({entry:.4f}) çekildi")
    return "HOLD", ""
