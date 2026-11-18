"""
Bilimsel strateji doğrulama araçları.

Kaynak: Bailey & López de Prado (DSR, PBO/CSCV), López de Prado (purge/embargo),
Brier (kalibrasyon). Amaç: "güzel backtest"i değil, **gerçek edge** olup olmadığını ölçmek.
"""

from __future__ import annotations

import math
import statistics
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd

from borsa_bot.backtest import run_backtest


_NORM = statistics.NormalDist()


def _sharpe(returns: np.ndarray) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 3:
        return 0.0
    std = float(np.std(r, ddof=1))
    return float(np.mean(r) / std) if std > 0 else 0.0


def _moments(r: np.ndarray) -> tuple[float, float]:
    r = np.asarray(r, dtype=float)
    if len(r) < 3:
        return 0.0, 3.0
    mean = float(np.mean(r))
    sd = float(np.std(r, ddof=1))
    if sd == 0:
        return 0.0, 3.0
    z = (r - mean) / sd
    return float(np.mean(z ** 3)), float(np.mean(z ** 4))


def deflated_sharpe(trial_returns: list[np.ndarray], n_trials: int | None = None) -> dict[str, Any]:
    """Bailey-López de Prado Deflated Sharpe Ratio (çoklu test düzeltmesi)."""
    if len(trial_returns) < 2:
        return {"available": False, "reason": "DSR için en az 2 deneme gerekir."}
    sharpes = np.array([_sharpe(r) for r in trial_returns])
    n = int(n_trials or len(sharpes))
    if n <= 1:
        return {"available": False, "reason": "Geçerli deneme sayısı yok."}

    gamma = 0.5772156649015329
    try:
        extreme = (
            (1 - gamma) * _NORM.inv_cdf(1 - 1 / n)
            + gamma * _NORM.inv_cdf(1 - 1 / (n * math.e))
        )
    except (ValueError, ZeroDivisionError):
        extreme = 0.0
    hurdle = float(np.std(sharpes, ddof=1)) * extreme

    champion = trial_returns[int(np.argmax(sharpes))]
    sr = _sharpe(champion)
    g3, g4 = _moments(champion)
    denom = math.sqrt(max(1e-12, 1 - g3 * sr + (g4 - 1) / 4 * sr * sr))
    z = (sr - hurdle) * math.sqrt(max(len(champion) - 1, 1)) / denom
    dsr = float(_NORM.cdf(z))
    return {
        "available": True,
        "observed_sr": round(sr, 4),
        "hurdle_sr": round(hurdle, 4),
        "n_trials": n,
        "dsr": round(dsr, 3),
        "verdict": (
            "Şansla uyumlu; strateji kanıtlanmadı."
            if dsr < 0.95 else "Çoklu test düzeltmesinden sonra anlamlı."
        ),
    }


def pbo_cscv(trial_returns: list[np.ndarray], slices: int = 8) -> dict[str, Any]:
    """Combinatorially Symmetric Cross-Validation ile backtest aşırı uyum olasılığı."""
    if len(trial_returns) < 5:
        return {"available": False, "reason": "PBO için en az 5 deneme gerekir."}
    matrix = np.column_stack([
        np.asarray(r, dtype=float)[: min(len(x) for x in trial_returns)]
        for r in trial_returns
    ])
    matrix = np.nan_to_num(matrix, nan=0.0)
    T, N = matrix.shape
    S = int(min(slices, max(4, T // 20)))
    if S % 2 or S < 4:
        S -= 1
    chunks = np.array_split(np.arange(T), S)

    logits: list[float] = []
    oos_ranks: list[float] = []
    for selected in combinations(range(S), S // 2):
        is_idx = np.concatenate([chunks[i] for i in selected])
        oos_idx = np.concatenate([chunks[i] for i in range(S) if i not in selected])
        is_sh = np.array([_sharpe(matrix[is_idx, j]) for j in range(N)])
        oos_sh = np.array([_sharpe(matrix[oos_idx, j]) for j in range(N)])
        champion = int(np.argmax(is_sh))
        rank = float(np.mean(oos_sh <= oos_sh[champion]))
        oos_ranks.append(rank)
        omega = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(omega / (1 - omega)))

    if not logits:
        return {"available": False, "reason": "CSCV kombinasyonu üretilemedi."}
    pbo = float(np.mean(np.array(logits) < 0))
    median_rank = float(np.median(oos_ranks))
    return {
        "available": True,
        "pbo": round(pbo, 3),
        "combinations": len(logits),
        "slices": S,
        "trials": N,
        "median_oos_rank": round(median_rank, 3),
        "verdict": (
            "Düşük aşırı uyum riski (PBO < 0.10)."
            if pbo < 0.10
            else "Orta risk." if pbo < 0.50
            else "Yüksek aşırı uyum riski; seçim şansla tutarlı."
        ),
    }


def permutation_test(returns: np.ndarray, iterations: int = 1000, seed: int = 42) -> dict[str, Any]:
    """Getirileri rastgele permüte edip gözlenen Sharpe'ın şansa karşı anlamlılığını ölçer."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 10:
        return {"available": False, "reason": "Permütasyon için yetersiz veri."}
    observed = _sharpe(r)
    rng = np.random.default_rng(seed)
    null = np.array([_sharpe(rng.permutation(r)) for _ in range(iterations)])
    p_value = float((null >= observed).mean())
    return {
        "available": True,
        "observed_sr": round(observed, 4),
        "null_mean_sr": round(float(null.mean()), 4),
        "p_value": round(p_value, 4),
        "verdict": "Şansla açıklanamaz (p<0.05)." if p_value < 0.05 else "Şansla uyumlu; kanıt yok.",
    }


def purged_walk_forward(
    df: pd.DataFrame,
    indicators: Any,
    weights: Any,
    thresholds: Any,
    risk: Any,
    backtest_cfg: Any,
    guards: Any,
    windows: int = 4,
    purge_bars: int = 20,
    embargo_bars: int = 5,
) -> tuple[dict[str, Any], ...]:
    """Eğitim/test sınırında purge + embargo uygulayan walk-forward."""
    from ui.validation import _prepare

    prepared = _prepare(df, dict(indicators))
    n = len(prepared)
    fold = max(n // (windows + 1), 40)
    cfg = {
        "signal_weights": dict(weights), "signal_thresholds": dict(thresholds),
        "risk": dict(risk), "backtest": dict(backtest_cfg), "guards": dict(guards or {}),
    }
    rows: list[dict[str, Any]] = []
    for k in range(windows):
        train_end = fold * (k + 1)
        test_end = min(train_end + fold, n)
        if test_end - train_end <= purge_bars + embargo_bars + 10:
            break
        train = prepared.iloc[: max(train_end - purge_bars, 50)]
        test = prepared.iloc[min(train_end + embargo_bars, n - 1): test_end]
        in_sample = run_backtest(train, cfg)
        out_sample = run_backtest(test, cfg)
        rows.append({
            "Pencere": k + 1,
            "Eğitim sonu": str(prepared.index[train_end - 1])[:10],
            "Test aralığı": f"{str(prepared.index[min(train_end + embargo_bars, n-1)])[:10]} → {str(prepared.index[test_end-1])[:10]}",
            "Purge": purge_bars, "Embargo": embargo_bars,
            "Eğitim getiri %": in_sample.get("total_return_pct", 0),
            "Test getiri %": out_sample.get("total_return_pct", 0),
            "Test işlem": out_sample.get("total_trades", 0),
            "Test max düşüş %": out_sample.get("max_drawdown_pct", 0),
        })
    return tuple(rows)


def calibration_report(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    """Brier skoru, Brier skill score ve güven kova tablosu."""
    rows = [
        o for o in outcomes
        if o.get("confidence") and "pnl_pct" in o
    ]
    if len(rows) < 5:
        return {"available": False, "reason": "Kalibrasyon için en az 5 gerçekleşmiş işlem gerekir."}
    probs = np.array([float(o["confidence"]) / 100 for o in rows])
    actual = np.array([1.0 if float(o["pnl_pct"]) > 0 else 0.0 for o in rows])
    brier = float(np.mean((probs - actual) ** 2))
    base = float(actual.mean())
    bss = 1 - brier / (base * (1 - base)) if 0 < base < 1 else 0.0

    buckets: list[dict[str, Any]] = []
    for low, high in ((0, 40), (40, 60), (60, 80), (80, 101)):
        subset = [o for o in rows if low <= float(o["confidence"]) < high]
        if not subset:
            continue
        pred = float(np.mean([float(o["confidence"]) for o in subset]))
        act = float(np.mean([1.0 if float(o["pnl_pct"]) > 0 else 0.0 for o in subset]))
        buckets.append({
            "Güven aralığı": f"{low}-{min(high,100)}",
            "Örnek": len(subset),
            "Ort. tahmin %": round(pred, 1),
            "Gerçek kazanma %": round(act * 100, 1),
            "Sapma": round(act * 100 - pred, 1),
        })
    return {
        "available": True,
        "samples": len(rows),
        "brier": round(brier, 4),
        "brier_skill": round(bss, 3),
        "buckets": buckets,
        "verdict": (
            "Güven tahminleri iyi kalibre."
            if abs(bss) < 0.05 and brier < 0.25
            else "Güven tahminleri gerçek sonuçlardan sapıyor; dikkatli yorumlayın."
        ),
    }


def data_quality(df: pd.DataFrame) -> dict[str, Any]:
    """OHLCV veri bütünlüğü: NaN, tekrar, boşluk, uç getiri."""
    issues: list[str] = []
    if df is None or df.empty:
        return {"ok": False, "issues": ["Veri boş."]}
    if df.index.has_duplicates:
        issues.append("Tekrar eden tarih satırları var.")
    needed = ["Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        issues.append(f"Eksik kolonlar: {missing}")
    else:
        if df["Close"].isna().any():
            issues.append("Close içinde NaN var.")
        if (df["Close"] <= 0).any():
            issues.append("Sıfır/negatif fiyat var.")
        if (df["High"] < df["Low"]).any():
            issues.append("High < Low olan satır var.")
        rets = df["Close"].pct_change().dropna()
        extreme = int((rets.abs() > 0.25).sum())
        if extreme:
            issues.append(f"{extreme} adet %25 üzeri günlük hareket (split/veri hatası olabilir).")
    return {
        "ok": not issues,
        "rows": len(df),
        "issues": issues,
    }
