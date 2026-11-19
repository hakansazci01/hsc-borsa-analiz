"""
Alpaca aracı kurum bağlantısı.

GÜVENLİK:
- `alpaca_paper` bölümü yalnızca paper (kurgusal) ortam içindir.
- `alpaca_live` bölümü GERÇEK PARA içindir ve yalnızca `ui.live_guard`
  tarafından tüm kilitler geçildiğinde kullanılmalıdır.
- Anahtar yoksa her iki yol da devre dışıdır. Bu modül kendi başına otomatik
  emir göndermez; her çağrı açık onay ve idempotency anahtarı gerektirir.
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


# ---------------------------------------------------------------------------
# GERÇEK PARA (varsayılan olarak erişilemez)
# ---------------------------------------------------------------------------

def live_configured() -> bool:
    """Gerçek canlı anahtarlar var mı? (değerleri göstermez)"""
    return bool(get("alpaca_live", "key_id") and get("alpaca_live", "secret_key"))


def _live_headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": get("alpaca_live", "key_id"),
        "APCA-API-SECRET-KEY": get("alpaca_live", "secret_key"),
        "Content-Type": "application/json",
    }


def live_base_url() -> str:
    return get("alpaca_live", "base_url", "https://api.alpaca.markets/v2").rstrip("/")


def live_account_status() -> dict[str, Any]:
    """Canlı hesap durumunu okur (anahtar yoksa başarısız)."""
    if not live_configured():
        return {"ok": False, "reason": "Canlı Alpaca anahtarı yapılandırılmadı."}
    if "paper-api" in live_base_url():
        return {"ok": False, "reason": "Canlı mod için paper endpoint kullanılamaz."}
    try:
        req = urllib.request.Request(live_base_url() + "/account", headers=_live_headers())
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return {
            "ok": True, "status": data.get("status"), "cash": data.get("cash"),
            "buying_power": data.get("buying_power"),
            "portfolio_value": data.get("portfolio_value"),
        }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reason": f"HTTP {exc.code}: kimlik bilgileri/izinler hatalı."}
    except Exception as exc:
        return {"ok": False, "reason": f"Bağlantı hatası ({type(exc).__name__})."}


def place_live_order(
    symbol: str,
    qty: float,
    side: str = "buy",
    client_order_id: str = "",
    limit_price: float | None = None,
) -> dict[str, Any]:
    """GERÇEK PARA emri — yalnızca tüm kilitler geçildikten sonra çağrılır."""
    if not live_configured():
        return {"ok": False, "reason": "Canlı anahtar yok; emir gönderilmedi."}
    if "paper-api" in live_base_url():
        return {"ok": False, "reason": "Paper endpoint canlı emir için kullanılamaz."}
    if side not in ("buy", "sell"):
        return {"ok": False, "reason": "Geçersiz emir yönü."}
    if not client_order_id:
        return {"ok": False, "reason": "Idempotency anahtarı (client_order_id) zorunlu."}
    payload: dict[str, Any] = {
        "symbol": symbol.upper(), "qty": str(qty), "side": side,
        "type": "limit" if limit_price else "market", "time_in_force": "day",
        "client_order_id": client_order_id[:48],
    }
    if limit_price:
        payload["limit_price"] = str(limit_price)
    try:
        req = urllib.request.Request(
            live_base_url() + "/orders",
            data=json.dumps(payload).encode(),
            headers=_live_headers(),
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return {
            "ok": True, "id": data.get("id"), "status": data.get("status"),
            "symbol": data.get("symbol"), "client_order_id": client_order_id,
        }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "reason": f"HTTP {exc.code}: {exc.read().decode()[:300]}"}
    except Exception as exc:
        return {"ok": False, "reason": f"Bağlantı hatası ({type(exc).__name__})."}
