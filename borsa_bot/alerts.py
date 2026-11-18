"""
Bildirim katmani: konsol, JSON/CSV dosya ve istege bagli Telegram.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests


def console_alert(symbol: str, info: dict[str, Any]) -> None:
    line = (
        f"\n{'='*55}\n"
        f"  HISSE : {symbol}\n"
        f"  SINYAL: {info['signal']}  |  PUAN: {info['score']}\n"
        f"  FIYAT : {info['last_close']}\n"
        f"  RSI   : {info['rsi']}\n"
        f"  MACD  : {info['macd']} (sinyal: {info['macd_signal']})\n"
        f"{'='*55}\n"
    )
    print(line)


def save_results(results: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    alert_cfg = cfg.get("alerts", {})
    results_dir = Path("results")
    results_dir.mkdir(exist_ok=True)

    if alert_cfg.get("save_json", True):
        path = results_dir / alert_cfg.get("json_path", "signals.json").split("/")[-1]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    if alert_cfg.get("save_csv", True):
        path = results_dir / alert_cfg.get("csv_path", "signals.csv").split("/")[-1]
        import csv

        if results:
            keys = sorted({key for row in results for key in row.keys()})
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
                writer.writeheader()
                for row in results:
                    flat = {k: (v if not isinstance(v, dict) else str(v)) for k, v in row.items()}
                    writer.writerow(flat)


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    if not token or not chat_id or token == "BOT_TOKEN_BURAYA":
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as exc:
        print(f"[Telegram Hata] {exc}")
        return False


def alert(symbol: str, info: dict[str, Any], cfg: dict[str, Any]) -> None:
    alert_cfg = cfg.get("alerts", {})
    if alert_cfg.get("console", True):
        console_alert(symbol, info)

    if alert_cfg.get("telegram_enabled", False):
        token = cfg.get("telegram_token", "") if hasattr(cfg, "get") else ""
        chat_id = cfg.get("telegram_chat_id", "") if hasattr(cfg, "get") else ""
        text = (
            f"<b>{symbol}</b> | Sinyal: <b>{info['signal']}</b>\n"
            f"Puan: {info['score']} | Fiyat: {info['last_close']}\n"
            f"RSI: {info['rsi']} | MACD: {info['macd']}"
        )
        send_telegram(token, chat_id, text)