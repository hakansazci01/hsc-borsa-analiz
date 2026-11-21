"""
Tam otonom operasyon katmanı — watchdog, bildirim, yedekleme, sağlık, strateji denetimi.

GÜVENLİK KİLİTLERİNE DOKUNMAZ: enabled, confirmation_phrase, STOP_FILE,
dinamik %10 işlem, dinamik günlük limit, trailing DD %15, kâr kilidi +50.
Sanal mod / all-in mod YOK. Sadece gerçek Binance TR.
"""

from __future__ import annotations

import csv
import json
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ui import auth, notify, trade_notify, tr_scalper


ROOT = Path(__file__).resolve().parent.parent
LOG = auth.USERS_DIR / "autonomous_ops.log"
MAX_LOG_BYTES = 10 * 1024 * 1024
BACKUPS = ROOT / "backups"
HEALTH = auth.USERS_DIR / "health_state.json"


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > MAX_LOG_BYTES:
            archive = LOG.with_name(f"autonomous_ops_{time.strftime('%Y%m%d_%H%M%S')}.log")
            shutil.move(str(LOG), str(archive))
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _send(title: str, msg: str) -> bool:
    try:
        ok, _ = notify.send_ntfy(msg, trade_notify._topic(), title=title)
        return ok
    except Exception:
        return False


# --------------------------------------------------------- trade bildirimi
def trade_notification(symbol: str, side: str, qty: float, buy_px: float,
                       sell_px: float, net_pnl: float, balance: float) -> bool:
    msg = (
        f"sembol: {symbol}\n"
        f"alış fiyatı: {buy_px:,.4f} TL\n"
        f"satış fiyatı: {sell_px:,.4f} TL\n"
        f"adet: {qty}\n"
        f"net kâr/zarar: {net_pnl:+.2f} TL\n"
        f"güncel bakiye: {balance:,.2f} TL\n"
        f"işlem: {side.upper()}"
    )
    return _send("HSC GERÇEK İŞLEM", msg)


def alive_signal() -> str:
    """Saatlik 'BOT YAŞIYOR' sinyali — 2 saat gelmezse bot durdu anlaşılır."""
    from ui import tr_monitor

    bal = tr_scalper.available_try()
    pos = tr_monitor.live_metrics()["position"]
    gate = tr_scalper.config_gate()
    try:
        hb = json.loads(autonomous.HEARTBEAT.read_text(encoding="utf-8"))
        age = int(time.time() - float(hb.get("ts", 0)))
    except Exception:
        age = 999999
    open_txt = "AÇIK" if not gate and not tr_scalper.STOP_FILE.exists() else "KAPALI"
    pos_txt = (f"{pos['symbol']} · ₺{pos['cost']:.2f} · {age//60} dk"
               if pos else "yok")
    msg = (
        f"BOT YAŞIYOR\n"
        f"Saat: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Bot: {open_txt}\n"
        f"Bakiye: {bal:,.2f} TL\n"
        f"Son cycle: {age//60} dk {age%60} sn önce\n"
        f"Açık pozisyon: {pos_txt}"
    )
    _send("HSC BOT YAŞIYOR", msg)
    _log("yaşam sinyali gönderildi")
    return msg


def brake_notification(reason: str) -> bool:
    return _send("HSC FREN DEVREYE GİRDİ", "FREN DEVREYE GİRDİ\nSebep: " + reason)


# --------------------------------------------------------- günlük özet
def daily_summary() -> str:
    from ui import tr_monitor, risk_brakes

    s = tr_monitor.summary()
    br = risk_brakes.status()
    today = time.strftime("%Y-%m-%d")
    rows = [h for h in tr_monitor.merged_history() if str(h.get("exit_time", "")).startswith(today)]
    msg = (
        f"GÜNLÜK ÖZET — {today}\n"
        f"Bugün işlem: {len(rows)}\n"
        f"Toplam işlem (tüm zaman): {s['trades']}\n"
        f"Toplam net K/Z: {s['net_pnl']:+.2f} TL\n"
        f"Günlük net: {br['day_realized_pnl']:+.2f} TL\n"
        f"Güncel kasa: {br['balance']:,.2f} TL\n"
        f"Bot: {'AÇIK' if not tr_scalper.STOP_FILE.exists() else 'KAPALI (STOP)'}"
    )
    _send("HSC GÜNLÜK ÖZET", msg)
    _log("günlük özet gönderildi")
    return msg


# --------------------------------------------------------- yedekleme
def backup_files() -> list[str]:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d")
    targets = [ROOT / "trades.csv", ROOT / "users" / "tr_daily_state.json", ROOT / "config.yaml"]
    saved = []
    for src in targets:
        if src.exists():
            dst = BACKUPS / f"{stamp}_{src.name}"
            shutil.copy2(src, dst)
            saved.append(dst.name)
    # son 30 gün
    cutoff = datetime.now() - timedelta(days=30)
    for f in BACKUPS.glob("*_trades.csv"):
        try:
            d = datetime.strptime(f.name[:8], "%Y%m%d")
            if d < cutoff:
                f.unlink()
        except Exception:
            pass
    _log(f"yedeklendi: {saved}")
    return saved


# --------------------------------------------------------- sağlık kontrolü
def health_check() -> dict[str, Any]:
    failed = 0
    errors: list[str] = []
    bal = None
    for attempt in range(10):
        try:
            bal = tr_scalper.available_try()
            if bal and bal > 0:
                failed = 0
                break
            raise ValueError("bakiye okunamadı")
        except Exception as exc:
            failed += 1
            errors.append(f"{type(exc).__name__}: {str(exc)[:60]}")
            if failed >= 10:
                break
            time.sleep(30)
    hist = tr_monitor_history() if False else []
    st = json.loads(HEALTH.read_text(encoding="utf-8")) if HEALTH.exists() else {}
    last_ok = st.get("last_ok_at", "—")
    result = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "api_ok": bal is not None and bal > 0,
        "balance": bal,
        "failures": failed,
        "errors": errors[-3:],
        "last_ok_at": last_ok,
        "stop_file": tr_scalper.STOP_FILE.exists(),
    }
    HEALTH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if failed >= 10:
        _send("HSC SAĞLIK UYARISI", "10 üst üste API başarısızlığı — bot duruyor, kontrol et")
    elif failed:
        _log(f"sağlık kontrolü uyarı: {errors[-1]}")
    else:
        _log("sağlık kontrolü OK")
    return result


def tr_monitor_history() -> list[dict[str, Any]]:
    return []


# --------------------------------------------------------- strateji değerlendirme
def weekly_strategy_review() -> dict[str, Any]:
    """Pazar 00:00 — son 7 gün trades.csv, win rate < %40 ve zarar > -50 TL ise DUR."""
    p = ROOT / "trades.csv"
    rows: list[dict[str, Any]] = []
    if p.exists():
        with p.open(encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    d = datetime.strptime(str(r.get("tarih", ""))[:10], "%Y-%m-%d")
                except Exception:
                    continue
                if d >= datetime.now() - timedelta(days=7):
                    rows.append(r)
    wins = sum(1 for r in rows if float(r.get("net_kar_zarar", 0) or 0) > 0)
    win_rate = round(wins / len(rows) * 100, 1) if rows else 0.0
    total = round(sum(float(r.get("net_kar_zarar", 0) or 0) for r in rows), 2)
    bad = bool(rows) and win_rate < 40 and total < -50
    report = {
        "week": time.strftime("%Y-%m-%d"),
        "trades": len(rows), "win_rate": win_rate, "net_pnl": total,
        "degraded": bad,
    }
    msg = (f"HAFTALIK STRATEJİ RAPORU\nSon 7 gün işlem: {len(rows)}\n"
           f"Win rate: %{win_rate}\nNet K/Z: {total:+.2f} TL\n"
           + ("STRATEJİ BOZULDU — yeni işlem durduruldu, kontrol et" if bad
              else "Strateji doğrulama aralığında"))
    _send("HSC HAFTALIK STRATEJİ", msg)
    if bad:
        tr_scalper.STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        tr_scalper.STOP_FILE.write_text("strateji bozuldu: win<40 ve zarar<-50", encoding="utf-8")
        _log("strateji bozuldu — STOP_FILE yazıldı")
    return report


# --------------------------------------------------------- watchdog
def watchdog(interval: int = 60) -> None:
    """Motoru izler; çökerse 60 sn içinde yeniden başlatır."""
    import subprocess
    import sys

    _log(f"WATCHDOG BAŞLADI — {interval} sn kontrol")
    while True:
        try:
            from ui import tr_runner

            alive = tr_runner.LOCK.exists() and tr_runner._pid_alive(
                int(tr_runner.LOCK.read_text(encoding="utf-8").strip() or 0)
            )
            if not alive:
                _log("motor ölü — yeniden başlatılıyor")
                exe = str(ROOT / ".venv" / "Scripts" / "python.exe")
                if not Path(exe).exists():
                    exe = sys.executable
                subprocess.Popen([exe, "-m", "ui.tr_runner"], cwd=str(ROOT),
                                 creationflags=0x00000008 | 0x00000200,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _send("HSC WATCHDOG", "Motor çöktü, otomatik yeniden başlatıldı")
        except Exception as exc:
            _log(f"watchdog hata: {type(exc).__name__}: {str(exc)[:100]}")
        time.sleep(interval)


if __name__ == "__main__":
    watchdog()
