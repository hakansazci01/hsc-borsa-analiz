"""
Veri kapısı (fail-closed): karar kullanıcıya gösterilmeden önce veriyi doğrular.

Bloomberg/TradingView/IBKR/Robinhood uygulamalarından öğrenilen ilkeler:
- Taze olmayan veri **taze gibi gösterilmez**
- Doğrulanamayan veride işlem önerisi **bastırılır** (fail closed)
- Gözlem (ham veri) ile yorum (sinyal) ayrı tutulur
- Anomali varsa sessizce devam edilmez, kullanıcıya açıkça bildirilir

Paper-only uygulamada en büyük risk, bozuk/eskimiş veriden üretilen
"makul görünen" bir AL sinyalidir. Bu modül tam olarak onu engeller.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import streamlit as st


MAX_AGE_MIN = 30          # 15 dk gecikmeli akış için üst sınır
MAX_ABS_CHANGE_PCT = 30   # günlük makul fiyat değişim bandı
MAX_JUMP_PCT = 15         # tek anda şüpheli sıçrama eşiği


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            moment = datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    elif isinstance(value, str) and value.strip():
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def age_minutes(value: Any) -> float | None:
    moment = _as_utc(value)
    if moment is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - moment).total_seconds() / 60.0)


def evaluate(
    symbol: str,
    decision: dict[str, Any] | None,
    snap: dict[str, Any] | None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Karar için veri kapısı sonucunu üretir."""
    info = (snap or {}).get("info") or {}
    price = info.get("price")
    change = info.get("change_pct")
    bid, ask = info.get("bid"), info.get("ask")
    source = str((snap or {}).get("quote_source") or "—")
    age = age_minutes(info.get("quote_time") or (snap or {}).get("fetched_at"))

    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool | None, detail: str, blocking: bool = True) -> None:
        checks.append({"Kontrol": name, "Geçti": ok, "Detay": detail, "Kritik": blocking})

    try:
        price_value = float(price) if price is not None else float("nan")
    except (TypeError, ValueError):
        price_value = float("nan")
    add(
        "Fiyat geçerli",
        bool(math.isfinite(price_value) and price_value > 0),
        f"Fiyat: {price if price is not None else 'yok'}",
    )

    try:
        change_value = float(change) if change is not None else None
    except (TypeError, ValueError):
        change_value = None
    if change_value is None:
        add("Fiyat değişim bandı", None, "Değişim verisi yok", blocking=False)
    else:
        add(
            "Fiyat değişim bandı",
            abs(change_value) <= MAX_ABS_CHANGE_PCT,
            f"Günlük değişim %{change_value:+.2f} (sınır ±%{MAX_ABS_CHANGE_PCT})",
        )
        if abs(change_value) > MAX_JUMP_PCT:
            add(
                "Ani sıçrama kontrolü", False,
                f"Tek seanslık %{change_value:+.2f} hareket şüpheli; veriyi doğrulayın",
                blocking=False,
            )

    if bid is not None and ask is not None:
        try:
            bid_ok = float(bid) <= float(ask)
        except (TypeError, ValueError):
            bid_ok = False
        add("Alış/satış tutarlı", bid_ok, f"Alış {bid} / Satış {ask}", blocking=False)
    else:
        add("Alış/satış tutarlı", None, "Tek kotasyon (bid/ask yok)", blocking=False)

    add(
        "Kaynak bilgisi var",
        bool(source and source not in ("—", "unknown", "None")),
        f"Kaynak: {source}",
    )

    if age is None:
        add("Veri tazeliği", None, "Zaman damgası yok — tazelik doğrulanamadı", blocking=False)
    else:
        add(
            "Veri tazeliği",
            age <= MAX_AGE_MIN,
            f"Veri {age:.0f} dk önce alındı (sınır {MAX_AGE_MIN} dk)",
        )

    if st.session_state.get("signals_off"):
        add("Sinyel anahtarı", False, "Kullanıcı sinyalleri kapattı (kill switch)")

    failed = [c for c in checks if c["Geçti"] is False]
    critical_failed = [c for c in failed if c["Kritik"]]
    unknown = [c for c in checks if c["Geçti"] is None]

    if critical_failed:
        level = "fail"
        note = "Veri kapısı **reddetti**: " + critical_failed[0]["Detay"] + " Sinyal bastırıldı."
    elif failed:
        level = "warn"
        note = "Veri anomalisi: " + failed[0]["Detay"] + " Temkinli olun."
    elif unknown:
        level = "warn"
        note = "Bazı kontroller doğrulanamadı: " + unknown[0]["Detay"]
    else:
        level = "ok"
        note = "Veri kapısı geçti: fiyat, kaynak ve tazelik tutarlı."

    return {
        "symbol": str(symbol).upper(),
        "level": level,
        "note": note,
        "checks": checks,
        "age_min": round(age, 1) if age is not None else None,
        "source": source,
        "decision_id": (
            f"{str(symbol).upper()}|{(decision or {}).get('decision') or (decision or {}).get('action') or 'BEKLE'}"
            f"|{int(age // 5) if age is not None else 'x'}"
        ),
    }


def apply_gate(decision: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed: kritik doğrulama hatasında kararı BEKLE'ye çeker."""
    result = dict(decision)
    if gate.get("level") != "fail":
        return result
    key = "action" if "action" in result else "decision"
    result[key] = "BEKLE"
    result["confidence"] = min(int(result.get("confidence", 0) or 0), 30)
    reasons = list(result.get("reasons", []) or [])
    reasons.append("Veri kapısı doğrulanamadı; sinyal bastırıldı (fail-closed).")
    result["reasons"] = reasons
    result["gated"] = True
    return result


def render(gate: dict[str, Any]) -> None:
    """Kapı sonucunu açık, renkli ve tek satırda gösterir."""
    palette = {"ok": "green", "warn": "orange", "fail": "red"}
    label = {"ok": "Doğrulandı", "warn": "Temkinli", "fail": "Engellendi"}[gate["level"]]
    st.badge(f"Veri kapısı: {label}", icon=":material/verified:", color=palette[gate["level"]],
             help="Karar gösterilmeden önce fiyat, kaynak ve tazelik kontrol edilir.")
    st.caption(gate["note"])
