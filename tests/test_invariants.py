"""Market invariansları ve güvenlik katmanı testleri (property-style)."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from borsa_bot.risk import position_size
from ui import data_integrity, log_store, trust_gate


def test_ohlc_invariants_random() -> None:
    rng = random.Random(7)
    for _ in range(200):
        open_ = rng.uniform(5, 500)
        close = max(0.01, open_ + rng.uniform(-20, 20))
        high = max(open_, close) + abs(rng.uniform(0, 10))
        low = max(0.01, min(open_, close) - abs(rng.uniform(0, 10)))
        assert low <= high
        assert low <= open_ <= high
        assert low <= close <= high
        assert rng.uniform(0, 1e6) >= 0


def test_position_size_never_negative() -> None:
    for capital in (0, 1000, 100000):
        for risk_pct in (0, 0.01, 0.05, 0.5):
            for entry, stop in ((100, 95), (100, 0), (10, 9.5)):
                size = position_size(capital, risk_pct, entry, stop)
                assert size >= 0


def test_log_sanitization_and_rotation() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "test.jsonl"
        log_store.append(path, {"event": "A\nB\rC", "payload": {"x": "line1\nline2"}})
        rows = log_store.read(path)
        assert len(rows) == 1
        assert "\n" not in rows[0]["event"]
        assert "\n" not in rows[0]["payload"]["x"]
        stats = log_store.stats(path)
        assert stats["active_kb"] >= 0

        # Küçük sınırla rotasyonu zorla
        for i in range(12):
            log_store.append(path, {"event": f"kayit-{i}", "value": i}, max_bytes=120, keep=3)
        backup = path.with_suffix(path.suffix + ".1")
        assert backup.exists(), " Rotasyon yedeği oluşmadı"
        assert len(log_store.read(path, 50)) >= 5, "Döndürme sonrası kayıtlar okunamadı"


def test_data_integrity_two_signals() -> None:
    idx = pd.date_range("2025-01-01", periods=120, freq="D")
    clean = pd.DataFrame({
        "Close": np.linspace(100, 120, 120),
        "Volume": np.full(120, 1_000_000.0),
    }, index=idx)
    assert data_integrity.analyze(clean)["level"] == "ok"

    bad = clean.copy()
    bad.iloc[80, bad.columns.get_loc("Close")] = bad.iloc[79, bad.columns.get_loc("Close")] / 2
    bad.iloc[80, bad.columns.get_loc("Volume")] = 100_000.0
    assert data_integrity.analyze(bad)["level"] == "quarantine"


def test_trust_gate_shape() -> None:
    snap = {
        "quote_source": "test",
        "info": {
            "price": 100.0, "change_pct": 1.0, "bid": 99.9, "ask": 100.1,
            "quote_time": datetime.now(timezone.utc).isoformat(),
        },
    }
    gate = trust_gate.evaluate("THYAO", {"decision": "AL", "confidence": 70}, snap)
    for key in ("symbol", "level", "note", "checks", "age_min", "source", "decision_id"):
        assert key in gate, key
