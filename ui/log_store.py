"""
Güvenli, dönebilen JSONL günlük katmanı.

- Kullanıcıdan gelen alanlardaki satır/control karakterlerini temizler
  (log injection -> sahte kayıt engellenir)
- Her kaydı `json.dumps` ile yazar (asla f-string ile JSON kurulmaz)
- Boyut tabanlı rotasyon ve saklama sınırı uygular
- Aynı dosya için yazma kilidi kullanır (Streamlit çoklu rerun / thread)
"""

from __future__ import annotations

import json
import math
import re
import threading
from pathlib import Path
from typing import Any


DEFAULT_MAX_BYTES = 2_000_000   # 2 MB
DEFAULT_KEEP = 3
_MAX_FIELD = 500
_CONTROL = re.compile(r"[\x00-\x1f\x7f]+")

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


def sanitize(value: Any, depth: int = 0) -> Any:
    """Kaydedilecek değeri güvenli hale getirir."""
    if depth > 4:
        return "[derinlik sınırı]"
    if isinstance(value, str):
        cleaned = _CONTROL.sub(" ", value)
        cleaned = " ".join(cleaned.split())
        return cleaned[:_MAX_FIELD]
    if isinstance(value, dict):
        return {str(k)[:80]: sanitize(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, depth + 1) for v in value[:50]]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def append(path: Path, record: dict[str, Any], *, max_bytes: int = DEFAULT_MAX_BYTES,
           keep: int = DEFAULT_KEEP) -> bool:
    """Tek bir JSON satırı ekler; gerekirse dosyayı döndürür."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(sanitize(record), ensure_ascii=False, default=str) + "\n"
    with _lock_for(path):
        if path.exists() and path.stat().st_size + len(line.encode("utf-8")) > max_bytes:
            _rotate(path, keep)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    return True


def _rotate(path: Path, keep: int) -> None:
    for index in range(keep - 1, 0, -1):
        source = path.with_suffix(path.suffix + f".{index}")
        target = path.with_suffix(path.suffix + f".{index + 1}")
        if source.exists():
            if target.exists():
                target.unlink()
            source.rename(target)
    first = path.with_suffix(path.suffix + ".1")
    if first.exists():
        first.unlink()
    path.rename(first)


def read(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    """Son kayıtları döndürür (önce aktif dosya, sonra en yeni yedek)."""
    files = [path] + [path.with_suffix(path.suffix + f".{i}")
                      for i in range(DEFAULT_KEEP, 0, -1)]
    rows: list[str] = []
    for file in files:
        if not file.exists():
            continue
        try:
            rows.extend(
                line for line in file.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        except (OSError, ValueError):
            continue
    result: list[dict[str, Any]] = []
    for line in rows[-limit:]:
        try:
            result.append(json.loads(line))
        except ValueError:
            continue
    return result


def stats(path: Path) -> dict[str, Any]:
    active = path.stat().st_size if path.exists() else 0
    backups = [path.with_suffix(path.suffix + f".{i}") for i in range(1, DEFAULT_KEEP + 1)]
    backup_bytes = sum(p.stat().st_size for p in backups if p.exists())
    return {
        "active_bytes": active,
        "backup_bytes": backup_bytes,
        "backups": sum(1 for p in backups if p.exists()),
        "active_kb": round(active / 1024, 1),
        "rotation_at_kb": round(DEFAULT_MAX_BYTES / 1024),
    }
