"""EKONOMİK SAĞLIK — process health değil, sistemin para yapıp yapmadığını izler.

Profesyonel botlarda (Medium/3Commas/Finelo 2026) standart kontroller:
  - 72+ saat successful trade yoksa uyar
  - saatlik hata sayısı eşiği
  - bakiye minimum emir boyutunun altındaysa uyar
  - açık pozisyonun karşılığında stop/emir yoksa uyar
Sadece uyarır — emir vermez, stratejiye dokunmaz.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

from ui import auth, tr_scalper as t

ROOT = Path(__file__).resolve().parent.parent
LOG = auth.USERS_DIR / "autonomous_ops.log"
MIN_ORDER_TRY = 10.0
MAX_ERRORS_PER_HOUR = 20
NO_TRADE_HOURS = 72


def status() -> dict[str, Any]:
    alerts: list[str] = []
    now = time.time()

    # 1) Son gerçek işlem
    trades = ROOT / "trades.csv"
    last_trade = "yok"
    hours_since = None
    if trades.exists():
        try:
            with trades.open(encoding="utf-8-sig", newline="") as fh:
                rows = list(csv.DictReader(fh))
            if rows:
                last_trade = str(rows[-1].get("tarih", "—"))
                ts = time.mktime(time.strptime(last_trade, "%Y-%m-%d %H:%M:%S"))
                hours_since = round((now - ts) / 3600, 1)
                if hours_since >= NO_TRADE_HOURS:
                    alerts.append(f"{hours_since:.0f} saattir işlem yok — strateji/veri kontrol et")
        except Exception:
            pass

    # 2) Son 1 saatteki hata sayısı
    errors = 0
    if LOG.exists():
        try:
            lines = LOG.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]
            for line in lines:
                if ("HATA" in line or "hata:" in line.lower()) and "[" in line:
                    stamp = line[1:20]
                    ts = time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S"))
                    if now - ts < 3600:
                        errors += 1
        except Exception:
            pass
    if errors >= MAX_ERRORS_PER_HOUR:
        alerts.append(f"son 1 saatte {errors} hata — eşik {MAX_ERRORS_PER_HOUR}")

    # 3) Bakiye minimum emir boyutu
    try:
        bal = t.available_try()
        if bal < MIN_ORDER_TRY:
            alerts.append(f"bakiye ₺{bal:.2f} < minimum emir ₺{MIN_ORDER_TRY}")
    except Exception:
        bal = 0.0
        alerts.append("bakiye API'den okunamadı")

    # 4) Açık pozisyonların stop/değerlendirme kaydı var mı
    st = t._load()
    positions = st.get("positions", [])
    if st.get("position"):
        positions = positions + [st["position"]]
    no_stop = [p.get("symbol") for p in positions
               if not (p.get("atr_stop") or p.get("locked_sl") or p.get("peak_tp"))]
    if no_stop:
        alerts.append("stop kaydı yok: " + ", ".join(no_stop))

    return {
        "ok": not alerts,
        "alerts": alerts,
        "last_trade": last_trade,
        "hours_since": hours_since,
        "errors_1h": errors,
        "balance": round(bal, 2),
        "open_positions": len(positions),
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
