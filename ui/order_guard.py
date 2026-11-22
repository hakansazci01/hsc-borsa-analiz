"""
SLIPPAGE + EMİR DOLUM KONTROLÜ — her emirden önce/sonra gerçek kontrol.

Kurallar:
  - Maksimum slippage %1. Beklenen ile gerçek dolum fiyatı arası >%1 ise
    "SLIPPAGE YÜKSEK, EMİR İPTAL" ve emir gönderilmez/cancel edilir.
  - Emir gönderildikten sonra dolum kontrolü: dolmadıysa "EMİR DOLMADI" logla,
    3 kez tekrar dene. 3'ü de dolmazsa iptal et + ntfy bildirimi.
  - Her emirden sonra beklenen/gerçek fiyat ve slippage yüzdesi kaydedilir.

Sanal mod YOK. Limitler değişmez.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ui import auth, autonomous_ops, tr_scalper as t

MAX_SLIPPAGE = 0.01   # %1
MAX_RETRIES = 3
MAX_ORDERS_PER_MIN = 20   # Binance TR ORDERS limitinin çok altında — runaway önleme
STATE = auth.USERS_DIR / "order_guard_state.json"


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    # CUSUM fill-quality takibi — her gerçek dolum kaydında birikim güncellenir
    try:
        last = d.get("last") or {}
        if "slippage_pct" in last:
            from ui import safety_guards
            safety_guards.record_slippage(float(last["slippage_pct"]))
    except Exception:
        pass


def slippage(expected: float, actual: float) -> dict[str, Any]:
    """Beklenen ve gerçek fiyat arasındaki kayma yüzdesi."""
    if expected <= 0:
        return {"pct": 0.0, "ok": False}
    pct = abs(actual - expected) / expected
    return {"pct": round(pct * 100, 4), "ok": pct <= MAX_SLIPPAGE,
            "expected": expected, "actual": actual}


def allow_order() -> tuple[bool, str]:
    """Dakikadaki emir sayısını sınırla — hatalı döngüde borsayı bombinga tutmaz."""
    st = _load()
    now = time.time()
    recent = [float(x) for x in st.get("order_ts", []) if now - float(x) < 60]
    if len(recent) >= MAX_ORDERS_PER_MIN:
        return False, (f"EMİR HIZI SINIRI: {len(recent)}/{MAX_ORDERS_PER_MIN} "
                       "— 60 sn bekleniyor")
    st["order_ts"] = (recent + [now])[-100:]
    _save(st)
    return True, ""


def check_slippage(expected: float, actual: float) -> tuple[bool, str]:
    """Slippage >%1 ise emri IPTAL et."""
    s = slippage(expected, actual)
    if not s["ok"]:
        return False, (f"SLIPPAGE YÜKSEK, EMİR İPTAL: beklenen {expected:.4f}, "
                       f"gerçek {actual:.4f}, kayma %{s['pct']:.2f} > %{MAX_SLIPPAGE*100:.0f}")
    return True, f"slippage %{s['pct']:.2f} ≤ %{MAX_SLIPPAGE*100:.0f}"


def is_filled(data: dict[str, Any] | None) -> bool:
    """Binance TR emir cevabından dolum durumunu oku."""
    if not data or data.get("code") not in (0, None):
        return False
    body = data.get("data") or {}
    status = str(body.get("status", "")).upper()
    filled = body.get("filledQty") or body.get("executedQty") or body.get("cumQty") or 0
    try:
        filled = float(filled)
    except (TypeError, ValueError):
        filled = 0.0
    # status=FILLED veya dolan miktar > 0 ise dolmuş say
    return status in ("FILLED", "2", "TRADE") or filled > 0


def retry_order(send_fn, symbol: str, side: str, expected_px: float,
                attempts: int = MAX_RETRIES) -> dict[str, Any]:
    """Emri gönder, dolum kontrolü yap; dolmazsa 3 kez dene, sonra iptal."""
    for i in range(1, attempts + 1):
        data = send_fn()
        if is_filled(data):
            body = (data or {}).get("data") or {}
            actual = float(body.get("avgPrice") or body.get("price") or expected_px)
            ok, msg = check_slippage(expected_px, actual)
            rec = {"status": "Doldu" if ok else "İptal", "attempt": i,
                   "expected": expected_px, "actual": actual,
                   "slippage_pct": slippage(expected_px, actual)["pct"], "msg": msg}
            _save({"last": rec, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
            if not ok:
                autonomous_ops._log(msg)
                autonomous_ops._send("HSC SLIPPAGE İPTAL", msg)
            return rec
        autonomous_ops._log(f"EMİR DOLMADI: {symbol} {side} — deneme {i}/{attempts}")
        time.sleep(0.5)
    msg = f"EMİR İPTAL: {symbol} {side} — {attempts} denemede dolmadı"
    autonomous_ops._log(msg)
    autonomous_ops._send("HSC EMİR İPTAL", msg)
    rec = {"status": "İptal", "attempt": attempts, "expected": expected_px,
           "actual": None, "slippage_pct": 0.0, "msg": msg}
    _save({"last": rec, "at": time.strftime("%Y-%m-%d %H:%M:%S")})
    return rec


def last() -> dict[str, Any]:
    return _load().get("last", {})


def log_fill_to_csv(expected: float, actual: float, qty: float) -> None:
    """Gerçek dolumu trades.csv'ye beklenen/gerçek/slippage ile kaydet."""
    import csv

    s = slippage(expected, actual)
    row = {
        "tarih": time.strftime("%Y-%m-%d %H:%M:%S"), "sembol": "—",
        "alış_fiyatı": round(expected, 6), "satış_fiyatı": round(actual, 6),
        "adet": qty, "komisyon": 0, "komisyon_oranı": t.COMMISSION,
        "net_kar_zarar": 0, "işlem_süresi": "0 sn",
        "strateji_adı": f"beklenen={expected:.4f} gerçek={actual:.4f} slippage=%{s['pct']:.2f}",
    }
    cols = list(row.keys())
    exists = t.TRADES_CSV.exists()
    with t.TRADES_CSV.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        if not exists:
            w.writeheader()
        w.writerow(row)
