"""
Yerel kullanıcı hesapları ve kullanıcıya özel veri yönetimi.

GÜVENLİK NOTU:
- Şifreler asla düz metin saklanmaz; PBKDF2-HMAC-SHA256 + rastgele tuz kullanılır.
- Bu, tek makinede çalışan yerel bir oturum sistemidir; üretim amaçlı kimlik
  doğrulama için Streamlit'in `st.login()` + OIDC çözümü önerilir.
- Kullanıcı verileri users/<kullanici>/ altında tutulur ve .gitignore ile dışlanır.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from pathlib import Path
from typing import Any

import streamlit as st


ROOT = Path(__file__).resolve().parent.parent
USERS_DIR = ROOT / "users"
ACCOUNTS_FILE = USERS_DIR / "accounts.json"
ITERATIONS = 240_000


def _safe_name(username: str) -> str:
    name = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", name):
        raise ValueError("Kullanıcı adı 3-32 karakter, yalnızca küçük harf/rakam/_.- içermeli.")
    return name


def user_dir(username: str) -> Path:
    path = USERS_DIR / _safe_name(username)
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path(username: str) -> Path:
    return user_dir(username) / "settings.json"


def portfolio_path(username: str) -> Path:
    return user_dir(username) / "portfolio.json"


def history_path(username: str) -> Path:
    return user_dir(username) / "decisions.jsonl"


def _load_accounts() -> dict[str, Any]:
    if not ACCOUNTS_FILE.exists():
        return {}
    try:
        return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_accounts(accounts: dict[str, Any]) -> None:
    USERS_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_FILE.write_text(
        json.dumps(accounts, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def register(username: str, password: str) -> str:
    """Yeni kullanıcı oluşturur; başarılı olursa normalize kullanıcı adını döndürür."""
    name = _safe_name(username)
    if len(password) < 10:
        raise ValueError("Şifre en az 10 karakter olmalı.")
    accounts = _load_accounts()
    if name in accounts:
        raise ValueError("Bu kullanıcı adı zaten var.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()
    accounts[name] = {"salt": salt, "hash": digest, "created": _now()}
    _save_accounts(accounts)
    user_dir(name)  # dizin oluştur
    return name


def login(username: str, password: str) -> str:
    """Kimlik doğrular; başarılı olursa kullanıcı adını döndürür."""
    name = _safe_name(username)
    accounts = _load_accounts()
    record = accounts.get(name)
    if not record:
        # Kullanıcı varlığını sızdırmamak için aynı mesaj kullanılır
        raise ValueError("Geçersiz kullanıcı veya şifre.")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(record["salt"]), ITERATIONS
    ).hex()
    if not hmac.compare_digest(digest, record["hash"]):
        raise ValueError("Geçersiz kullanıcı veya şifre.")
    return name


def delete_account(username: str) -> None:
    """Hesabı ve tüm kullanıcı verilerini siler."""
    name = _safe_name(username)
    accounts = _load_accounts()
    accounts.pop(name, None)
    _save_accounts(accounts)
    import shutil

    target = USERS_DIR / name
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


def reset_user_data(username: str) -> None:
    """Ayarlar, portföy, geçmiş ve performans defterini siler; hesabı korur."""
    name = _safe_name(username)
    performance_path = user_dir(name) / "performance.jsonl"
    for path in (settings_path(name), portfolio_path(name), history_path(name), performance_path):
        if path.exists():
            path.unlink()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_history(username: str, record: dict[str, Any]) -> None:
    path = history_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_history(username: str, limit: int = 100) -> list[dict[str, Any]]:
    path = history_path(username)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except (OSError, ValueError):
        return []
    return rows[-limit:]


def current_user() -> str | None:
    return st.session_state.get("user")


def _now() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M:%S")
