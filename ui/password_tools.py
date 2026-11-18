"""
Şifre oluşturma ve güç değerlendirme yardımcıları.

Yalnızca Python `secrets` modülünü kullanır; harici bağımlılık yoktur.
Kayıt ekranında kullanıcıya güçlü bir şifre önerisi sunar.
"""

from __future__ import annotations

import secrets
import string
from typing import Any


ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}?."


def generate_password(length: int = 16) -> str:
    """Kriptografik olarak güvenli, karmaşık bir şifre üretir."""
    length = max(10, min(64, int(length)))
    while True:
        candidate = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if strength(candidate)["score"] >= 3:
            return candidate


def strength(password: str) -> dict[str, Any]:
    """Şifreyi 0-4 arası puanlar, kontrol listesi ve renk döndürür."""
    value = password or ""
    checks = {
        "En az 10 karakter": len(value) >= 10,
        "Büyük harf": any(c.isupper() for c in value),
        "Küçük harf": any(c.islower() for c in value),
        "Rakam": any(c.isdigit() for c in value),
        "Sembol": any(c in ALPHABET[-24:] for c in value),
    }
    score = sum(1 for ok in checks.values() if ok)
    # Beş kontrol birden geçebilir; etiketler 0-4 aralığındadır.
    score = 4 if len(value) >= 16 else min(score, 4)
    labels = {0: "Çok zayıf", 1: "Zayıf", 2: "Orta", 3: "Güçlü", 4: "Çok güçlü"}
    colors = {0: "red", 1: "orange", 2: "yellow", 3: "green", 4: "green"}
    return {
        "score": score,
        "label": labels[score],
        "color": colors[score],
        "checks": checks,
        "valid": score >= 3,
    }
