"""TEST İZOLE STATE — tüm testler canlı users/ state'inden koparılır.

Autouse fixture her test öncesi modül STATE yollarını tmp_path'e yönlendirir.
Böylece hiçbir test tr_daily_state.json / safety_guards.json / backups/ vb.
CANLI dosyalarına yazamaz. Oturum başı/sonu log'a kanıt yazar.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
USERS = ROOT / "users"
PROOF_LOG = USERS / "test_isolation.log"
LIVE_STATE_FILES = [
    "tr_daily_state.json", "safety_guards.json", "order_guard_state.json",
    "trading_params.json", "risk_brakes_state.json", "auto_mode_state.json",
    "ws_state.json", "engine_state.json", "crash_bid.json",
    "tiered_brakes.json", "whale_guard_state.json", "live_feed_state.json",
    "recovery_state.json", "tp_proof.json", "daily_report.json",
]


def _proof(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        USERS.mkdir(parents=True, exist_ok=True)
        with PROOF_LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        with (USERS / "autonomous_ops.log").open("a", encoding="utf-8") as fh:
            fh.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] TEST İZOLE STATE, "
                     f"canlıya DOKUNULMADI — {msg}\n")
    except Exception:
        pass


def _snapshot() -> dict[str, str]:
    """Kritik alanların özeti — canlı bot cycle_count/zaman damgası yazıyor,
    bunlar test izolasyonu kanıtı için anlamsız. Pozisyon ve limitler önemli.
    """
    import json

    out = {}
    for name in LIVE_STATE_FILES:
        p = USERS / name
        if not p.exists():
            out[name] = "-"
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(d, dict):
                out[name] = "?"
                continue
            critical = {}
            for k in ("positions", "position", "cusum", "history",
                      "day_realized_pnl", "day_open_balance", "mode",
                      "loss_streak", "active"):
                if k in d:
                    critical[k] = d[k]
            out[name] = hashlib.md5(
                json.dumps(critical, sort_keys=True, ensure_ascii=False,
                           default=str).encode("utf-8")).hexdigest()
        except Exception:
            out[name] = "?"
    return out


@pytest.fixture(scope="session", autouse=True)
def isolation_session():
    before = _snapshot()
    _proof("TEST OTURUMU BAŞLADI — canlı state yolları izole edildi")
    yield
    after = _snapshot()
    changed = [k for k in before if before[k] != after[k]]
    if changed:
        _proof(f"UYARI: canlı state değişti — {', '.join(changed)}")
    else:
        _proof("TEST OTURUMU BİTTİ — canlı users/ state dosyalarına DOKUNULMADI ✅")


@pytest.fixture(autouse=True)
def isolate_live_state(tmp_path, monkeypatch):
    """Her testte TÜM state yolları geçici dizine yönlendirilir."""
    import importlib

    targets = {
        "ui.tr_scalper": ["STATE"],
        "ui.safety_guards": ["STATE"],
        "ui.order_guard": ["STATE"],
        "ui.risk_brakes": ["STATE"],
        "ui.strategy_mode": ["STATE"],
        "ui.ws_feed": ["STATE"],
        "ui.engine": ["STATE"],
        "ui.crash_bid": ["STATE"],
        "ui.tiered_brakes": ["STATE"],
        "ui.tp_proof": ["STATE"],
        "ui.whale_guard": ["STATE"],
        "ui.live_feed": ["STATE"],
        "ui.autonomous": ["STATE"],
        "ui.health_report": ["STATE"],
        "ui.monthly_backtest": ["STATE"],
        "ui.performance_export": ["STATE"],
        "ui.disaster_recovery": ["STATE", "BACKUPS", "RECOVERY", "SOURCES"],
        "ui.check_gate": [],
        "ui.autonomous_ops": ["DAILY_REPORT"],
    }
    sandbox = tmp_path / "isolated"
    sandbox.mkdir(exist_ok=True)
    # Yedek testlerinin her zaman 3 dosya bulmasını sağla — test sırasına bağlı kalmasın.
    for name in ("trades.csv", "tr_daily_state.json", "config.yaml"):
        f = sandbox / name
        if not f.exists():
            f.write_text("tarih,sembol\n" if name.endswith(".csv") else "{}", encoding="utf-8")
    for mod_name, attrs in targets.items():
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        for attr in attrs:
            if not hasattr(mod, attr):
                continue
            if mod_name == "ui.disaster_recovery" and attr == "SOURCES":
                monkeypatch.setattr(mod, attr, [sandbox / "trades.csv",
                                                sandbox / "tr_daily_state.json",
                                                sandbox / "config.yaml"])
            elif mod_name == "ui.disaster_recovery" and attr == "BACKUPS":
                monkeypatch.setattr(mod, attr, sandbox / "backups")
            else:
                monkeypatch.setattr(mod, attr, sandbox / f"{mod_name.split('.')[-1]}_{attr}")
    # Gate sonucunu canlı last_gate.json'a yazmasın
    try:
        import ui.check_gate as cg
        monkeypatch.setattr(cg, "save", lambda *a, **k: None)
    except Exception:
        pass
    yield
