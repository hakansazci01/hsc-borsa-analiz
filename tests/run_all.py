"""pytest olmadan da çalışan bağımsız test koşucusu."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests import test_contracts, test_golden, test_invariants  # noqa: E402


MODULES = (test_contracts, test_golden, test_invariants)


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
                fn()
                print(f"OK   {module.__name__}.{name}")
            except Exception as exc:
                failed += 1
                print(f"FAIL {module.__name__}.{name}: {type(exc).__name__}: {exc}")
    print(f"\n{total - failed}/{total} test geçti")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
