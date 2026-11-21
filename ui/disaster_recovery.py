"""
YEDEK + FELAKET KURTARMA — her işlemden sonra 3 yere yedek.

1) trades.csv         (işlem kaydı)
2) users/tr_daily_state.json  (anlık state — açık pozisyon dahil)
3) backups/TTT_<dosya>        (tarihli kopya, saatlik)

Kurtarma: bot yeniden başladığında en son yedeği okur. Bozuksa bir önceki yedeği
dener. İkisi de bozuksa "YEDEK BOZUK" bildirimi + işlem yapma.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from ui import auth, autonomous_ops, tr_scalper as t

BACKUPS = t.ROOT / "backups"
STATE = t.ROOT / "users" / "tr_daily_state.json"
RECOVERY = t.ROOT / "users" / "recovery_state.json"
SOURCES = [t.TRADES_CSV, STATE, t.ROOT / "config.yaml"]


def _save_recovery(d: dict[str, Any]) -> None:
    RECOVERY.parent.mkdir(parents=True, exist_ok=True)
    RECOVERY.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def backup(reason: str = "işlem sonrası") -> dict[str, Any]:
 """3 yere yedek al, saatlik kayıt tut."""
 BACKUPS.mkdir(parents=True, exist_ok=True)
 stamp = time.strftime("%Y%m%d_%H%M%S")
 saved = []
 for src in SOURCES:
  if src.exists():
   dst = BACKUPS / f"{stamp}_{src.name}"
   shutil.copy2(src, dst)
   saved.append(dst.name)
 # son 30 günden eski yedekleri sil
 from datetime import datetime, timedelta
 cutoff = datetime.now() - timedelta(days=30)
 for f in BACKUPS.glob("*_trades.csv"):
  try:
   if datetime.strptime(f.name[:8], "%Y%m%d") < cutoff:
    f.unlink()
  except Exception:
   pass
 rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "reason": reason,
        "files": saved, "ok": bool(saved)}
 _save_recovery(rec)
 autonomous_ops._log(f"YEDEK ALINDI: {len(saved)} dosya ({reason})")
 return rec


def _valid_state(path: Path) -> dict[str, Any] | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def recover() -> dict[str, Any]:
    """Son yedeği yükle; bozuksa önceki yedeği dene."""
    candidates = [STATE]
    # tarihli yedekleri en yeniden eskiye doğru sırala
    dated = sorted(BACKUPS.glob("*_tr_daily_state.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    candidates.extend(dated)
    tried: list[str] = []
    for path in candidates:
        if not path.exists():
            continue
        tried.append(path.name)
        data = _valid_state(path)
        if data is not None:
            # Geçerli yedeği ana state'e geri yükle (açık pozisyon korunur)
            if path != STATE:
                shutil.copy2(path, STATE)
            rec = {"ok": True, "restored_from": path.name, "tried": tried,
                   "open_position": data.get("position", {}).get("symbol") if data.get("position") else None,
                   "at": time.strftime("%Y-%m-%d %H:%M:%S")}
            _save_recovery(rec)
            autonomous_ops._log(f"KURTARMA BAŞARILI: {path.name} · "
                                f"açık pozisyon: {rec['open_position'] or 'yok'}")
            return rec
    # ikisi de bozuk
    msg = "YEDEK BOZUK — hiçbir geçerli yedek bulunamadı, işlem yapılmıyor"
    autonomous_ops._log(msg)
    autonomous_ops._send("HSC YEDEK BOZUK", msg)
    rec = {"ok": False, "restored_from": None, "tried": tried, "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    _save_recovery(rec)
    return rec


def status() -> dict[str, Any]:
    try:
        d = json.loads(RECOVERY.read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return {
        "last_backup": d.get("at", "—"),
        "ok": bool(d.get("ok", False)),
        "status": "Sağlam ✅" if d.get("ok") else "Bozuk ❌",
        "restored_from": d.get("restored_from"),
        "open_position": d.get("open_position"),
        "recovery": "Başarılı ✅" if d.get("ok") and d.get("restored_from") else (
            "Bozuk ❌" if d.get("ok") is False else "Beklemede"),
    }


def block_on_corrupt() -> bool:
    """Yedek bozuksa işlem engelli mi?"""
    return status()["ok"] is False
