"""
MANUEL MÜDAHALE KAYDI — kullanıcının elle yaptığı işlemleri ayrı dosyaya yazar.

Tespit yöntemleri:
1) Bot durdur/başlat: doğrudan emergency_stop/start çağrılarından kaydedilir.
2) Elle alım/satım: Binance TR emir-geçmişi endpoint'i bu API key'de izin vermediği
   (3700) için BAKİYE DEĞİŞİMİ ile tespit edilir. Bot emir atmadığı halde
   varlık bakiyesi değiştiyse -> "Elle Alım/Satım" olarak kaydedilir.

trades.csv SADECE botun kendi işlemleri — buraya ASLA yazılmaz.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from ui import auth, autonomous_ops, tr_scalper as t

CSV_FILE = t.ROOT / "manual_log.csv"
SNAPSHOT = auth.USERS_DIR / "manual_baseline.json"
COLUMNS = ["Tarih", "Saat", "Müdahale Türü", "Coin", "Miktar", "Not"]


def log(kind: str, coin: str = "", qty: Any = "", note: str = "") -> dict[str, Any]:
    """Manuel müdahaleyi manual_log.csv'ye yazar (trades.csv'ye ASLA)."""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    row = {"Tarih": now[:10], "Saat": now[11:], "Müdahale Türü": kind,
           "Coin": coin, "Miktar": qty, "Not": note}
    exists = CSV_FILE.exists()
    with CSV_FILE.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        if not exists:
            w.writeheader()
        w.writerow(row)
    autonomous_ops._log(f"MANUEL MÜDAHALE: {kind} · {coin} · {qty} · {note}")
    return row


def balances() -> dict[str, float]:
    """Gerçek Binance TR varlıklarından boş olmayan bakiyeler."""
    ok, data = t._request("/open/v1/account/spot", signed=True)
    if not (ok and isinstance(data, dict) and data.get("code") in (0, None)):
        return {}
    out = {}
    for a in (data.get("data", {}).get("accountAssets") or []):
        try:
            v = float(a.get("free", 0) or 0)
        except (TypeError, ValueError):
            v = 0.0
        if v > 0:
            out[a.get("asset", "?")] = v
    return out


def set_baseline() -> dict[str, float]:
    b = balances()
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
    return b


def detect_changes() -> list[dict[str, Any]]:
    """Bakiye değişiminden elle işlem tespit et (bot emri yoksa)."""
    try:
        prev = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    except Exception:
        set_baseline()
        return []
    now = balances()
    found = []
    for asset in set(prev) | set(now):
        diff = round(float(now.get(asset, 0)) - float(prev.get(asset, 0)), 8)
        if abs(diff) < 1e-8:
            continue
        kind = "Elle Alım" if diff > 0 else "Elle Satım"
        found.append(log(kind, asset, abs(diff),
                         "bakiye değişimi ile tespit edildi (bot emri yok)"))
    set_baseline()
    return found


def recent(limit: int = 5) -> list[dict[str, Any]]:
    if not CSV_FILE.exists():
        return []
    with CSV_FILE.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[-limit:]
