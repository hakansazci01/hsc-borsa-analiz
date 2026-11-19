"""
Gate.io adapter — bu ağda erişilebilen tek borsa olduğu için eklendi.

Varsayılan TESTNET (sanal para), çoklu kilit, imzalı istekler, idempotency
ve denetim kaydı. Anahtar değerleri yalnızca secrets.toml içinden okunur.
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


ARM_FILE = "gateio_armed.json"


def cfg(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings and isinstance(settings.get("gateio"), dict):
        return settings["gateio"]
    return dict(Config().get("gateio", default={}))


def configured() -> bool:
    return bool(get("gateio", "key") and get("gateio", "secret"))


def base_url(config: dict[str, Any] | None = None) -> str:
    config = config or cfg()
    if bool(config.get("testnet", True)):
        return str(config.get("base_test", "https://api-testnet.gateapi.io/api/v4")).rstrip("/")
    return str(config.get("base_live", "https://api.gateio.ws/api/v4")).rstrip("/")


def is_local_armed() -> bool:
    data = auth.read_json(auth.USERS_DIR / ARM_FILE, {})
    return bool(data.get("armed")) if isinstance(data, dict) else False


def set_local_armed(enabled: bool) -> None:
    auth.write_json(auth.USERS_DIR / ARM_FILE, {"armed": bool(enabled), "at": auth._now()})


def _symbol(symbol: str) -> str:
    value = symbol.upper().replace("-", "_")
    return value if "_" in value else value + "_USDT"


def _request(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    signed: bool = False,
    config: dict[str, Any] | None = None,
) -> tuple[bool, Any]:
    config = config or cfg()
    params = dict(params or {})
    query = urllib.parse.urlencode(params)
    full_path = "/api/v4" + path
    url = base_url(config) + path + ("?" + query if query else "")
    payload = json.dumps(body) if body is not None else ""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if signed:
        if not configured():
            return False, "Gate.io anahtarı yok"
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha512(payload.encode()).hexdigest()
        sign_string = f"{method}\n{full_path}\n{query}\n{body_hash}\n{timestamp}"
        headers.update({
            "KEY": get("gateio", "key"),
            "Timestamp": timestamp,
            "SIGN": hmac.new(get("gateio", "secret").encode(), sign_string.encode(), hashlib.sha512).hexdigest(),
        })
    try:
        req = urllib.request.Request(
            url, data=payload.encode() if payload else None, headers=headers, method=method
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode()[:200]}"
    except Exception as exc:
        return False, f"Bağlantı hatası ({type(exc).__name__})"


def ticker_price(symbol: str) -> float | None:
    ok, data = _request("GET", "/spot/tickers", {"currency_pair": _symbol(symbol)})
    if not ok or not isinstance(data, list) or not data:
        return None
    try:
        return float(data[0].get("last"))
    except (TypeError, ValueError):
        return None


def klines(symbol: str, interval: str = "15m", limit: int = 100) -> pd.DataFrame | None:
    ok, data = _request("GET", "/spot/candlesticks", {
        "currency_pair": _symbol(symbol), "interval": interval, "limit": limit,
    })
    if not ok or not isinstance(data, list) or not data:
        return None
    rows = []
    for item in data:
        try:
            rows.append({
                "Open": float(item[5]), "High": float(item[3]),
                "Low": float(item[4]), "Close": float(item[2]), "Volume": float(item[6]),
            })
        except (ValueError, TypeError, IndexError):
            continue
    return pd.DataFrame(rows) if rows else None


def quick_signal(symbol: str) -> dict[str, Any]:
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
    bull = ema9.iloc[-1] > ema20.iloc[-1] and float(rsi.iloc[-1]) > 50
    bear = ema9.iloc[-1] < ema20.iloc[-1] and float(rsi.iloc[-1]) < 50
    return {
        "decision": "AL" if bull else "SAT" if bear else "BEKLE",
        "price": float(close.iloc[-1]),
        "rsi": round(float(rsi.iloc[-1]), 1),
        "reason": "Gate.io 15m EMA9/20 + RSI7",
    }


def account_status() -> dict[str, Any]:
    ok, data = _request("GET", "/spot/accounts", signed=True)
    if not ok:
        return {"ok": False, "reason": str(data)}
    rows = [
        {"currency": r.get("currency"), "available": r.get("available")}
        for r in (data if isinstance(data, list) else [])
        if float(r.get("available", 0) or 0) > 0
    ]
    return {"ok": True, "balances": rows[:10]}


def guard(
    symbol: str, qty: float, price: float, phrase: str = "",
    session_armed: bool = False, settings: dict[str, Any] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    config = cfg(settings)
    reasons: list[str] = []
    if not bool(config.get("enabled", False)):
        reasons.append("config.yaml: gateio.enabled = false")
    if os.environ.get("HSC_GATEIO_ARMED") != "YES" and not is_local_armed():
        reasons.append("Ortam kilidi yok (HSC_GATEIO_ARMED veya paneldeki yerel kilit)")
    if str(phrase).strip() != str(config.get("confirmation_phrase", "HSC-GATEIO-ARM")):
        reasons.append("Onay ifadesi eksik/yanlış")
    if not session_armed:
        reasons.append("Oturum onayı verilmedi")
    if not configured():
        reasons.append("Gate.io anahtarı yapılandırılmadı")
    if not bool(config.get("testnet", True)) and os.environ.get("HSC_GATEIO_LIVE") != "YES":
        reasons.append("Canlı mod için HSC_GATEIO_LIVE=YES gerekli")
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
        audit_log.append(username, "GATEIO_EMIR_ENGELLENDI", {
            "symbol": symbol, "decision": side, "gate": "locked", "source": "gateio kilidi",
            "idempotency_key": f"gateblock|{symbol}|{side}|{auth._now()[:16]}",
        })
        return {"ok": False, "reason": "Emir gönderilmedi: " + "; ".join(reasons)}

    key = f"gate|{username}|{_symbol(symbol)}|{side}|{qty}|{round(price, 4)}|{auth._now()[:10]}"
    path = auth.user_dir(username) / live_guard.ORDERS_FILE
    for row in log_store.read(path, 500):
        if str(row.get("idempotency_key")) == key:
            return {"ok": False, "reason": "Bu emir zaten kayıtlı (tekrar gönderilmedi)."}

    body = {
        "currency_pair": _symbol(symbol), "side": side.upper(), "type": "limit",
        "amount": str(qty), "price": str(price), "client_order_id": key[:40],
    }
    success, data = _request("POST", "/spot/orders", body=body, signed=True, config=config)
    result = {"ok": bool(success), "data" if success else "reason": data}
    log_store.append(path, {
        "time": auth._now(), "symbol": _symbol(symbol), "decision": side.upper(),
        "side": side, "qty": qty, "price": price, "ok": bool(success),
        "broker": "gateio", "testnet": bool(config.get("testnet", True)),
        "order_id": (data or {}).get("id") if isinstance(data, dict) else None,
        "source": "gateio", "idempotency_key": key,
    })
    audit_log.append(username, "GATEIO_EMIR_DENEMESI", {
        "symbol": symbol, "decision": side, "gate": "ok" if success else "hata",
        "source": "gateio", "idempotency_key": key + "|audit",
    })
    return result
