"""
ADIM 2 — Frenler: günlük zarar limiti + kasa drawdown kilidi + ani çöküş koruması.

Hiçbir fren "tahmin" değildir; gerçek bakiye, gerçek işlem geçmişi ve gerçek
fiyat değişimi üzerinden çalışır. Frenler YALNIZCA yeni girişi engeller veya
mevcut pozisyonu kapatır; yanlış yönde emir üretmez.

Kurallar:
1) Günlük zarar: o gün gerçekleşen net K/Z <= -DAILY_LOSS_PCT * açılış bakiyesi
   ise yeni giriş yok (ve açık pozisyon varsa kapatılır).
2) Kasa drawdown: mevcut bakiye, kaydedilmiş zirve bakiyeden %MAX_DD_PCT düştüyse
   yeni giriş yok.
3) Ani çöküş: son 5 dakikada fiyat %CRASH_PCT düşüş yaptıysa (gerçek 1dk mumlar),
   yeni giriş yok; açık pozisyon varsa stop'a çekilir.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth, tr_scalper

STATE = auth.USERS_DIR / "risk_brakes_state.json"

DAILY_LOSS_PCT = 0.03     # günlük %3
MAX_DD_PCT = 0.10         # kasa zirveden %10 düşüş
CRASH_PCT = 0.10          # 5 dakikada %10
CRASH_WINDOW_MIN = 5


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


def reset_daily_if_needed(balance: float) -> dict[str, Any]:
    st = _load()
    if st.get("day") != today():
        st["day"] = today()
        st["day_open_balance"] = balance
        st["day_started"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _save(st)
    return st


def sync_equity(balance: float) -> dict[str, Any]:
    """Zirve bakiyeyi güncelle (sadece yukarı yönde)."""
    st = reset_daily_if_needed(balance)
    peak = float(st.get("peak_balance", 0) or 0)
    if balance > peak:
        st["peak_balance"] = balance
        st["peak_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save(st)
    return st


def update_from_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Günlük gerçekleşen K/Z'i işlem geçmişinden hesapla."""
    st = reset_daily_if_needed(float(tr_scalper.available_try()))
    day = today()
    realized = sum(
        float(h.get("net_pnl", 0))
        for h in history
        if str(h.get("exit_time", "")).startswith(day)
    )
    st["day_realized_pnl"] = round(realized, 4)
    _save(st)
    return st


def daily_loss_breached() -> tuple[bool, str]:
    st = _load()
    day_open = float(st.get("day_open_balance", 0) or 0)
    pnl = float(st.get("day_realized_pnl", 0) or 0)
    if day_open <= 0:
        return False, ""
    limit = -day_open * DAILY_LOSS_PCT
    if pnl <= limit:
        return True, f"günlük zarar {pnl:+.2f} ₺ ≤ %{DAILY_LOSS_PCT*100:.0f} limit ({limit:.2f} ₺)"
    return False, ""


def drawdown_breached(balance: float) -> tuple[bool, str]:
    st = sync_equity(balance)
    peak = float(st.get("peak_balance", 0) or balance)
    if peak <= 0:
        return False, ""
    dd = (peak - balance) / peak
    if dd >= MAX_DD_PCT:
        return True, f"kasa drawdown %{dd*100:.1f} ≥ %{MAX_DD_PCT*100:.0f} (zirve {peak:.2f} ₺)"
    return False, ""


def crash_detected(symbol: str) -> tuple[bool, str]:
    """Son 5 adet 1dk mumda %10'dan fazla düşüş var mı?"""
    frame = tr_scalper.klines(symbol, "1m", CRASH_WINDOW_MIN + 2)
    if frame is None or len(frame) < 3:
        return False, ""
    first = float(frame["Close"].iloc[0])
    last = float(frame["Close"].iloc[-1])
    if first <= 0:
        return False, ""
    change = (last - first) / first
    if change <= -CRASH_PCT:
        return True, f"{symbol} 5dk içinde %{change*100:.1f} düştü"
    return False, ""


def status() -> dict[str, Any]:
    bal = tr_scalper.available_try()
    st = _load()
    daily, daily_msg = daily_loss_breached()
    dd, dd_msg = drawdown_breached(bal)
    return {
        "balance": bal,
        "day": st.get("day", "—"),
        "day_open_balance": float(st.get("day_open_balance", 0) or 0),
        "day_realized_pnl": float(st.get("day_realized_pnl", 0) or 0),
        "peak_balance": float(st.get("peak_balance", 0) or 0),
        "daily_breached": daily,
        "daily_msg": daily_msg,
        "dd_breached": dd,
        "dd_msg": dd_msg,
        "daily_limit_pct": DAILY_LOSS_PCT * 100,
        "dd_limit_pct": MAX_DD_PCT * 100,
        "crash_limit_pct": CRASH_PCT * 100,
    }
