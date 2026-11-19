"""
Yapılandırma Doktoru.

config.yaml, secrets.toml, kullanıcı JSON'ları ve sonuç dosyalarını doğrular;
bozuk veya tutarsız ayarları "hangi dosya / hangi alan / nasıl düzeltilir" diye
raporlar. Hiçbir dosyayı otomatik değiştirmez.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ui import auth


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"
RESULTS_DIR = ROOT / "results"

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_ERROR = "error"

STATUS_LABEL = {STATUS_OK: "Geçerli", STATUS_WARN: "Uyarı", STATUS_ERROR: "Hata"}
STATUS_COLOR = {STATUS_OK: "green", STATUS_WARN: "orange", STATUS_ERROR: "red"}


SETTINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["symbols", "period", "interval", "profile", "signal", "signal_weights", "risk"],
    "properties": {
        "symbols": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "period": {"type": "string"},
        "interval": {"type": "string"},
        "profile": {"type": "string"},
        "signal": {"type": "object"},
        "signal_weights": {"type": "object"},
        "risk": {"type": "object"},
        "guards": {"type": "object"},
    },
}

PORTFOLIO_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["id", "symbol", "qty", "entry_price"],
        "properties": {
            "id": {"type": "string"},
            "symbol": {"type": "string"},
            "qty": {"type": "number"},
            "entry_price": {"type": "number"},
        },
    },
}


def _result(title: str, status: str, detail: str, fix: str = "") -> dict[str, str]:
    return {"title": title, "status": status, "detail": detail, "fix": fix}


def check_yaml() -> dict[str, str]:
    if not CONFIG_PATH.exists():
        return _result("config.yaml", STATUS_ERROR, "Dosya bulunamadı.", "Proje kökünde config.yaml oluşturun.")
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return _result(
            "config.yaml", STATUS_ERROR,
            f"YAML sözdizimi hatası: {str(exc).splitlines()[0][:120]}",
            "Girintilemeyi ve ':' kullanımını kontrol edin.",
        )

    required = ["symbols", "data", "indicators", "signal", "signal_weights", "risk"]
    missing = [k for k in required if k not in data]
    if missing:
        return _result(
            "config.yaml", STATUS_ERROR,
            f"Eksik bölümler: {', '.join(missing)}",
            "config.yaml içinde bu bölümleri tanımlayın.",
        )

    problems: list[str] = []
    symbols = data.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        problems.append("symbols boş veya liste değil")
    elif not all(isinstance(s, str) for s in symbols):
        problems.append("symbols içinde string olmayan değer var")

    signals = data.get("signal", {})
    for key in ("strong_buy", "buy", "sell", "strong_sell"):
        value = signals.get(key)
        if not isinstance(value, (int, float)):
            problems.append(f"signal.{key} sayı değil")

    if isinstance(signals.get("buy"), (int, float)) and isinstance(signals.get("strong_buy"), (int, float)):
        if signals["strong_buy"] < signals["buy"]:
            problems.append("strong_buy, buy'dan küçük olamaz")
    if isinstance(signals.get("sell"), (int, float)) and isinstance(signals.get("strong_sell"), (int, float)):
        if signals["strong_sell"] > signals["sell"]:
            problems.append("strong_sell, sell'den büyük olamaz")

    ind = data.get("indicators", {})
    os_, ob = ind.get("rsi_oversold"), ind.get("rsi_overbought")
    if isinstance(os_, (int, float)) and isinstance(ob, (int, float)) and os_ >= ob:
        problems.append("rsi_oversold, rsi_overbought'dan küçük olmalı")

    weights = data.get("signal_weights", {})
    if not isinstance(weights, dict) or not weights:
        problems.append("signal_weights boş")
    elif any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()):
        problems.append("signal_weights içinde negatif veya sayı olmayan değer var")

    risk = data.get("risk", {})
    for key in ("initial_capital", "commission_pct", "slippage_pct", "stop_loss_pct", "take_profit_pct"):
        value = risk.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            problems.append(f"risk.{key} negatif veya sayı değil")

    if problems:
        return _result(
            "config.yaml", STATUS_ERROR,
            f"{len(problems)} tutarsızlık: " + "; ".join(problems[:6]),
            "Ayarlar sayfasından veya config.yaml üzerinden düzeltin.",
        )
    return _result("config.yaml", STATUS_OK, "Sözdizimi ve zorunlu alanlar geçerli.")


def check_secrets() -> dict[str, str]:
    if not SECRETS_PATH.exists():
        return _result(
            "secrets.toml", STATUS_WARN, "Dosya yok; harici API anahtarları kullanılamıyor.",
            "Denetim sayfasındaki API rehberini kullanarak oluşturun.",
        )
    try:
        data = tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        return _result(
            "secrets.toml", STATUS_ERROR, f"TOML hatası: {str(exc)[:120]}",
            "Denetim sayfasındaki anahtar düzenleyici ile yeniden kaydedin.",
        )
    # Tüm harici servisler opsiyoneldir: eksik anahtar hata veya uyarı değildir.
    configured = [
        name for name in ("finnhub", "gemini", "alpaca_paper", "twilio", "inngest", "alerts")
        if isinstance(data.get(name), dict) and any(data[name].values())
    ]
    if not configured:
        return _result(
            "secrets.toml", STATUS_OK,
            "Opsiyonel servis anahtarı yok; uygulama anahtarsız çalışır.",
            "Bildirim veya AI yorumu isterseniz Denetim > API rehberini kullanın.",
        )
    return _result(
        "secrets.toml", STATUS_OK,
        f"Yapılandırılan opsiyonel servisler: {', '.join(configured)}. "
        "Eksik servisler opsiyoneldir, hata değildir.",
    )


def _validate_json_file(path: Path, schema: dict[str, Any], label: str) -> dict[str, str]:
    if not path.exists():
        return _result(label, STATUS_OK, "Henüz oluşmadı (varsayılan kullanılıyor).")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return _result(label, STATUS_ERROR, f"JSON hatası: {str(exc)[:120]}", "Dosyayı yeniden kaydedin.")
    errors = sorted(
        Draft202012Validator(schema).iter_errors(data),
        key=lambda e: tuple(str(p) for p in e.path),
    )
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.absolute_path) or "kök"
        return _result(
            label, STATUS_ERROR,
            f"{len(errors)} şema hatası; ilki: {loc} → {first.message[:100]}",
            "Ayarlar sayfasından varsayılana dönüp yeniden kaydedin.",
        )
    return _result(label, STATUS_OK, "JSON ve şema geçerli.")


def check_user_files(username: str) -> list[dict[str, str]]:
    rows = [
        _validate_json_file(auth.settings_path(username), SETTINGS_SCHEMA, "Kullanıcı ayarları"),
        _validate_json_file(auth.portfolio_path(username), PORTFOLIO_SCHEMA, "Kurgusal portföy"),
    ]
    history = auth.history_path(username)
    if history.exists():
        bad = 0
        try:
            for line in history.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    json.loads(line)
        except ValueError:
            bad = 1
        rows.append(
            _result(
                "Karar geçmişi", STATUS_ERROR if bad else STATUS_OK,
                "Bozuk JSON satırı var." if bad else "Tüm satırlar geçerli JSON.",
                "Bozuk satırı silin veya geçmişi sıfırlayın." if bad else "",
            )
        )
    else:
        rows.append(_result("Karar geçmişi", STATUS_OK, "Henüz kayıt yok."))
    return rows


def check_results() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    json_path = RESULTS_DIR / "signals.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            rows.append(
                _result(
                    "results/signals.json", STATUS_OK if isinstance(data, list) else STATUS_WARN,
                    f"{len(data)} kayıt." if isinstance(data, list) else "Beklenen liste değil.",
                )
            )
        except ValueError as exc:
            rows.append(_result("results/signals.json", STATUS_ERROR, f"JSON hatası: {str(exc)[:100]}"))
    csv_path = RESULTS_DIR / "signals.csv"
    if csv_path.exists():
        try:
            with csv_path.open(encoding="utf-8", newline="") as f:
                count = sum(1 for _ in csv.reader(f))
            rows.append(_result("results/signals.csv", STATUS_OK, f"{count} satır okundu."))
        except (OSError, csv.Error) as exc:
            rows.append(_result("results/signals.csv", STATUS_ERROR, f"CSV hatası: {str(exc)[:100]}"))
    if not rows:
        rows.append(_result("Sonuç dosyaları", STATUS_OK, "Henüz oluşmadı."))
    return rows


def run_all(username: str) -> list[dict[str, str]]:
    rows = [check_yaml(), check_secrets()]
    rows.extend(check_user_files(username))
    rows.extend(check_results())
    return rows


def summary(rows: list[dict[str, str]]) -> dict[str, int]:
    return {
        STATUS_OK: sum(1 for r in rows if r["status"] == STATUS_OK),
        STATUS_WARN: sum(1 for r in rows if r["status"] == STATUS_WARN),
        STATUS_ERROR: sum(1 for r in rows if r["status"] == STATUS_ERROR),
    }
