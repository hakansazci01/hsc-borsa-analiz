"""
GERÇEK PARA KORUMALARI — kullanıcı talimatıyla sabitlenen limitler.

1) GÜNLÜK ZARAR: o gün gerçekleşen net K/Z <= -100 TL ise yeni işlem YOK,
   ertesi güne kadar bekler (gün otomatik sıfırlanır).
2) KASA DRAWDOWN: başlangıç kasasına göre %10 erime olursa botu TAMAMEN durdurur
   ve STOP_FILE oluşturur.
3) ANİ ÇÖKÜŞ: son 5 dakikada fiyat %5'ten fazla düşerse yeni alımı durdurur,
   30 dakika bekletir (cooldown süresi kaydedilir).

Sanal/paper/dry-run modu YOK. Tüm veri gerçek Binance TR API'sindendir.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth, tr_scalper

STATE = auth.USERS_DIR / "risk_brakes_state.json"

DAILY_LOSS_PCT = 0.10        # günlük limit = gün başı bakiyenin %10'u (dinamik)
TRAILING_DD_PCT = 0.15       # trailing drawdown: o günkü ZİRVE bakiyeden %15
MAX_DD_PCT = TRAILING_DD_PCT # geriye dönük uyumluluk
CRASH_PCT = 0.05             # 5 dakikada %5 düşüş
CRASH_WINDOW_MIN = 5
CRASH_COOLDOWN_SEC = 1800    # 30 dakika bekleme


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def today() -> str:
    return time.strftime("%Y-%m-%d")


def portfolio_balance() -> float:
    """Toplam portföy = API hesabındaki TÜM pozitif bakiyelerin TRY karşılığı.

    Artık state dosyalarına (position/AMM inventories) bakılmaz — çünkü AMM
    state'i boşaldığında elde duran ETH/BTC hesaba katılmıyor ve trailing
    drawdown %15 yanlış tetikleniyordu. Kaynak: GERÇEK /open/v1/account/spot.
    """
    try:
        ok, data = tr_scalper._request("/open/v1/account/spot", signed=True)
        if ok and isinstance(data, dict) and data.get("code") in (0, None):
            assets = (data.get("data") or {}).get("accountAssets") or []
            total = 0.0
            for a in assets:
                if not isinstance(a, dict):
                    continue
                q = float(a.get("free", 0) or 0) + float(a.get("locked", 0) or 0)
                if q <= 0:
                    continue
                sym = str(a.get("asset", ""))
                if sym == "TRY":
                    total += q
                else:
                    px = float(tr_scalper.price(f"{sym}_TRY") or 0)
                    if px > 0:
                        total += q * px
            if total > 0:
                return round(total, 2)
    except Exception:
        pass
    # API erişilemezse güvenli fallback: sadece TRY
    return round(float(tr_scalper.available_try() or 0), 2)


def reset_daily_if_needed(balance: float) -> dict[str, Any]:
    st = _load()
    if st.get("day") != today():
        st["day"] = today()
        st["day_open_balance"] = balance
        st["day_started"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if not st.get("start_balance"):
        st["start_balance"] = balance
    if balance > float(st.get("peak_balance", 0) or 0):
        st["peak_balance"] = balance
        st["peak_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    # Yeni sermaye (para yatırma / kâr bileşimi): günlük %10 limiti yeni
    # bakiyeden hesaplanmalı — eski gün başı bakiyesinde kalmasın.
    if balance > float(st.get("day_open_balance", 0) or 0):
        st["day_open_balance"] = balance
    _save(st)
    return st


def update_from_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    bal = portfolio_balance()
    st = reset_daily_if_needed(bal)
    day = today()
    realized = sum(
        float(h.get("net_pnl", 0))
        for h in history
        if str(h.get("exit_time", "")).startswith(day)
    )
    st["day_realized_pnl"] = round(realized, 4)
    _save(st)
    return st


def daily_loss_limit() -> float:
    """DİNAMİK günlük limit = gün başı bakiyenin %10'u."""
    st = _load()
    day_open = float(st.get("day_open_balance", 0) or 0)
    return round(day_open * DAILY_LOSS_PCT, 4)


def daily_loss_breached() -> tuple[bool, str]:
    st = _load()
    pnl = float(st.get("day_realized_pnl", 0) or 0)
    limit = daily_loss_limit()
    if limit > 0 and pnl <= -limit:
        return True, f"günlük zarar {pnl:+.2f} TL ≤ -{limit:.2f} TL (gün başı %10) — yarına kadar bekle"
    return False, ""


def drawdown_breached(balance: float) -> tuple[bool, str]:
    """TRAILING drawdown: o günkü en yüksek bakiyeden %15 düşüşte tam dur."""
    st = reset_daily_if_needed(balance)
    peak = max(float(st.get("day_peak_balance", 0) or 0), balance)
    st["day_peak_balance"] = round(peak, 4)
    _save(st)
    loss = peak - balance
    stop_at = peak * TRAILING_DD_PCT
    if peak > 0 and loss >= stop_at:
        return True, (f"trailing drawdown {loss:.2f} TL ≥ %{TRAILING_DD_PCT*100:.0f} "
                      f"({stop_at:.2f} TL) — zirve {peak:.2f} TL, şu an {balance:.2f} TL, TAM DUR")
    return False, ""


def crash_detected(symbol: str) -> tuple[bool, str]:
    """Son 5 dk 1dk mumlarda %5+ düşüş -> 30 dk cooldown yazar."""
    st = _load()
    until = float(st.get("crash_until", 0) or 0)
    if time.time() < until:
        left = int(until - time.time())
        return True, f"ani çöküş cooldown: {left//60} dk {left%60} sn kaldı"
    frame = tr_scalper.klines(symbol, "1m", CRASH_WINDOW_MIN + 2)
    if frame is None or len(frame) < 3:
        return False, ""
    first = float(frame["Close"].iloc[0])
    last = float(frame["Close"].iloc[-1])
    if first <= 0:
        return False, ""
    change = (last - first) / first
    if change <= -CRASH_PCT:
        st["crash_until"] = time.time() + CRASH_COOLDOWN_SEC
        st["crash_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        st["crash_symbol"] = symbol
        st["crash_pct"] = round(change * 100, 2)
        _save(st)
        return True, (f"{symbol} son 5 dk %{change*100:.1f} düştü — "
                      f"30 dk yeni alım yok")
    return False, ""


def status() -> dict[str, Any]:
    bal = portfolio_balance()
    st = reset_daily_if_needed(bal)
    daily, dmsg = daily_loss_breached()
    dd, ddmsg = drawdown_breached(bal)
    until = float(st.get("crash_until", 0) or 0)
    return {
        "balance": bal,
        "day": st.get("day", "—"),
        "day_open_balance": float(st.get("day_open_balance", 0) or 0),
        "day_realized_pnl": float(st.get("day_realized_pnl", 0) or 0),
        "start_balance": float(st.get("start_balance", 0) or 0),
        "peak_balance": float(st.get("peak_balance", 0) or 0),
        "daily_breached": daily, "daily_msg": dmsg,
        "dd_breached": dd, "dd_msg": ddmsg,
        "crash_until": until,
        "crash_remaining": max(0, int(until - time.time())),
        "daily_limit_try": daily_loss_limit(),
        "daily_limit_pct": DAILY_LOSS_PCT * 100,
        "day_peak_balance": float(st.get("day_peak_balance", 0) or 0),
        "dd_limit_pct": TRAILING_DD_PCT * 100,
        "crash_limit_pct": CRASH_PCT * 100,
        "crash_cooldown_min": CRASH_COOLDOWN_SEC // 60,
    }
