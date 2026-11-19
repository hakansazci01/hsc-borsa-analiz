"""
GERÇEK PARA emir kilitleri — varsayılan olarak her şey kapalıdır.

Tek bir toggle ile gerçek emir açılmaz. Aşağıdakilerin **tamamı** gerekir:
  1. config.yaml → live_trading.enabled: true
  2. Ortam değişkeni HSC_LIVE_ARMED=YES
  3. Arayüzde onay ifadesinin yazılması ve oturum onayı
  4. Canlı broker anahtarlarının secrets.toml içinde bulunması
  5. Kill switch kapalı olması
  6. Sembol izin listesi, tek emir/günlük emir limiti

Bu modül hiçbir anahtar değeri göstermez, saklamaz veya göndermez.
"""

from __future__ import annotations

import os
from typing import Any

from borsa_bot.config import Config

from ui import auth, broker, log_store


ORDERS_FILE = "hsc_live_orders.jsonl"


def _cfg(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if settings and isinstance(settings.get("live_trading"), dict):
        return settings["live_trading"]
    return dict(Config().get("live_trading", default={}))


def config(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Gerçek işlem ayarlarını döndürür (anahtar içermez)."""
    return _cfg(settings)


def _orders_path(username: str):
    return auth.user_dir(username) / ORDERS_FILE


def today_order_count(username: str) -> int:
    today = auth._now()[:10]  # dd.mm.YYYY
    return sum(
        1 for row in log_store.read(_orders_path(username), 500)
        if str(row.get("time", "")).startswith(today)
    )


def check(
    username: str,
    symbol: str,
    qty: float,
    price: float,
    phrase: str = "",
    session_armed: bool = False,
    settings: dict[str, Any] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Tüm kilitleri kontrol eder: (geçerli mi, nedenler, config)."""
    cfg = _cfg(settings)
    reasons: list[str] = []

    if not bool(cfg.get("enabled", False)):
        reasons.append("config.yaml: live_trading.enabled = false")
    if bool(cfg.get("require_env_armed", True)) and os.environ.get("HSC_LIVE_ARMED") != "YES":
        reasons.append("Ortam değişkeni HSC_LIVE_ARMED=YES değil")
    expected = str(cfg.get("confirmation_phrase", "HSC-LIVE-ARM"))
    if str(phrase).strip() != expected:
        reasons.append(f"Onay ifadesi eksik/yanlış ({expected})")
    if not session_armed:
        reasons.append("Oturum onayı verilmedi")
    if not broker.live_configured():
        reasons.append("Canlı broker anahtarları yapılandırılmadı")
    try:
        import streamlit as st

        if st.session_state.get("signals_off"):
            reasons.append("Kill switch açık")
    except Exception:
        pass

    allowed = [str(s).upper() for s in (cfg.get("allowed_symbols") or [])]
    symbol = str(symbol).upper()
    if not allowed or symbol not in allowed:
        reasons.append("Sembol izin listesinde yok (allowed_symbols)")

    max_order = float(cfg.get("max_order_tl", 5000) or 5000)
    if qty <= 0 or price <= 0 or qty * price > max_order:
        reasons.append(f"Emir tutarı sınırı aşıyor (≤ {max_order:,.0f} ₺)")

    max_daily = int(cfg.get("max_daily_orders", 3) or 3)
    if today_order_count(username) >= max_daily:
        reasons.append(f"Günlük emir sınırına ulaşıldı ({max_daily})")

    return (not reasons), reasons, cfg
