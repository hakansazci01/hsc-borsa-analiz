"""İŞLEM EKONOMİSİ — komisyonu yenmeyen emri hiç gönderme.

Araştırma (Binance TR 2026: maker %0.10 / taker %0.15):
  taker+taker   = %0.30 gidiş-dönüş
  maker+taker   = %0.25
  maker+maker   = %0.20  → net kârı %0.30'dan %0.40'a çıkarır

Kural: net TL kârı MIN_NET_TRY altındaysa işlem YOK. "Boşa işlem" sorunu
tamamen burada çözülür — mikro işlem 30 TL ise net 0.09 TL < 0.20 → iptal.
"""

from __future__ import annotations

from typing import Any

TAKER_PCT = 0.15
MAKER_PCT = 0.10
ROUND_TRIP_TAKER = 0.30
ROUND_TRIP_MAKER = 0.25
ROUND_TRIP_BOTH_MAKER = 0.20
MIN_NET_TRY = 0.15   # 50 TL @ maker çıkış → net 0.175 TL → geçer; 30 TL → 0.105 → atlanır
MICRO_TP_PCT = 1.50   # kullanıcı onayı: %0.6 → %1.5 (R/R için gerekli)


def net_try(cap_try: float, gross_pct: float,
            round_trip_pct: float = ROUND_TRIP_TAKER) -> float:
    net_pct = float(gross_pct) - float(round_trip_pct)
    return round(max(0.0, float(cap_try)) * net_pct / 100.0, 4)


def worth_it(cap_try: float, gross_pct: float = MICRO_TP_PCT,
             round_trip_pct: float = ROUND_TRIP_TAKER,
             min_net: float = MIN_NET_TRY) -> tuple[bool, str]:
    net = net_try(cap_try, gross_pct, round_trip_pct)
    ok = net >= float(min_net)
    detail = (f"Net kâr {net:.3f} TL (brüt %{gross_pct:.2f} - komisyon "
              f"%{round_trip_pct:.2f}) {'≥' if ok else '<'} eşik {min_net:.2f} TL"
              f" — {'EMİR AT' if ok else 'İŞLEM YAPILMAYACAK'}")
    return ok, detail


def best_round_trip(maker_exit: bool = False) -> float:
    return ROUND_TRIP_MAKER if maker_exit else ROUND_TRIP_TAKER
