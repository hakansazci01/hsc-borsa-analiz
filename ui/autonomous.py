"""
Otonom Yönetici — sürekli analiz, öngörü self-test, karar ve motor kontrolü.

Döngü:
1. Gerçek Binance verisiyle quant_lab.research() çalıştır (iç/dış örneklem).
2. Piyasa rejimini oku; bir öngörü kaydet (yukarı / aşağı-yatay).
3. Önceki öngörüyü gerçekleşen BTC fiyatıyla karşılaştır → isabet oranı.
4. Karar: yalnızca DOĞRULANMIŞ kârlı edge + yukarı rejim + makul isabet varsa AÇ.
   Aksi halde KAPALI kal (sermaye koruma).
5. Motoru aç/kapat; tüm kararları denetim kaydı olarak sakla.

Bu sistem "tahmin edip yatırım yapmaz"; tahminlerini ölçer ve kanıt olmadan
parayı riske atmaz. Hiçbir sayı uydurulmaz; veri yoksa karar KAPALI'dır.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ui import auth, quant_lab, tr_runner, tr_scalper

STATE = auth.USERS_DIR / "tr_autonomous_state.json"
LOCK = auth.USERS_DIR / "TR_AUTONOMOUS_LOCK"
LOG = auth.USERS_DIR / "tr_autonomous.log"
HEARTBEAT = auth.USERS_DIR / "tr_autonomous_heartbeat.json"
INTERVAL_MIN = 60
MIN_ACCURACY = 40.0
MIN_SAMPLES = 4


def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(data: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def heartbeat(extra: dict[str, Any] | None = None) -> None:
    """Her turda güncellenir: 'şu an gerçekten çalışıyor' kanıtı."""
    state = _load()
    rec = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ts": time.time(),
        "pid": os.getpid(),
        "last_decision": state.get("last_decision", {}).get("decision"),
        "last_analysis": state.get("last_decision", {}).get("at"),
        "accuracy": accuracy(state),
        "robot_running": _runner_alive(),
    }
    if extra:
        rec.update(extra)
    try:
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def btc_price() -> float | None:
    frame = quant_lab.fetch("BTCUSDT", "4h", 10)
    return float(frame["Close"].iloc[-1]) if frame is not None and not frame.empty else None


def _score(prev: dict[str, Any], now_px: float | None) -> dict[str, Any] | None:
    """Önceki öngörüyü gerçek fiyatla karşılaştır."""
    if not prev or now_px is None:
        return None
    old_px = float(prev.get("btc_price", 0) or 0)
    if old_px <= 0:
        return None
    ret = (now_px / old_px - 1) * 100
    expected = prev.get("prediction")
    if expected == "up":
        correct = ret > 0.5
    elif expected == "down_flat":
        correct = ret < 0.5
    else:
        return None
    return {"at": prev.get("at"), "prediction": expected,
            "realized_pct": round(ret, 2), "correct": bool(correct)}


def accuracy(state: dict[str, Any]) -> dict[str, Any]:
    tests = state.get("prediction_tests", [])[-20:]
    if not tests:
        return {"rate": None, "n": 0}
    ok = sum(1 for t in tests if t.get("correct"))
    return {"rate": round(ok / len(tests) * 100, 1), "n": len(tests)}


def decide() -> dict[str, Any]:
    """Tek analiz turu: ölç, öngörüyü test et, karar ver, kaydet."""
    state = _load()
    research = quant_lab.research()
    regime = research.get("regime", {})
    bull = bool(regime.get("bull"))
    now_px = btc_price()

    last = state.get("last_prediction")
    scored = _score(last, now_px)
    tests = state.get("prediction_tests", [])
    if scored:
        tests.append(scored)
        tests = tests[-20:]

    acc = accuracy({"prediction_tests": tests})
    robust = int(research.get("robust_count", 0))
    verdict = research.get("verdict", "veri yok")

    reasons: list[str] = []
    if not research.get("ok"):
        reasons.append("gerçek veri alınamadı")
    if robust <= 0:
        reasons.append("doğrulanmış kârlı strateji yok")
    if not bull:
        reasons.append(f"ayı rejimi ({regime.get('dist_pct', '?')}%)")
    if acc["n"] >= MIN_SAMPLES and acc["rate"] is not None and acc["rate"] < MIN_ACCURACY:
        reasons.append(f"öngörü isabeti düşük (%{acc['rate']})")

    open_it = not reasons
    decision = "OPEN" if open_it else "CLOSED"

    new_pred = {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ts": time.time(),
        "prediction": "up" if bull else "down_flat",
        "btc_price": now_px,
        "regime": regime.get("name"),
        "robust": robust,
        "decision": decision,
        "reasons": reasons,
        "best_train": research.get("best_train"),
    }
    state["last_prediction"] = new_pred
    state["prediction_tests"] = tests
    state["last_decision"] = new_pred
    history = state.get("decisions", [])
    history.append(new_pred)
    state["decisions"] = history[-100:]
    state["updated_at"] = new_pred["at"]
    _save(state)

    _log(
        f"ANALIZ: rejim={regime.get('name')} robust={robust} "
        f"isabet={acc['rate'] if acc['rate'] is not None else '—'}%({acc['n']}) "
        f"KARAR={decision} neden={'; '.join(reasons) or 'edge doğrulandı'}"
    )
    return new_pred


def _runner_alive() -> bool:
    if not tr_runner.LOCK.exists():
        return False
    try:
        pid = int(tr_runner.LOCK.read_text(encoding="utf-8").strip() or 0)
    except Exception:
        return False
    return pid > 0 and tr_runner._pid_alive(pid)


def apply(decision: dict[str, Any]) -> None:
    """Kararı motora uygula (tek process, güvenli)."""
    if decision.get("decision") == "OPEN":
        tr_scalper.STOP_FILE.unlink(missing_ok=True)
        if not _runner_alive():
            root = Path(__file__).resolve().parent.parent
            exe = str(root / ".venv" / "Scripts" / "python.exe")
            if not Path(exe).exists():
                exe = sys.executable
            subprocess.Popen(
                [exe, "-m", "ui.tr_runner"], cwd=str(root),
                creationflags=0x00000008 | 0x00000200,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            _log("Motor başlatıldı (doğrulanmış edge)")
        else:
            _log("Motor zaten çalışıyor")
    else:
        was = _runner_alive()
        tr_scalper.STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        tr_scalper.STOP_FILE.write_text("autonomous: " + "; ".join(decision.get("reasons", [])), encoding="utf-8")
        _log("Motor kapalı tutuluyor" + (f" (çalışan process durduruldu)" if was else ""))


def run_once() -> dict[str, Any]:
    d = decide()
    apply(d)
    return d


def run_forever() -> None:
    # Windows named mutex — süreçler arası tek-instance garantisi (dosya kilidi
    # yerine çekirdek seviyesinde kilit; yarış durumu olmaz).
    mutex = None
    try:
        import ctypes

        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "HSCAutonomousGovernor")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            _log("Zaten çalışan otonom yönetici var (mutex) — çıkıyorum")
            return
    except Exception:
        mutex = None
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        # Bayat kilit (önceki süreç öldüyse) yeni süreci engellemesin.
        try:
            old = int(LOCK.read_text(encoding="utf-8").strip() or 0)
        except Exception:
            old = 0
        if not old or not tr_runner._pid_alive(old):
            LOCK.write_text(str(os.getpid()), encoding="utf-8")
            _log(f"Bayat kilit temizlendi (eski PID={old})")
    # Başlangıçta sahiplik doğrula: yarışlı çift başlatmada fazlası hemen çıkar.
    time.sleep(2)
    try:
        if int(LOCK.read_text(encoding="utf-8").strip() or 0) != os.getpid():
            _log("Kilit başka PID'de — çıkıyorum")
            return
    except Exception:
        pass
    _log(f"OTONOM YÖNETİCİ BAŞLADI — {INTERVAL_MIN} dk analiz, 60 sn güvenlik kontrolü")
    last_research = 0.0
    try:
        while True:
            try:
                if int(LOCK.read_text(encoding="utf-8").strip() or 0) != os.getpid():
                    _log("Kilit başka PID'de — çıkıyorum")
                    return
                heartbeat()
                now = time.time()
                if now - last_research >= INTERVAL_MIN * 60:
                    run_once()
                    last_research = now
            except Exception as exc:
                _log(f"HATA ({type(exc).__name__}): {str(exc)[:150]} — devam ediliyor")
            time.sleep(60)
    finally:
        try:
            if LOCK.exists() and int(LOCK.read_text(encoding="utf-8").strip() or 0) == os.getpid():
                LOCK.unlink()
        except Exception:
            pass
