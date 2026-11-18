"""
Şeffaf sinyal performans defteri (R çarpanı).

Arrowsticks'teki "her sonuç kayıt altında" yaklaşımını kurgusal (paper)
sinyallerimize uyarlar: kapanan her pozisyon giriş, stop, hedef, çıkış,
R çarpanı, yüzde K/Z, güven ve gerekçeyle kalıcı olarak kaydedilir.
Kazananlar ve kaybedenler **aynı yöntemle** hesaplanır; seçici sunum yapılmaz.

R çarpanı, K/Z'nin alınan riske (stop mesafesine) oranıdır:
    R = (çıkış - giriş) / (giriş - stop)        (uzun pozisyon)
Stop yoksa ayarlardaki zarar-durdurma yüzdesi risk ölçüsü olarak kullanılır
ve kayıtta `r_basis` alanıyla hangi yöntemin kullanıldığı belirtilir.

Tüm veriler kullanıcıya özel `users/<kullanici>/performance.jsonl` dosyasındadır.
Gerçek emir veya gerçek para söz konusu değildir.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ui import auth

PERFORMANCE_FILE = "performance.jsonl"


def performance_path(username: str):
    """Kullanıcının performans defteri dosya yolu."""
    return auth.user_dir(username) / PERFORMANCE_FILE


def _today() -> str:
    return datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d")


def compute_r(
    entry: float, exit_price: float, stop: float | None, stop_loss_pct: float = 5.0
) -> tuple[float, float, str]:
    """R çarpanını, risk yüzdesini ve hesaplama esasını döndürür.

    stop geçerliyse (girişin altında ve pozitif) gerçek stop mesafesi,
    değilse ayarlardaki stop_loss_pct (yüzde) risk ölçüsü olarak kullanılır.
    """
    entry = float(entry)
    exit_price = float(exit_price)
    try:
        stop_value = float(stop) if stop else 0.0
    except (TypeError, ValueError):
        stop_value = 0.0

    if stop_value > 0 and entry > stop_value:
        risk_per_unit = entry - stop_value
        basis = "stop mesafesi"
    else:
        risk_per_unit = entry * (float(stop_loss_pct) / 100.0)
        basis = f"ayar stop %{float(stop_loss_pct):.1f}"

    risk_per_unit = max(risk_per_unit, 1e-9)
    r = (exit_price - entry) / risk_per_unit
    risk_pct = risk_per_unit / entry * 100.0
    return round(r, 3), round(risk_pct, 3), basis


def record_close(
    username: str,
    position: dict[str, Any],
    exit_price: float,
    reason: str,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Kapanan kurgusal pozisyonu performans defterine ekler ve kaydı döndürür."""
    risk_cfg = (settings or {}).get("risk", {}) or {}
    stop_pct = float(risk_cfg.get("stop_loss_pct", 0.05) or 0.05) * 100.0

    entry = float(position["entry_price"])
    exit_price = float(exit_price)
    qty = float(position.get("qty", 0) or 0)
    stop = position.get("stop")
    target = position.get("target")

    r, risk_pct, basis = compute_r(entry, exit_price, stop, stop_pct)
    pnl_pct = (exit_price / entry - 1) * 100 if entry else 0.0
    pnl_amount = (exit_price - entry) * qty

    record = {
        "id": position.get("id", ""),
        "time": auth._now(),
        "date": _today(),
        "symbol": str(position.get("symbol", "")).upper(),
        "direction": "AL",  # kurgusal pozisyonlar uzun (long) açılır
        "entry": round(entry, 4),
        "exit": round(exit_price, 4),
        "stop": round(float(stop), 4) if stop else None,
        "target": round(float(target), 4) if target else None,
        "qty": round(qty, 4),
        "r_multiple": r,
        "risk_pct": risk_pct,
        "r_basis": basis,
        "pnl_pct": round(pnl_pct, 2),
        "pnl_amount": round(pnl_amount, 2),
        "confidence": int(position.get("confidence", 0) or 0),
        "entry_signal": str(position.get("reason", "")),
        "exit_reason": str(reason),
        "outcome": "KÂR" if r > 0 else "ZARAR" if r < 0 else "BAŞA BAŞ",
    }

    path = performance_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_records(username: str, limit: int = 1000) -> list[dict[str, Any]]:
    """Performans kayıtlarını en eskiden en yeniye doğru döndürür."""
    path = performance_path(username)
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


def summarize(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Kapanan sinyaller için şeffaf performans özeti ve kümülatif R eğrisi."""
    if not records:
        return None

    rs = [float(r.get("r_multiple", 0) or 0) for r in records]
    n = len(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    n_win, n_loss = len(wins), len(losses)

    net_r = sum(rs)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    avg_win = gross_win / n_win if n_win else 0.0
    avg_loss = sum(losses) / n_loss if n_loss else 0.0
    win_rate = n_win / n * 100.0

    profit_factor = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    payoff = avg_win / abs(avg_loss) if avg_loss else 0.0
    expectancy = (win_rate / 100.0) * avg_win + (n_loss / n) * avg_loss

    curve: list[dict[str, Any]] = []
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for i, (r, rec) in enumerate(zip(rs, records), start=1):
        cum += r
        peak = max(peak, cum)
        dd = cum - peak
        max_dd = min(max_dd, dd)
        curve.append({
            "no": i,
            "kumulatif_r": round(cum, 3),
            "dusus": round(dd, 3),
            "zaman": rec.get("time", ""),
            "sembol": rec.get("symbol", ""),
        })

    streak = 0
    best_win_streak = 0
    best_loss_streak = 0
    for r in rs:
        if r > 0:
            streak = streak + 1 if streak > 0 else 1
            best_win_streak = max(best_win_streak, streak)
        elif r < 0:
            streak = streak - 1 if streak < 0 else -1
            best_loss_streak = max(best_loss_streak, -streak)
        else:
            streak = 0

    return {
        "total": n,
        "wins": n_win,
        "losses": n_loss,
        "breakeven": n - n_win - n_loss,
        "win_rate_pct": round(win_rate, 1),
        "net_r": round(net_r, 2),
        "avg_r": round(net_r / n, 3),
        "avg_win_r": round(avg_win, 3),
        "avg_loss_r": round(avg_loss, 3),
        "payoff": round(payoff, 3),
        "profit_factor": round(profit_factor, 3),
        "expectancy_r": round(expectancy, 3),
        "best_r": round(max(rs), 2),
        "worst_r": round(min(rs), 2),
        "max_drawdown_r": round(max_dd, 2),
        "current_streak": streak,
        "best_win_streak": best_win_streak,
        "best_loss_streak": best_loss_streak,
        "total_pnl_amount": round(sum(float(r.get("pnl_amount", 0) or 0) for r in records), 2),
        "curve": curve,
    }


def breakdown(records: list[dict[str, Any]], key: str = "symbol") -> list[dict[str, Any]]:
    """Hisse veya yön bazında performans dökümü."""
    groups: dict[str, list[float]] = {}
    for rec in records:
        name = str(rec.get(key, "—") or "—")
        groups.setdefault(name, []).append(float(rec.get("r_multiple", 0) or 0))
    rows = []
    for name, rs in groups.items():
        wins = sum(1 for r in rs if r > 0)
        rows.append({
            key: name,
            "Sinyal": len(rs),
            "Kazanma %": round(wins / len(rs) * 100, 1),
            "Net R": round(sum(rs), 2),
            "Ort. R": round(sum(rs) / len(rs), 3),
        })
    return sorted(rows, key=lambda r: r["Net R"], reverse=True)
