"""
Alpaca paper (kurgusal) aracı kurum bağlantısı.

GÜVENLİK: Yalnızca paper-api.alpaca.markets kullanılır. Gerçek canlı
endpoint asla kullanılmaz. Secret key yoksa tüm işlevler devre dışıdır.
Bu modül otomatik emir göndermez; çağrılan her işlem açık onay gerektirir.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ui.secrets_access import get


def configured() -> bool:
    return bool(get("alpaca_paper", "key_id") and get("alpaca_paper", "secret_key"))


def _headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": get("alpaca_paper", "key_id"),
        "APCA-API-SECRET-KEY": get("alpaca_paper", "secret_key"),
        "Content-Type": "application/json",
    }


def account_status() -> dict[str, Any]:
    """Paper hesap durumunu döndürür; yapılandırma yoksa nedenini bildirir."""
    if not configured():
        return {"ok": False, "reason": "Alpaca secret key eksik. alpaca.markets API Keys sayfasından ekleyin."}
    base = get("alpaca_paper", "base_url", "https://paper-api.alpaca.markets/v2")
    url = base.rstrip("/") + "/account"
    try:
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return {
            "ok": True,
            "status": data.get("status"),
            "cash": data.get("cash"),
            "buying_power": data.get("buying_power"),
            "portfolio_value": data.get("portfolio_value"),
            "currency": data.get("currency"),
        }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reason": f"HTTP {exc.code}: kimlik bilgileri veya izinler hatalı olabilir."}
    except Exception as exc:
        return {"ok": False, "reason": f"Bağlantı hatası ({type(exc).__name__})."}


def place_paper_order(symbol: str, qty: float, side: str = "buy") -> dict[str, Any]:
    """
    YALNIZCA paper ortamında emir oluşturur.
    Bu fonksiyon arayüz tarafından otomatik çağrılmaz; kullanıcı açıkça onaylamadan
    emir gönderilmemelidir.
    """
    if side not in ("buy", "sell"):
        return {"ok": False, "reason": "Geçersiz emir yönü."}
    if not configured():
        return {"ok": False, "reason": "Alpaca yapılandırılmadı."}
    base = get("alpaca_paper", "base_url", "https://paper-api.alpaca.markets/v2")
    payload = json.dumps({
        "symbol": symbol.upper(), "qty": str(qty), "side": side,
        "type": "market", "time_in_force": "day",
    }).encode()
    req = urllib.request.Request(base.rstrip("/") + "/orders", data=payload, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return {"ok": True, "id": data.get("id"), "status": data.get("status"), "symbol": data.get("symbol")}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reason": f"HTTP {exc.code}: {exc.read().decode()[:160]}"}
    except Exception as exc:
        return {"ok": False, "reason": f"Bağlantı hatası ({type(exc).__name__})."}
