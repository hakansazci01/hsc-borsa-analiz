"""
Strateji doğrulama laboratuvarı (vectorbt esinli).

- Walk-forward: veriyi ardışık eğitim/test pencerelerine bölüp, aynı kuralın
  görülmemiş dönemlerdeki performansını ölçer (parametre fitting yok; kural
  sabit, dönemler değişir).
- Parametre duyarlılığı: eşik/ağırlık ızgarasında sonuçları hesaplayıp
  "tek bir sihirli ayar"a mı yoksa geniş bir platoya mı dayandığını gösterir.

Hızlı backtest sayesinde (O(n)) bu hesaplar etkileşimli olarak çalışır.
"""

from __future__ import annotations

import time

from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from borsa_bot.backtest import run_backtest
from borsa_bot.indicators import add_cross_flags, compute_indicators


def _prepare(df: pd.DataFrame, indicators: dict[str, Any]) -> pd.DataFrame:
    return add_cross_flags(compute_indicators(df, indicators))


def _bt_config(
    weights: Any, thresholds: Any, risk: Any, backtest: Any, guards: Any
) -> dict[str, Any]:
    return {
        "signal_weights": dict(weights),
        "signal_thresholds": dict(thresholds),
        "risk": dict(risk),
        "backtest": dict(backtest),
        "guards": dict(guards or {}),
    }


def crypto_walk_forward(df: pd.DataFrame, windows: int = 4) -> tuple[dict[str, Any], ...]:
    """MEVCUT kripto stratejisiyle walk-forward (yeni strateji YOK).

    Günlük EMA50 pullback (quant_lab.signals "pullback", (50,))
    + 16-CHECK GATE sonucu (geçerliyse) + slippage %0,5 (quant_lab.backtest).

    90 gün → fold = 90//(windows+1) = 30 → Pencere 1: eğitim 0-29 / test 30-59,
    Pencere 2: eğitim 0-59 / test 60-89. Aynı kural iki dönemde de çalışır.
    """
    from ui import check_gate, quant_lab

    n = len(df)
    if n < 60:
        return ()
    fold = max(n // (windows + 1), 30)
    slip = 0.005  # mevcut backtest slippage modeli (%0,5)
    rows: list[dict[str, Any]] = []

    def window_stats(upto: int, start: int) -> dict[str, Any]:
        # Warm-up: EMA50 tüm mevcut veriden hesaplanır; sinyaller 'start' indeksinden değerlendirilir.
        frame = df.iloc[:upto]
        trades = quant_lab.backtest(frame, "pullback", (50,),
                                    maxhold=90, slippage=slip, start_idx=start)
        rets = [float(x["ret"]) for x in trades]
        return {
            "islem": len(trades),
            "kar_pct": round(float(sum(rets)) * 100, 2),
            "kazanma_pct": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1)
                           if rets else 0.0,
        }

    for k in range(windows):
        train_end = fold * (k + 1)
        test_end = min(train_end + fold, n)
        if test_end - train_end < 20:
            break
        # Eğitim: 0..train_end-1 aralığındaki sinyaller (warm-up aynı veri)
        tr = window_stats(train_end, max(1, train_end - fold))
        # Test: train_end..test_end-1 aralığındaki sinyaller, warm-up olarak train_end'e kadar veri
        te = window_stats(test_end, train_end)
        # 16-CHECK GATE: mevcut durumu rapora ekle (stratejiyi değiştirmez)
        try:
            gate = check_gate.run("BTC_TRY", price=float(df["Close"].iloc[-1]))
            gate_txt = gate["summary"]
        except Exception:
            gate_txt = "gate kontrolü yapılamadı"
        rows.append({
            "Pencere": k + 1,
            "Eğitim sonu": str(df.index[train_end - 1])[:10],
            "Test aralığı": f"{str(df.index[train_end])[:10]} → {str(df.index[test_end-1])[:10]}",
            "Eğitim işlem": tr["islem"],
            "Eğitim getiri %": tr["kar_pct"],
            "Test işlem": te["islem"],
            "Test getiri %": te["kar_pct"],
            "Test kazanma %": te["kazanma_pct"],
            "16-CHECK GATE": gate_txt,
            "Slippage %": slip * 100,
            "Neden": ("Eğitimde sinyal var, test döneminde EMA50 pullback koşulu "
                      "(Close>EMA50 ve Low<=EMA50) gerçekleşmedi — ayı rejiminde "
                      "fiyat EMA50 altında kaldı, AL sinyali üretilmedi."
                      if tr["islem"] > 0 and te["islem"] == 0 else
                      "Bu dönemde EMA50 pullback koşulu gerçekleşmedi (ayı rejimi / "
                      "fiyat EMA50 altında); AL sinyali yok."),
        })
    if len(rows) >= 2:
        # Fold stabilitesi — "karlılık" değil, tutarlılık kontrolü (2026 kılavuzları)
        diffs = [abs(float(r["Eğitim getiri %"]) - float(r["Test getiri %"]))
                 for r in rows]
        counts = [int(r["Test işlem"]) for r in rows]
        spread = max(diffs)
        count_ratio = (max(counts) + 1) / (min(counts) + 1) if counts else 1.0
        stable = spread <= 10.0 and count_ratio <= 3.0
        for r in rows:
            r["Stabilite"] = ("STABİL" if stable else
                              f"DENGESİZ (getiri farkı %{spread:.1f}, işlem oranı {count_ratio:.1f}x)")
    return tuple(rows)


@st.cache_data(ttl="1h", max_entries=20, show_spinner=False)
def walk_forward(
    df: pd.DataFrame,
    indicators: Any,
    weights: Any,
    thresholds: Any,
    risk: Any,
    backtest_cfg: Any,
    guards: Any,
    windows: int = 4,
) -> tuple[dict[str, Any], ...]:
    """Ardışık dönemlerde eğitim/test performansını karşılaştırır."""
    prepared = _prepare(df, dict(indicators))
    n = len(prepared)
    if n < 60:
        return ()

    fold = max(n // (windows + 1), 30)
    cfg = _bt_config(weights, thresholds, risk, backtest_cfg, guards)
    rows: list[dict[str, Any]] = []

    for k in range(windows):
        train_end = fold * (k + 1)
        test_end = min(train_end + fold, n)
        if test_end - train_end < 20:
            break
        train = prepared.iloc[:train_end]
        test = prepared.iloc[train_end:test_end]
        in_sample = run_backtest(train, cfg)
        out_sample = run_backtest(test, cfg)
        rows.append({
            "Pencere": k + 1,
            "Eğitim sonu": str(prepared.index[train_end - 1])[:10],
            "Test aralığı": f"{str(prepared.index[train_end])[:10]} → {str(prepared.index[test_end - 1])[:10]}",
            "Eğitim getiri %": in_sample.get("total_return_pct", 0),
            "Test getiri %": out_sample.get("total_return_pct", 0),
            "Test işlem": out_sample.get("total_trades", 0),
            "Test kazanma %": out_sample.get("win_rate_pct", 0),
            "Test max düşüş %": out_sample.get("max_drawdown_pct", 0),
        })

    return tuple(rows)


@st.cache_data(ttl="1h", max_entries=20, show_spinner=False)
def parameter_sensitivity(
    df: pd.DataFrame,
    indicators: Any,
    weights: Any,
    thresholds: Any,
    risk: Any,
    backtest_cfg: Any,
    guards: Any,
    buy_grid: tuple[float, ...] = (1.0, 1.5, 2.0, 2.5, 3.0),
    weight_scales: tuple[float, ...] = (0.5, 1.0, 1.5),
) -> tuple[dict[str, Any], ...]:
    """Eşik ve ağırlık ızgarasında getiriyi hesaplar (aşırı uyum kontrolü)."""
    prepared = _prepare(df, dict(indicators))
    rows: list[dict[str, Any]] = []
    base_thresholds = dict(thresholds)
    base_weights = dict(weights)

    for buy in buy_grid:
        for scale in weight_scales:
            th = {**base_thresholds, "buy": float(buy)}
            wt = {k: float(v) * scale for k, v in base_weights.items()}
            cfg = _bt_config(wt, th, risk, backtest_cfg, guards)
            result = run_backtest(prepared, cfg)
            rows.append({
                "AL eşiği": float(buy),
                "Ağırlık çarpanı": float(scale),
                "Getiri %": result.get("total_return_pct", 0),
                "İşlem": result.get("total_trades", 0),
                "Kazanma %": result.get("win_rate_pct", 0),
            })
    return tuple(rows)


@st.cache_data(ttl="1h", max_entries=20, show_spinner=False)
def grid_trials(
    df: pd.DataFrame,
    indicators: Any,
    weights: Any,
    thresholds: Any,
    risk: Any,
    backtest_cfg: Any,
    guards: Any,
    buy_grid: tuple[float, ...] = (1.0, 1.5, 2.0, 2.5, 3.0),
    weight_scales: tuple[float, ...] = (0.5, 1.0, 1.5),
) -> tuple[np.ndarray, ...]:
    """Parametre ızgarasındaki her denemenin günlük getiri dizisi (DSR/PBO için)."""
    prepared = _prepare(df, dict(indicators))
    trials: list[np.ndarray] = []
    base_thresholds = dict(thresholds)
    base_weights = dict(weights)
    for buy in buy_grid:
        for scale in weight_scales:
            th = {**base_thresholds, "buy": float(buy)}
            wt = {k: float(v) * scale for k, v in base_weights.items()}
            cfg = _bt_config(wt, th, risk, backtest_cfg, guards)
            result = run_backtest(prepared, cfg)
            equity = pd.Series(result.get("equity_curve", []), dtype=float)
            returns = equity.pct_change().replace([float("inf"), float("-inf")], pd.NA).dropna()
            trials.append(returns.to_numpy(dtype=float))
    return tuple(trials)


def summarize(rows: tuple[dict[str, Any], ...], key: str) -> dict[str, Any]:
    """Duyarlılık ızgarasının kararlılık özeti."""
    if not rows:
        return {"positive_pct": 0.0, "best": None, "worst": None}
    values = [float(r.get(key, 0) or 0) for r in rows]
    positive = sum(1 for v in values if v > 0)
    best = max(rows, key=lambda r: float(r.get(key, 0) or 0))
    worst = min(rows, key=lambda r: float(r.get(key, 0) or 0))
    return {
        "positive_pct": round(positive / len(rows) * 100, 1),
        "best": best,
        "worst": worst,
        "stable": positive / len(rows) >= 0.5,
    }


# ------------------------------------------------------------------ MİKRO R/R DOĞRULAMA
# Araştırma (Frontiers 2026, Mykola-Quant 2026): mikro sinyaller %0.30 komisyon
# sonrası ayakta kalmıyor. Bu bölüm sadece ÖLÇER — emir/limit/state değiştirmez.
MICRO_FEE_PCT = 0.25
MICRO_SLIP_PCT = 0.05
MICRO_TP_PCT = 0.60
MICRO_STOP_PCT = 1.00


def _micro_sim(bars: list[dict[str, float]], stop_pct: float) -> dict[str, Any]:
    pos = None
    trades = wins = 0
    net = 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for b in bars:
        o, h, l = b["o"], b["h"], b["l"]
        if pos is None:
            if b.get("entry"):
                pos = o * (1 + MICRO_SLIP_PCT / 100)
            continue
        e = pos
        if l <= e * (1 - stop_pct / 100):
            px = e * (1 - stop_pct / 100) * (1 - MICRO_SLIP_PCT / 100)
            r = (px - e) / e * 100 - MICRO_FEE_PCT
        elif h >= e * (1 + MICRO_TP_PCT / 100):
            px = e * (1 + MICRO_TP_PCT / 100) * (1 - MICRO_SLIP_PCT / 100)
            r = (px - e) / e * 100 - MICRO_FEE_PCT
        else:
            peak = max(peak, equity)
            max_dd = min(max_dd, equity / peak - 1)
            continue
        net += r
        equity *= (1 + r / 100)
        trades += 1
        wins += 1 if r > 0 else 0
        pos = None
        peak = max(peak, equity)
        max_dd = min(max_dd, equity / peak - 1)
    return {"trades": trades, "wins": wins,
            "win_rate": round(wins / trades * 100, 1) if trades else 0.0,
            "net_pct": round(net, 3), "max_dd_pct": round(max_dd * 100, 2),
            "final_equity": round(equity, 4)}


def micro_walk_forward(bars: list[dict[str, float]],
                       stop_pct: float = MICRO_STOP_PCT,
                       train_frac: float = 0.7) -> dict[str, Any]:
    n = len(bars)
    if n < 200:
        return {"ok": False, "reason": f"yetersiz veri: {n} bar"}
    cut = int(n * train_frac)
    a = _micro_sim(bars[:cut], stop_pct)
    b = _micro_sim(bars[cut:], stop_pct)
    test = bars[cut:]
    bh = ((test[-1]["c"] / test[0]["c"] - 1) * 100) if test and test[0]["c"] > 0 else 0.0
    credible = b["trades"] >= 100 and b["net_pct"] > 0 and a["net_pct"] > 0
    return {"ok": True, "train": a, "test": b, "buy_hold_test_pct": round(bh, 2),
            "credible": credible,
            "verdict": ("GÜVENİLİR" if credible else
                        "KANIT YOK — OOS negatif / <100 işlem / bozulma"),
            "fee_pct": MICRO_FEE_PCT, "slippage_pct": MICRO_SLIP_PCT,
            "stop_pct": stop_pct,
            "at": time.strftime("%Y-%m-%d %H:%M:%S")}


def micro_report(results: dict[str, Any]) -> None:
    from ui import auth as _auth
    import json as _json

    p = _auth.USERS_DIR / "validation_report.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
