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
    """pytest monkeypatch'inin setattr(parçası) — bağımsız runner için."""

    @staticmethod
    def setattr(target: object, name: str, value: object) -> None:
        setattr(target, name, value)


def _call(fn):
    """pytest fixture'larını (tmp_path, monkeypatch) bağımsız runner'da da sağla."""
    params = inspect.signature(fn).parameters
    kwargs = {}
    if "tmp_path" in params:
        kwargs["tmp_path"] = Path(tempfile.mkdtemp(prefix="hsc_test_"))
    if "monkeypatch" in params:
        kwargs["monkeypatch"] = _Monkeypatch()
    return fn(**kwargs)


def main() -> int:
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
