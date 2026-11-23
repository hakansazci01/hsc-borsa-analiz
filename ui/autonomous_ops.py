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


def weekly_report() -> dict[str, Any]:
    """Pazartesi 09:00 — haftalık işlem raporu (ntfy)."""
    import csv
    from datetime import timedelta

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
    pnls = [float(r.get("net_kar_zarar", 0) or 0) for r in rows]
    wins = sum(1 for x in pnls if x > 0)
    win_rate = round(wins / len(pnls) * 100, 1) if pnls else 0.0
    total = round(sum(pnls), 2)
    fees = round(sum(float(r.get("komisyon", 0) or 0) for r in rows), 4)
    best = round(max(pnls), 2) if pnls else 0.0
    worst = round(min(pnls), 2) if pnls else 0.0
    report = {"trades": len(rows), "win_rate": win_rate, "net_pnl": total,
              "best": best, "worst": worst, "fees": fees}
    msg = (
        f"HAFTALIK RAPOR\n"
        f"Bu hafta işlem: {len(rows)}\n"
        f"Win rate: %{win_rate}\n"
        f"Toplam K/Z: {total:+.2f} TL\n"
        f"En iyi işlem: {best:+.2f} TL\n"
        f"En kötü işlem: {worst:+.2f} TL\n"
        f"Toplam komisyon: {fees:.4f} TL"
    )
    _send("HSC HAFTALIK RAPOR", msg)
    _log("haftalık rapor gönderildi")
    return report


def api_resilience() -> dict[str, Any]:
    """Binance TR API bakım koruması: 5 dk arayla 3 deneme, sonra bildir."""
    bal = None
    failures = 0
    for attempt in range(3):
        try:
            bal = tr_scalper.available_try()
            if bal and bal > 0:
                return {"ok": True, "attempts": attempt + 1, "balance": bal}
            raise ValueError("bakiye okunamadı")
        except Exception as exc:
            failures += 1
            _log(f"API deneme {attempt+1}/3 başarısız: {type(exc).__name__}")
            if failures < 3:
                time.sleep(300)  # 5 dakika bekle
    _send("HSC BİNANCE TR BAKIMDA",
          "BINANCE TR API 3 denemede cevap vermedi — bot bekliyor, "
          "yeni alım yok. Lütfen kontrol et.")
    return {"ok": False, "attempts": 3, "balance": None}


def brake_notification(reason: str) -> bool:
    return _send("HSC FREN DEVREYE GİRDİ", "FREN DEVREYE GİRDİ\nSebep: " + reason)


# --------------------------------------------------------- günlük özet
DAILY_REPORT = ROOT / "users" / "daily_report.json"


def daily_report_data() -> dict[str, Any]:
    """23:00 net rakam — vaat değil, gerçek kayıtlar."""
    import csv
    from datetime import datetime
    from ui import motor_ledger, risk_brakes, trade_stats, tp_proof

    today = time.strftime("%Y-%m-%d")
    rows: list[dict[str, Any]] = []
    p = ROOT / "trades.csv"
    if p.exists():
        with p.open(encoding="utf-8-sig", newline="") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if str(r.get("tarih", "")).startswith(today)]
    pnls = [float(r.get("net_kar_zarar", 0) or 0) for r in rows]
    wins = sum(1 for x in pnls if x > 0)
    losses = sum(1 for x in pnls if x < 0)
    st = tr_scalper._load()
    pos_list = st.get("positions") or []
    pos = st.get("position") or (pos_list[0] if pos_list else None)
    pos_txt = ("Yok" if not pos else
               f"{pos.get('symbol')} · {pos.get('qty')} adet @ {float(pos.get('avg_entry', 0)):.8f} "
               f"· ₺{float(pos.get('cost', 0)):.2f}")
    br = risk_brakes.status()
    stt = trade_stats.stats()
    return {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"), "day": today,
        "trades": len(pnls), "wins": wins, "losses": losses,
        "win_rate": round(wins / len(pnls) * 100, 1) if pnls else 0.0,
        "today_net": round(sum(pnls), 2),
        "week_net": stt["week_net"],
        "balance": br["balance"], "open_position": pos_txt,
        "tp_proof": tp_proof.count(),
        "motor_ledger": motor_ledger.summary_text(),
        "bot": "AÇIK" if not tr_scalper.STOP_FILE.exists() else "KAPALI (STOP)",
    }


def daily_summary(notify: bool = True) -> str:
    d = daily_report_data()
    msg = (
        f"GÜNLÜK ÖZET / GÜNLÜK RAPOR — {d['day']}\n"
        f"Bugün işlem: {d['trades']} (kârlı {d['wins']} / zararlı {d['losses']})\n"
        f"Win rate: %{d['win_rate']}\n"
        f"Bugün net K/Z: {d['today_net']:+.2f} TL\n"
        f"Son 7 gün net: {d['week_net']:+.2f} TL\n"
        f"Güncel kasa / Bakiye: ₺{d['balance']:,.2f}\n"
        f"Açık pozisyon: {d['open_position']}\n"
        f"Gerçek TP kanıtı: {d['tp_proof']}\n"
        f"Motor defteri: {d['motor_ledger']}\n"
        f"Bot: {d['bot']}"
    )
    try:
        DAILY_REPORT.parent.mkdir(parents=True, exist_ok=True)
        DAILY_REPORT.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    _log(msg.replace("\n", " | "))
    if notify:
        _send("HSC GÜNLÜK RAPOR", msg)
    return msg


# --------------------------------------------------------- yedekleme
# Yedekleme TEK yerde: ui.disaster_recovery.backup()
# (günlük 00:00 ve işlem sonrası aynı fonksiyonu çağırır)


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
def process_state(pattern: str) -> tuple[bool, int | None, str]:
    """GERÇEK süreç listesinden (psutil) kontrol — dosya kilidine güvenmez."""
    import psutil

    import sys as _sys

    me = __import__("os").getpid()
    for p in psutil.process_iter(["pid", "cmdline", "create_time", "exe"]):
        cmd = " ".join(p.info.get("cmdline") or [])
        pexe = (p.info.get("exe") or "").lower()
        # .venv YA DA global python — ikisini de gör (kaçan süreç kalmasın)
        args = p.info.get("cmdline") or []
        # Sadece gerçek `-m <modul>` süreci say — sorgu/-c komutlarındaki
        # modül metni sahte "canlı" sonucu vermesin.
        if ("-m" not in args or args[args.index("-m") + 1] not in
                (pattern, pattern.split(".")[-1])):
            continue
        # SADECE proje .venv python'unu say — global Python kopyaları
        # .venv'leri göremeyip sürekli yeni süreç doğuruyordu.
        _venv = ".venv" in pexe.replace("/", "\\").lower()
        if p.info["pid"] != me and pattern in cmd and "python" in pexe and _venv:
            module = args[args.index("-m") + 1]
            if True:
                start = datetime.fromtimestamp(p.info["create_time"]).strftime("%H:%M:%S")
                return True, p.info["pid"], start
    return False, None, "—"


def _start_module(module: str) -> int | None:
    """Bir modülü detached süreç olarak başlatır, PID döndürür."""
    import subprocess
    import sys

    exe = str(ROOT / ".venv" / "Scripts" / "python.exe")
    if not Path(exe).exists():
        raise RuntimeError("proje .venv python'u yok — global python ile kalıcı süreç başlatılamaz")
    # Global python'dan çağrılsa bile ÇALIŞAN executable'ı .venv'e çevir.
    # (Kilit dosyasını global süreç tutarsa zincirleme kopyalar doğuyordu.)
    sys.executable = exe
    proc = subprocess.Popen(
        [exe, "-m", module], cwd=str(ROOT),
        creationflags=0x00000008 | 0x00000200,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return proc.pid


def watchdog_once() -> dict[str, Any]:
    """Tek tur: MOTOR + SCHEDULER'ı gerçek süreç listesinden kontrol et,
    durmuş olanları 60 sn içinde yeniden başlat."""
    motor = process_state("ui.tr_runner")
    sched = process_state("ui.autonomous_scheduler")
    watch = process_state("ui.watchdog_runner")
    # KRİTİK: process_state kendi PID'ini hariç tutar. Bu fonksiyon zaten
    # watchdog sürecinin içinde çalışıyorsa kendisi "yok" sanılır ve her 60 sn
    # yeni bir watchdog doğar (sonsuz çoğalma). Kendi PID'imizi say.
    try:
        _self_cmd = " ".join(__import__("psutil").Process(__import__("os").getpid()).cmdline() or [])
        if "ui.watchdog_runner" in _self_cmd:
            watch = (True, __import__("os").getpid(),
                     time.strftime("%H:%M:%S"))
    except Exception:
        pass
    try:                       # WS sessizse 60 sn içinde yeniden bağlan
        from ui import ws_feed
        ws_feed.health_check()
    except Exception:
        pass
    actions: list[str] = []
    # Watchdog'u BURADA BAŞLATMA — bu fonksiyon zaten watchdog'un içinden
    # çağrılıyor. Kendini başlatmaya çalışınca zincirleme kopyalar doğuyordu.
    # Watchdog'u yalnızca launch_all.py başlatır (bkz. _start_module çağrısı).
    if not motor[0]:
        pid = _start_module("ui.tr_runner")
        actions.append(f"MOTOR yeniden başlatıldı (PID {pid})")
    if not sched[0]:
        pid = _start_module("ui.autonomous_scheduler")
        actions.append(f"SCHEDULER yeniden başlatıldı (PID {pid})")
    if actions:
        msg = "WATCHDOG AKSİYON: " + "; ".join(actions)
        _log(msg)
        _send("HSC WATCHDOG", msg)
    else:
        _log(f"watchdog OK — motor PID {motor[1]}, scheduler PID {sched[1]}")
    return {
        "motor_alive": motor[0], "motor_pid": motor[1], "motor_start": motor[2],
        "sched_alive": sched[0], "sched_pid": sched[1], "sched_start": sched[2],
        "watch_alive": watch[0], "watch_pid": watch[1],
        "actions": actions,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def watchdog(interval: int = 60, claim_fn=None) -> None:
    """60 saniyede bir motoru ve scheduler'ı gerçekten başlatır/izler.

    claim_fn verilirse HER TURDA tek-instance kilidini doğrular; kilidi başkası
    aldıysa bu örnek hemen çıkar (çift watchdog birbirini başlatmasın).
    """
    _log(f"WATCHDOG BAŞLADI — {interval} sn ctrl, MOTOR + SCHEDULER")
    while True:
        if claim_fn is not None and not claim_fn():
            _log("BAŞKA WATCHDOG VAR — tek-instance kilidi bu örneği durdurdu")
            return
        try:
            watchdog_once()
        except Exception as exc:
            _log(f"watchdog hata: {type(exc).__name__}: {str(exc)[:100]}")
        time.sleep(interval)


if __name__ == "__main__":
    watchdog()
