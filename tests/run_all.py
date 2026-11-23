"""pytest olmadan da çalışan bağımsız test koşucusu."""

from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests import (  # noqa: E402
    test_bot_features, test_contracts, test_golden, test_invariants, test_live_guard,
)


MODULES = (test_contracts, test_golden, test_invariants, test_bot_features, test_live_guard)


class _Monkeypatch:
    """pytest monkeypatch'inin setattr(parçası) — geri alma ile."""

    def __init__(self) -> None:
        self._undo: list[tuple[object, str, object]] = []

    def setattr(self, target: object, name: str, value: object) -> None:
        old = getattr(target, name, None)
        self._undo.append((target, name, old))
        setattr(target, name, value)

    def undo(self) -> None:
        for target, name, value in reversed(self._undo):
            setattr(target, name, value)


def _call(fn):
    """pytest fixture'larını (tmp_path, monkeypatch) bağımsız runner'da da sağla."""
    # Her test öncesi izolasyonu yenile — önceki test modül state'lerini bozmuş olabilir.
    _isolate_live_state()
    params = inspect.signature(fn).parameters
    kwargs = {}
    if "tmp_path" in params:
        kwargs["tmp_path"] = Path(tempfile.mkdtemp(prefix="hsc_test_"))
    patch = None
    if "monkeypatch" in params:
        patch = _Monkeypatch()
        kwargs["monkeypatch"] = patch
    try:
        return fn(**kwargs)
    finally:
        if patch is not None:
            patch.undo()


def _isolate_live_state() -> None:
    """Canlı users/ state dosyalarını asla değiştirme — tüm modülleri sandbox'a yönlendir."""
    import importlib

    sandbox = Path(tempfile.mkdtemp(prefix="hsc_runall_"))
    for n in ("trades.csv", "tr_daily_state.json", "config.yaml"):
        f = sandbox / n
        if not f.exists():
            f.write_text("tarih,sembol\n" if n.endswith(".csv") else "{}", encoding="utf-8")
    targets = {
        "ui.tr_scalper": ["STATE", "STOP_FILE"], "ui.safety_guards": ["STATE"],
        "ui.order_guard": ["STATE"], "ui.risk_brakes": ["STATE"],
        "ui.strategy_mode": ["STATE"], "ui.ws_feed": ["STATE"],
        "ui.engine": ["STATE"], "ui.crash_bid": ["STATE"],
        "ui.tiered_brakes": ["STATE"], "ui.tp_proof": ["STATE"],
        "ui.live_feed": ["STATE"], "ui.autonomous": ["STATE"],
        "ui.health_report": ["STATE"], "ui.disaster_recovery": ["STATE"],
        "ui.paper": ["STATE", "TRADES_CSV"],
        "ui.amm": ["STATE"], "ui.motor_guard": ["STATE"],
        "ui.autonomous_ops": ["DAILY_REPORT"],
        "ui.tr_scalper": ["STATE", "STOP_FILE"],
    }
    for name, attrs in targets.items():
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        for attr in attrs:
            if hasattr(mod, attr):
                setattr(mod, attr, sandbox / f"{name.split('.')[-1]}_{attr}")
    # Genel tarama: ui.* modüllerindeki tüm state/log/csv Path alanları sandbox'a.
    for name, mod in list(sys.modules.items()):
        if not name.startswith("ui."):
            continue
        for attr in list(vars(mod)):
            if attr in ("STATE", "LOG", "CSV", "REPORT_FILE", "DAILY_REPORT",
                        "BACKUPS", "RECOVERY", "SOURCES") or attr.endswith("_STATE"):
                val = getattr(mod, attr)
                if isinstance(val, Path):
                    setattr(mod, attr, sandbox / f"{name.split('.')[-1]}_{attr}")
    try:
        import ui.disaster_recovery as dr
        dr.BACKUPS = sandbox / "backups"
        dr.RECOVERY = sandbox / "recovery.json"
        dr.SOURCES = [sandbox / "trades.csv", sandbox / "tr_daily_state.json",
                      sandbox / "config.yaml"]
        import ui.check_gate as cg
        cg.save = lambda *a, **k: None
    except Exception:
        pass


def main() -> int:
    _isolate_live_state()
    total = failed = 0
    for module in MODULES:
        for name in sorted(dir(module)):
            if not name.startswith("test_"):
                continue
            fn = getattr(module, name)
            if not callable(fn):
                continue
            total += 1
            try:
                _call(fn)
                print(f"OK   {module.__name__}.{name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {module.__name__}.{name}: {type(exc).__name__}: {exc}")
    print(f"\n{total - failed}/{total} test geçti")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
