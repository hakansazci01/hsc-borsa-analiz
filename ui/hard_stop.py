"""HARD STOP — gerçek para koruması.

Katmanlar dolu değilse girişin %5 altında, 3 katman doluysa %7 altında
otomatik MARKET SATIŞ. DCA/PARTIAL satışlardan ÖNCE çalışır, çakışmaz.

Kural (kullanıcı onaylı):
  grid_layers >= 3  -> %7  (son DCA katmanı da dolu, daha geniş tolerans)
  grid_layers <  3  -> %5  (erken Stop — inatlaşma yok)
"""

from __future__ import annotations

from typing import Any

STOP_PCT_EARLY = 0.05
STOP_PCT_FULL = 0.07
FULL_LAYERS = 3


def stop_pct(pos: dict[str, Any]) -> float:
    # Yeni pozisyonlarda R/R kapısıyla belirlenen mikro stop (%1) kullanılır.
    # Eski pozisyonlarda (alan yok) felaket stop %5/%7 aynen korunur — dokunulmaz.
    micro = pos.get("micro_stop_pct")
    if micro:
        return float(micro)
    layers = int(pos.get("grid_layers", pos.get("micro_layers", 0)) or 0)
    return STOP_PCT_FULL if layers >= FULL_LAYERS else STOP_PCT_EARLY


def stop_price(pos: dict[str, Any]) -> float:
    entry = float(pos.get("entry", 0) or 0)
    return round(entry * (1 - stop_pct(pos)), 8)


def decision(pos: dict[str, Any], price: float) -> tuple[bool, str]:
    entry = float(pos.get("entry", 0) or 0)
    stop = stop_price(pos)
    pct = stop_pct(pos)
    if entry <= 0 or stop <= 0:
        return False, ""
    px = float(price)
    if px <= stop:
        return True, (f"HARD STOP: {pos.get('symbol', '?')} {stop:.8f}, "
                      f"zarar -%{pct*100:.0f}, satış yapıldı "
                      f"(giriş {entry:.8f}, şu an {px:.8f}, "
                      f"katman {int(pos.get('grid_layers', 0) or 0)}/3)")
    return False, ""
