"""
Türkçe sayı, para ve yüzde biçimlendirmesi.

Finansal arayüzde `1234.5` yerine `1.234,50 ₺` görmek gerekir; aksi halde
binlik/ondalık ayrımı yanlış okunur. Harici bağımlılık kullanmadan,
Python'un locale'inden bağımsız biçimlendirme yapar.
"""

from __future__ import annotations

from typing import Any


def num(value: Any, decimals: int = 2) -> str:
    """1.234,56 biçiminde sayı."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number != number or number in (float("inf"), float("-inf")):
        return "∞" if number > 0 else "—"
    return f"{number:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def money(value: Any, decimals: int = 2, sign: bool = False) -> str:
    """1.234,56 ₺ / +1.234,56 ₺ biçiminde para."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    body = num(abs(number), decimals)
    prefix = "+" if sign and number > 0 else ("-" if number < 0 else "")
    return f"{prefix}{body} ₺"


def pct(value: Any, decimals: int = 2, sign: bool = False) -> str:
    """%12,34 / +%1,25 biçiminde yüzde."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    body = num(abs(number), decimals)
    prefix = "+" if sign and number > 0 else ("-" if number < 0 else "")
    return f"{prefix}%{body}"


def r_value(value: Any) -> str:
    """+2,15R biçiminde R çarpanı."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    prefix = "+" if number > 0 else ("-" if number < 0 else "")
    return f"{prefix}{num(abs(number), 2)}R"
