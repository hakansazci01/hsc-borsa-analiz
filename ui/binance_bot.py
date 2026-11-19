"""
Binance adapter — varsayılan TESTNET (sanal para), çoklu kilit, idempotency.

Binance API anahtarı *kullanıcı adı/şifre değildir*: para çekme yetkisi verilmeden,
IP kısıtlamasıyla üretilen sınırlı bir anahtardır. Anahtarlar yalnızca
`.streamlit/secrets.toml` içinden okunur, asla gösterilmez/günlüğe yazılmaz.

Kod: ui.live_guard ile aynı güvenlik felsefesini uygular; testnet varsayılandır.
Canlı mod için ek ortam kilidi gerekir.
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


def cfg(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings and isinstance(settings.get("binance"), dict):
        return settings["binance"]
    return dict(Config().get("binance", default={}))


def configured() -> bool:
    return bool(get("binance", "api_key") and get("binance", "secret_key"))


def base_url(config: dict[str, Any] | None = None) -> str:
    config = config or cfg()
    if bool(config.get("testnet", True)):
        return str(config.get("base_test", "https://testnet.binance.vision/api")).rstrip("/")
    return str(config.get("base_live", "https://api.binance.com/api")).rstrip("/")


def _request(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    signed: bool = False,
    method: str = "GET",
    config: dict[str, Any] | None = None,
) -> tuple[bool, Any]:
    config = config or cfg()
    params = dict(params or {})
    headers: dict[str, str] = {}
    if signed:
        if not configured():
            return False, "Binance anahtarı yok"
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query = urllib.parse.urlencode(params)
        signature = hmac.new(
            get("binance", "secret_key").encode(), query.encode(), hashlib.sha256
        ).hexdigest()
        query += "&signature=" + signature
        headers["X-MBX-APIKEY"] = get("binance", "api_key")
    else:
        query = urllib.parse.urlencode(params)

    url = base_url(config) + path + ("?" + query if query else "")
    try:
        req = urllib.request.Request(url, data=b"" if method == "POST" else None,
                                     headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode()[:200]}"
    except Exception as exc:
        return False, f"Bağlantı hatası ({type(exc).__name__})"


def account_status() -> dict[str, Any]:
    ok, data = _request("/v3/account", signed=True)
    if not ok:
        return {"ok": False, "reason": str(data)}
    balances = [
        {"asset": b.get("asset"), "free": b.get("free"), "locked": b.get("locked")}
        for b in (data.get("balances") or [])
        if float(b.get("free", 0) or 0) > 0 or float(b.get("locked", 0) or 0) > 0
    ]
    return {"ok": True, "balances": balances[:10]}


def ticker_price(symbol: str) -> float | None:
    ok, data = _request("/v3/ticker/price", {"symbol": symbol.upper()})
    if not ok or not isinstance(data, dict):
        return None
    try:
        return float(data.get("price"))
    except (TypeError, ValueError):
        return None


def klines(symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame | None:
    ok, data = _request("/v3/klines", {
        "symbol": symbol.upper(), "interval": interval, "limit": limit,
    })
    if not ok or not isinstance(data, list) or not data:
        return None
    rows = []
    for item in data:
        try:
            rows.append({
                "Open": float(item[1]), "High": float(item[2]),
                "Low": float(item[3]), "Close": float(item[4]), "Volume": float(item[5]),
            })
        except (ValueError, TypeError):
            continue
    return pd.DataFrame(rows) if rows else None


def quick_signal(symbol: str) -> dict[str, Any]:
    """Binance 15m kapanmış mumlardan basit EMA9/20 + RSI7 sinyali."""
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
        "reason": "15m EMA9/20 + RSI7 uyumu",
    }


def guard(
    symbol: str,
    qty: float,
    price: float,
    phrase: str = "",
    session_armed: bool = False,
    settings: dict[str, Any] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    config = cfg(settings)
    reasons: list[str] = []
    if not bool(config.get("enabled", False)):
        reasons.append("config.yaml: binance.enabled = false")
    if os.environ.get("HSC_BINANCE_ARMED") != "YES":
        reasons.append("HSC_BINANCE_ARMED=YES ortam değişkeni yok")
    if str(phrase).strip() != str(config.get("confirmation_phrase", "HSC-BINANCE-ARM")):
        reasons.append("Onay ifadesi eksik/yanlış")
    if not session_armed:
        reasons.append("Oturum onayı verilmedi")
    if not configured():
        reasons.append("Binance anahtarı yapılandırılmadı")
    if not bool(config.get("testnet", True)) and os.environ.get("HSC_BINANCE_LIVE") != "YES":
        reasons.append("Canlı mod için HSC_BINANCE_LIVE=YES gerekli")
    try:
        import streamlit as st

        if st.session_state.get("signals_off"):
            reasons.append("Kill switch açık")
    except Exception:
        pass
    allowed = [str(s).upper() for s in (config.get("allowed_symbols") or [])]
    if str(symbol).upper() not in allowed:
        reasons.append("Sembol izin listesinde yok")
    max_usdt = float(config.get("max_order_usdt", 50) or 50)
    if qty <= 0 or price <= 0 or qty * price > max_usdt:
        reasons.append(f"Emir tutarı sınırı aşıyor (≤ {max_usdt:,.0f} USDT)")
    return (not reasons), reasons, config


def execute(
    username: str,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    phrase: str = "",
    session_armed: bool = False,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ok, reasons, config = guard(symbol, qty, price, phrase, session_armed, settings)
    if not ok:
        audit_log.append(username, "BINANCE_EMIR_ENGELLENDI", {
            "symbol": symbol, "decision": side, "gate": "locked",
            "source": "binance kilidi",
            "idempotency_key": f"binblock|{symbol}|{side}|{auth._now()[:16]}",
        })
        return {"ok": False, "reason": "Emir gönderilmedi: " + "; ".join(reasons)}

    key = f"bin|{username}|{symbol.upper()}|{side}|{qty}|{round(price, 4)}|{auth._now()[:10]}"
    path = auth.user_dir(username) / live_guard.ORDERS_FILE
    for row in log_store.read(path, 500):
        if str(row.get("idempotency_key")) == key:
            return {"ok": False, "reason": "Bu emir zaten kayıtlı (tekrar gönderilmedi)."}

    payload = {
        "symbol": symbol.upper(), "side": side.upper(), "type": "MARKET",
        "quantity": str(qty), "newClientOrderId": key[:36],
    }
    success, data = _request("/v3/order", payload, signed=True, method="POST", config=config)
    result = {"ok": bool(success), "data" if success else "reason": data}
    log_store.append(path, {
        "time": auth._now(), "symbol": symbol.upper(), "decision": side.upper(),
        "side": side, "qty": qty, "price": price, "ok": bool(success),
        "broker": "binance", "testnet": bool(config.get("testnet", True)),
        "order_id": (data or {}).get("orderId") if isinstance(data, dict) else None,
        "source": "binance", "idempotency_key": key,
    })
    audit_log.append(username, "BINANCE_EMIR_DENEMESI", {
        "symbol": symbol, "decision": side, "gate": "ok" if success else "hata",
        "source": "binance", "idempotency_key": key + "|audit",
    })
    return result
