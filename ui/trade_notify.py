"""
Otonom sistem bildirimleri — yalnızca GERÇEK olaylarda çalışır.

Olaylar:
- Karar CLOSED -> OPEN değişimi (edge + rejim oluştu, motor açıldı)
- Gerçek emir atıldı / reddedildi
- Kill switch veya sistem hatası

Bildirim başarısızlığı işlemi ASLA engellemez (fail-open notification).
Konu config.yaml alerts.ntfy_topic içinden okunur.
"""

from __future__ import annotations

from typing import Any

from ui import notify


def _topic() -> str:
    try:
        from ui.core import default_settings

        return str(default_settings().get("alerts", {}).get("ntfy_topic", "") or "")
    except Exception:
        return ""


def enabled() -> bool:
    try:
        from ui.core import default_settings

        return bool(default_settings().get("alerts", {}).get("ntfy_enabled", False))
    except Exception:
        return False


def alert(title: str, message: str) -> bool:
    """Gerçek olay bildirimi gönderir; hata yutulur, işlem etkilenmez."""
    if not enabled():
        return False
    try:
        ok, _ = notify.send_ntfy(message, _topic(), title=title)
        return ok
    except Exception:
        return False


def decision_alert(decision: str, reasons: list[str], robust: int, accuracy: dict[str, Any]) -> None:
    msg = (
        f"Karar: {decision}\n"
        f"Edge: {robust}\n"
        f"İsabet: %{accuracy.get('rate', '—')} ({accuracy.get('n', 0)} test)\n"
        + ("Neden: " + "; ".join(reasons) if reasons else "Tüm koşullar sağlandı.")
    )
    alert("HSC Otonom Karar", msg)


def order_alert(symbol: str, side: str, qty: float, price: float,
                ok: bool, detail: str = "") -> None:
    status = "GERÇEK EMİR İLETİLDİ" if ok else "EMİR REDDEDİLDİ"
    msg = (
        f"{status}\n"
        f"{symbol} · {side.upper()} · {qty} adet · {price:,.4f} TL\n"
        f"{detail[:200]}"
    )
    alert("HSC CANLI İŞLEM", msg)
