"""
Binance TR adapter — global Binance'den AYRI borsa.

Farklar:
- Base URL: https://www.binance.tr (global api.binance.com degil)
- Imzali hesap: GET /open/v1/account/spot
- Emir: POST /open/v1/orders  (symbol=BTC_USDT, side=0 AL / 1 SAT, type=1 LIMIT / 2 MARKET)
- Mum verisi: api.binance.me/api/v1/klines (sembolde "_" kaldirilir)

Anahtarlar yalnizca secrets.toml [binance_tr] bolumunden okunur; asla gosterilmez
veya gunluge yazilmaz. Varsayilan olarak emirler KILITLIDIR: config.yaml
binance_tr.enabled acik olmali, yerel/ortam kilidi, onay ifadesi, oturum onayi
ve canli mod ek ortam kilidi gerekir. Idempotency ve denetim kaydi vardir.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from borsa_bot.config import Config

from ui import audit_log, auth, log_store, live_guard
from ui.secrets_access import get


ARM_FILE = "binance_tr_armed.json"
BASE = "https://www.binance.tr"
KLINES_BASE = "https://api.binance.me/api/v1"


def cfg(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings and isinstance(settings.get("binance_tr"), dict):
        return settings["binance_tr"]
    return dict(Config().get("binance_tr", default={}))


def configured() -> bool:
    return bool(get("binance_tr", "api_key") and get("binance_tr", "secret_key"))


def is_local_armed() -> bool:
    data = auth.read_json(auth.USERS_DIR / ARM_FILE, {})
    return bool(data.get("armed")) if isinstance(data, dict) else False


def set_local_armed(enabled: bool) -> None:
    auth.write_json(auth.USERS_DIR / ARM_FILE, {
        "armed": bool(enabled), "at": auth._now(),
    })


def _symbol(symbol: str) -> str:
    """BTCUSDT / BTC-USDT -> BTC_USDT (Binance TR formagi)."""
    value = str(symbol).upper().replace("-", "_").replace("/", "_")
    return value if "_" in value else value[:-4] + "_" + value[-4:]


def _request(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    signed: bool = False,
    method: str = "GET",
) -> tuple[bool, Any]:
    params = dict(params or {})
    headers: dict[str, str] = {"Accept": "application/json"}
    if signed:
        if not configured():
            return False, "Binance TR anahtarı yok"
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query = urllib.parse.urlencode(params)
        signature = hmac.new(
            get("binance_tr", "secret_key").encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        query += "&signature=" + signature
        headers["X-MBX-APIKEY"] = get("binance_tr", "api_key")
    else:
        query = urllib.parse.urlencode(params)

    url = BASE + path + ("?" + query if query else "")
    try:
        req = urllib.request.Request(
            url, data=b"" if method == "POST" else None, headers=headers, method=method
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode()[:200]}"
    except Exception as exc:
        return False, f"Bağlantı hatası ({type(exc).__name__})"


def account_status() -> dict[str, Any]:
    """GET /open/v1/account/spot — gerçek hesap verisi (bakiye yazdirilmaz)."""
    ok, data = _request("/open/v1/account/spot", signed=True)
    if not ok:
        return {"ok": False, "reason": str(data)}
    if isinstance(data, dict) and data.get("code") not in (0, None):
        return {"ok": False, "reason": f"API {data.get('code')}: {data.get('msg')}"}
    body = (data or {}).get("data") or {}
    # Binance TR bu alani "balances" degil "accountAssets" olarak dondurur.
    assets = body.get("accountAssets") or body.get("balances") or []
    balances = [
        {"asset": a.get("asset"), "free": a.get("free"), "locked": a.get("locked")}
        for a in assets
        if float(a.get("free", 0) or 0) > 0 or float(a.get("locked", 0) or 0) > 0
    ]
    return {
        "ok": True,
        "balances": balances[:10],
        "can_trade": bool(body.get("canTrade")),
        "can_withdraw": bool(body.get("canWithdraw")),
        "fields": sorted(body.keys())[:12],
    }


def klines(symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame | None:
    """Gercek mum verisi: api.binance.me (sembol type 1 icin)."""
    plain = _symbol(symbol).replace("_", "")
    url = (
        f"{KLINES_BASE}/klines?symbol={plain}"
        f"&interval={interval}&limit={limit}"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None
    rows = []
    for item in data:
        try:
            rows.append({
                "Open": float(item[1]), "High": float(item[2]),
                "Low": float(item[3]), "Close": float(item[4]), "Volume": float(item[5]),
            })
        except (ValueError, TypeError, IndexError):
            continue
    return pd.DataFrame(rows) if rows else None


def ticker_price(symbol: str) -> float | None:
    frame = klines(symbol, interval="1m", limit=1)
    if frame is None or frame.empty:
        return None
    return float(frame["Close"].iloc[-1])


def quick_signal(symbol: str) -> dict[str, Any]:
    """Binance TR 15m kapanmis mumlardan EMA9/20 + RSI7 sinyali."""
    frame = klines(symbol)
    if frame is None or len(frame) < 30:
        return {"decision": "BEKLE", "reason": "Yeterli mum verisi yok."}
    close = frame["Close"]
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema20 = close.ewm(span=20, adjust=False).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 7, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 7, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, float("nan")))
    price = float(close.iloc[-1])
    bull = ema9.iloc[-1] > ema20.iloc[-1] and float(rsi.iloc[-1]) > 50
    bear = ema9.iloc[-1] < ema20.iloc[-1] and float(rsi.iloc[-1]) < 50
    return {
        "decision": "AL" if bull else "SAT" if bear else "BEKLE",
        "price": price,
        "rsi": round(float(rsi.iloc[-1]), 1),
        "reason": "Binance TR 15m EMA9/20 + RSI7",
    }


def guard(
    symbol: str, qty: float, price: float, phrase: str = "",
    session_armed: bool = False, settings: dict[str, Any] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    config = cfg(settings)
    reasons: list[str] = []
    if not bool(config.get("enabled", False)):
        reasons.append("config.yaml: binance_tr.enabled = false")
    if os.environ.get("HSC_BINANCE_TR_ARMED") != "YES" and not is_local_armed():
        reasons.append("Ortam kilidi yok (HSC_BINANCE_TR_ARMED veya paneldeki yerel kilit)")
    if str(phrase).strip() != str(config.get("confirmation_phrase", "HSC-BINANCE-TR-ARM")):
        reasons.append("Onay ifadesi eksik/yanlış")
    if not session_armed:
        reasons.append("Oturum onayı verilmedi")
    if not configured():
        reasons.append("Binance TR anahtarı yapılandırılmadı")
    if os.environ.get("HSC_BINANCE_TR_LIVE") != "YES":
        reasons.append("Canlı emir için HSC_BINANCE_TR_LIVE=YES gerekli")
    try:
        import streamlit as st

        if st.session_state.get("signals_off"):
            reasons.append("Kill switch açık")
    except Exception:
        pass
    allowed = [_symbol(s) for s in (config.get("allowed_symbols") or [])]
    if _symbol(symbol) not in allowed:
        reasons.append("Sembol izin listesinde yok")
    max_usdt = float(config.get("max_order_usdt", 50) or 50)
    if qty <= 0 or price <= 0 or qty * price > max_usdt:
        reasons.append(f"Emir tutarı sınırı aşıyor (≤ {max_usdt:,.0f} USDT)")
    return (not reasons), reasons, config


def execute(
    username: str, symbol: str, side: str, qty: float, price: float,
    phrase: str = "", session_armed: bool = False,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ok, reasons, config = guard(symbol, qty, price, phrase, session_armed, settings)
    if not ok:
        audit_log.append(username, "BINANCE_TR_EMIR_ENGELLENDI", {
            "symbol": symbol, "decision": side, "gate": "locked", "source": "binance tr kilidi",
            "idempotency_key": f"btrblock|{symbol}|{side}|{auth._now()[:16]}",
        })
        return {"ok": False, "reason": "Emir gönderilmedi: " + "; ".join(reasons)}

    sym = _symbol(symbol)
    key = f"btr|{username}|{sym}|{side}|{qty}|{round(price, 4)}|{auth._now()[:10]}"
    path = auth.user_dir(username) / live_guard.ORDERS_FILE
    for row in log_store.read(path, 500):
        if str(row.get("idempotency_key")) == key:
            return {"ok": False, "reason": "Bu emir zaten kayıtlı (tekrar gönderilmedi)."}

    side_code = 0 if str(side).upper() in ("BUY", "AL") else 1
    payload: dict[str, Any] = {
        "symbol": sym,
        "side": side_code,
        "type": 1,  # LIMIT
        "quantity": str(qty),
        "price": str(price),
        "timeInForce": "GTC",
    }
    success, data = _request("/open/v1/orders", payload, signed=True, method="POST")
    if isinstance(data, dict) and data.get("code") not in (0, None):
        success = False
        data = f"API {data.get('code')}: {data.get('msg')}"
    result = {"ok": bool(success), "data" if success else "reason": data}
    log_store.append(path, {
        "time": auth._now(), "symbol": sym, "decision": str(side).upper(),
        "side": side, "qty": qty, "price": price, "ok": bool(success),
        "broker": "binance_tr", "testnet": False,
        "order_id": (data or {}).get("data", {}).get("orderId") if isinstance(data, dict) else None,
        "source": "binance_tr", "idempotency_key": key,
    })
    audit_log.append(username, "BINANCE_TR_EMIR_DENEMESI", {
        "symbol": symbol, "decision": side, "gate": "ok" if success else "hata",
        "source": "binance_tr", "idempotency_key": key + "|audit",
    })
    return result
