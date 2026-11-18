"""
Aktif bildirimler: Telegram, ntfy.sh ve e-posta.

Öncelik: `.streamlit/secrets.toml` -> kullanıcı ayarları.
Gizli değerler arayüzde gösterilmez.
"""

from __future__ import annotations

import json
import secrets
import smtplib
import string
from email.message import EmailMessage

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib
from pathlib import Path
from typing import Any

import requests
import streamlit as st

from ui import secrets_access


SECRETS_PATH = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"


def _alerts(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or (st.session_state.get("settings", {}) if st.session_state else {})
    return settings.get("alerts", {}) or {}


def credentials(settings: dict[str, Any] | None = None) -> tuple[str, str]:
    alerts = _alerts(settings)
    token = secrets_access.get("alerts", "telegram_bot_token", "") or alerts.get("telegram_bot_token", "")
    chat = secrets_access.get("alerts", "telegram_chat_id", "") or alerts.get("telegram_chat_id", "")
    return token, chat


def telegram_enabled(settings: dict[str, Any] | None = None) -> bool:
    return bool(_alerts(settings).get("telegram_enabled", False))


def ntfy_enabled(settings: dict[str, Any] | None = None) -> bool:
    return bool(_alerts(settings).get("ntfy_enabled", False))


def email_enabled(settings: dict[str, Any] | None = None) -> bool:
    return bool(_alerts(settings).get("email_enabled", False))


def send_telegram(text: str, settings: dict[str, Any] | None = None) -> tuple[bool, str]:
    token, chat = credentials(settings)
    if not token or not chat or token.startswith("BOT_TOKEN"):
        return False, "Telegram token veya chat id tanımlı değil."
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        if resp.status_code == 200:
            return True, "Telegram bildirimi gönderildi."
        return False, f"Telegram HTTP {resp.status_code}: {resp.text[:120]}"
    except Exception as exc:
        return False, f"Bağlantı hatası ({type(exc).__name__})."


def detect_chat_id(token: str) -> tuple[str | None, str]:
    """Botunuza gönderilen son mesajdan chat id'yi otomatik bulur."""
    token = (token or "").strip()
    if not token or token.startswith("BOT_TOKEN"):
        return None, "Önce BotFather'dan aldığınız token'ı girin."
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"limit": 10, "timeout": 3},
            timeout=10,
        )
        if resp.status_code != 200:
            return None, f"Telegram HTTP {resp.status_code}: {resp.text[:120]}"
        results = resp.json().get("result", [])
        for item in reversed(results):
            chat = (item.get("message") or item.get("callback_query") or {}).get("chat", {})
            if chat.get("id"):
                return str(chat["id"]), "Chat ID bulundu."
        return None, "Henüz botunuza mesaj yok. Telegram'da botunuza /start yazın, sonra tekrar deneyin."
    except Exception as exc:
        return None, f"Bağlantı hatası ({type(exc).__name__})."


def new_topic() -> str:
    """ntfy için tahmin edilemez, benzersiz bir konu adı üretir."""
    alphabet = string.ascii_lowercase + string.digits
    return "borsa-" + "".join(secrets.choice(alphabet) for _ in range(12))


def send_ntfy(text: str, topic: str, title: str = "HKC Borsa Analiz") -> tuple[bool, str]:
    topic = (topic or "").strip()
    if not topic:
        return False, "ntfy konusu tanımlı değil."
    try:
        resp = requests.post(
            f"https://ntfy.sh/{topic}",
            data=text.encode("utf-8"),
            headers={"Title": title, "Priority": "high", "Tag": "chart_with_upwards_trend"},
            timeout=10,
        )
        if resp.status_code == 200:
            return True, "ntfy bildirimi gönderildi."
        return False, f"ntfy HTTP {resp.status_code}: {resp.text[:120]}"
    except Exception as exc:
        return False, f"Bağlantı hatası ({type(exc).__name__})."


def send_email(text: str, settings: dict[str, Any] | None = None) -> tuple[bool, str]:
    alerts = _alerts(settings)
    host = secrets_access.get("smtp", "host", "") or alerts.get("smtp_host", "smtp.gmail.com")
    port = int(secrets_access.get("smtp", "port", "") or alerts.get("smtp_port", 587))
    user = secrets_access.get("smtp", "user", "") or alerts.get("smtp_user", "")
    password = secrets_access.get("smtp", "password", "") or alerts.get("smtp_password", "")
    to = secrets_access.get("smtp", "to", "") or alerts.get("smtp_to", user)
    if not user or not password or not to:
        return False, "E-posta ayarları eksik (kullanıcı, uygulama şifresi veya alıcı)."
    try:
        msg = EmailMessage()
        msg["Subject"] = "HKC Borsa Analiz bildirimi"
        msg["From"] = user
        msg["To"] = to
        msg.set_content(text)
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True, "E-posta gönderildi."
    except Exception as exc:
        return False, f"E-posta hatası ({type(exc).__name__})."


def trade_alert(
    reason: str,
    results: list[dict[str, Any]],
    settings: dict[str, Any] | None = None,
    username: str | None = None,
) -> str:
    """AL / BEKLE / SAT için net zamanlama + fiyat seviyeleri + 15 dk K/Z içeren bildirim metni."""
    from ui.market_session import now, status as session_status

    session = session_status()
    timing = (
        f"İŞLEM ZAMANI: ŞİMDİ ({now().strftime('%H:%M')}, seans açık)"
        if session["in_session"]
        else f"İŞLEM ZAMANI: BEKLE — {session['detail']} (seans içinde teyit et)"
    )
    lines = [f"BIST AL/SAT SİNYALİ — {reason}", timing, ""]

    actionable = [
        r for r in results
        if "info" in r and r["info"]["signal"] in ("STRONG_BUY", "BUY", "STRONG_SELL", "SELL")
    ]
    if actionable:
        for r in actionable[:8]:
            info = r["info"]
            price = float(info.get("last_close", 0))
            stop = round(price * 0.95, 2)
            target = round(price * 1.10, 2)
            lines.append(
                f"• {r['symbol']}: {info['signal']} | puan {info['score']:+.2f} | "
                f"giriş ~{price:,.2f} | stop {stop:,.2f} | hedef {target:,.2f}"
            )
    else:
        lines.append("Yönlü sinyal yok: BEKLE. Yeni onay gelene kadar işlem yapmayın.")

    if username:
        try:
            from ui.pnl_tracker import today_table

            table = today_table(username)
            if not table.empty:
                last = table.iloc[-1]
                lines += ["", "15-DK NET K/Z TABLOSU (son 4 dilim)"]
                for _, row in table.tail(4).iterrows():
                    lines.append(
                        f"{row['Saat']}: net {float(row['Net K/Z']):+,.2f} ₺ "
                        f"(gerç. {float(row['Gerçekleşen']):+,.2f} / açık {float(row['Açık K/Z']):+,.2f})"
                    )
                lines.append(f"Sermaye: {float(last['Sermaye']):,.2f} ₺")
        except Exception:
            pass

    lines += ["", "Yatırım tavsiyesi değildir. Seviyeleri KAP ve güncel fiyattan teyit edin."]
    return "\n".join(lines)


def send_notification(text: str, settings: dict[str, Any] | None = None) -> list[tuple[str, bool, str]]:
    """Etkin olan tüm kanallara gönderir; kanal bazlı sonuç döndürür."""
    results: list[tuple[str, bool, str]] = []
    if telegram_enabled(settings):
        results.append(("Telegram", *send_telegram(text, settings)))
    if ntfy_enabled(settings):
        topic = secrets_access.get("alerts", "ntfy_topic", "") or _alerts(settings).get("ntfy_topic", "")
        results.append(("ntfy", *send_ntfy(text, topic)))
    if email_enabled(settings):
        results.append(("E-posta", *send_email(text, settings)))
    if not results:
        results.append(("Hiçbiri", False, "Aktif bildirim kanalı yok."))
    return results


def _read_secrets() -> dict[str, Any]:
    if not SECRETS_PATH.exists():
        return {}
    try:
        return tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        return {}


def save_secrets_section(section: str, values: dict[str, str]) -> None:
    data = _read_secrets()
    current = dict(data.get(section, {}) or {})
    current.update({k: v for k, v in values.items() if v})
    data[section] = current
    lines = ["# YEREL GİZLİ ANAHTARLAR - COMMIT ETMEYİN", ""]
    for name, section_values in data.items():
        if not isinstance(section_values, dict):
            continue
        lines.append(f"[{name}]")
        for key, value in section_values.items():
            lines.append(f"{key} = {json.dumps(str(value), ensure_ascii=False)}")
        lines.append("")
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text("\n".join(lines), encoding="utf-8")


def save_credentials(token: str, chat_id: str) -> None:
    save_secrets_section("alerts", {
        "telegram_bot_token": token,
        "telegram_chat_id": chat_id,
    })
