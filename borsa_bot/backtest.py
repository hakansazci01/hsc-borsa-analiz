"""
Geriye dönük test (backtest) modülü.

Olay tabanlı günlük simülasyon:
- Sinyal günün kapanışında üretilir; işlem ertesi günün kapanışında yapılır.
- Stop-loss / take-profit günlük High/Low ile kontrol edilir (giriş günü hariç).
- AL sinyalinde alınır, SAT sinyalinde çıkılır.
- Komisyon ve kayma (slippage) her giriş/çıkışta uygulanır.
- Puan, canlı sinyal motoruyla aynı şekilde normalize edilir.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def run_backtest(df: pd.DataFrame, cfg: dict[str, Any]) -> dict[str, Any]:
    bt_cfg = cfg.get("backtest", {})
    risk_cfg = cfg.get("risk", {})
    thresholds = cfg.get("signal_thresholds", {})

    initial_capital = float(risk_cfg.get("initial_capital", 100000))
    commission = float(risk_cfg.get("commission_pct", 0.0015))
    slippage = float(risk_cfg.get("slippage_pct", 0.0))
    stop_loss_pct = float(risk_cfg.get("stop_loss_pct", 0.05))
    take_profit_pct = float(risk_cfg.get("take_profit_pct", 0.10))

    from borsa_bot.guards import RiskGuards
    from borsa_bot.indicators import add_cross_flags
    from borsa_bot.signals import _score, score_to_signal

    guards = RiskGuards(cfg.get("guards")) if cfg.get("guards") else None

    original_index = df.index
    date_index = list(original_index)
    df = df.copy().dropna(subset=["Close"]).reset_index(drop=True)
    n = len(df)
    if n < 3:
        return {"error": "Yetersiz veri (en az 3 gün gerekli)."}

    weights = cfg.get("signal_weights", {})

    # Göstergeler tamamen geçmişe baklı oldukları için tek seferde hesaplanabilir.
    # Her adımda artan pencere oluşturmak O(n^2) yavaşlık yaratıyordu; O(n)'e indirildi.
    flagged = add_cross_flags(df)
    signals: list[str] = []
    scores: list[float] = []
    for i in range(n):
        row = flagged.iloc[i]
        prev_row = flagged.iloc[i - 1] if i > 0 else row
        raw, _ = _score(row, prev_row, weights, thresholds, has_prev=i > 0)
        sig, normalized = score_to_signal(raw, weights, thresholds)
        signals.append(sig)
        scores.append(normalized)

    capital = initial_capital
    position = 0.0
    entry_price = 0.0
    stop_price = 0.0
    target_price = 0.0
    entry_index = -1  # giriş gününde stop kontrolü yapılmaz (look-ahead önlemi)

    trades: list[dict[str, Any]] = []
    equity_curve: list[float] = []
    dates: list[Any] = []

    def _date(row: pd.Series, position_index: int) -> str:
        value = row.name
        return str(value) if value is not None else str(position_index)

    def _close_position(exit_price: float, reason: str, date_value: str, bar_index: int) -> None:
        nonlocal capital, position, entry_price
        pnl_pct = (exit_price - entry_price) / entry_price if entry_price else 0.0
        gross = position * exit_price
        capital += gross * (1 - commission)
        if guards is not None:
            day = str(date_index[bar_index])[:10] if bar_index < len(date_index) else date_value[:10]
            guards.register_exit(bar_index, day, pnl_pct * 100, reason)
        trades.append(
            {
                "type": "EXIT",
                "reason": reason,
                "date": date_value,
                "price": round(exit_price, 4),
                "pnl_pct": round(pnl_pct * 100, 2),
                "capital": round(capital, 2),
            }
        )
        position = 0.0
        entry_price = 0.0

    for i in range(n - 1):
        today = df.iloc[i]
        tomorrow = df.iloc[i + 1]
        exec_price = float(tomorrow["Close"])
        next_date = _date(tomorrow, i + 1)
        sig = signals[i]

        # Koruma katmanı: zirve sermayeyi güncelle ve işlem izni sorgula
        equity_now = capital + (position * float(today["Close"]) if position > 0 else 0.0)
        guard_result = None
        if guards is not None:
            day_now = str(date_index[i])[:10] if i < len(date_index) else next_date[:10]
            guard_result = guards.evaluate(i, day_now, equity_now)

        # Açık pozisyon: stop / hedef kontrolü (giriş günü hariç)
        if position > 0 and i > entry_index:
            low_today = float(today["Low"])
            high_today = float(today["High"])
            exit_price = None
            reason = ""
            if low_today <= stop_price:
                exit_price = stop_price * (1 - slippage)
                reason = "Stop-Loss"
            elif high_today >= target_price:
                exit_price = target_price * (1 - slippage)
                reason = "Take-Profit"

            if exit_price is not None:
                _close_position(exit_price, reason, next_date, i)
                equity_curve.append(capital)
                dates.append(next_date)
                continue

        # Açık pozisyonda SAT sinyali: ertesi gün kapanışında çık
        if position > 0 and sig in ("SELL", "STRONG_SELL"):
            _close_position(exec_price * (1 - slippage), "Sinyal", next_date, i)
            equity_curve.append(capital)
            dates.append(next_date)
            continue

        # Yeni alım
        if (
            position == 0 and sig in ("STRONG_BUY", "BUY") and scores[i] > 0
            and (guard_result is None or guard_result["allowed"])
        ):
            fill_price = exec_price * (1 + slippage)
            size_multiplier = 1.0 if guard_result is None else guard_result["size_multiplier"]
            qty = capital * float(risk_cfg.get("position_size_pct", 0.10)) * size_multiplier / fill_price
            qty = math.floor(qty * 100) / 100
            if qty > 0:
                cost = qty * fill_price * (1 + commission)
                if cost <= capital:
                    capital -= cost
                    position = qty
                    entry_price = fill_price
                    entry_index = i + 1
                    stop_price = entry_price * (1 - stop_loss_pct)
                    target_price = entry_price * (1 + take_profit_pct)
                    trades.append(
                        {
                            "type": "ENTRY",
                            "date": next_date,
                            "price": round(fill_price, 4),
                            "qty": round(qty, 4),
                            "capital": round(capital, 2),
                        }
                    )

        # Gün sonu sermaye, işlemin yapıldığı (ertesi) günün kapanışında işaretlenir
        equity = capital + position * exec_price if position > 0 else capital
        equity_curve.append(equity)
        dates.append(next_date)

    # Açık kalan pozisyonu son kapanışta kapat (çift sayımı önle)
    if position > 0:
        last_close = float(df.iloc[-1]["Close"])
        _close_position(last_close * (1 - slippage), "Son Gün", _date(df.iloc[-1], n - 1), n - 1)

    # final_equity her durumda nakit sermayedir; pozisyon kapatıldı
    final_equity = capital
    total_return = (final_equity - initial_capital) / initial_capital

    exit_trades = [t for t in trades if t["type"].startswith("EXIT")]
    win_trades = [t for t in exit_trades if t.get("pnl_pct", 0) > 0]
    win_rate = (len(win_trades) / len(exit_trades)) if exit_trades else 0.0

    # Maksimum düşüş, başlangıç sermayesini de içeren seri üzerinden hesaplanır
    eq = pd.Series([initial_capital] + equity_curve, dtype=float)
    running_max = eq.cummax()
    drawdown = (eq - running_max) / running_max
    max_dd = float(drawdown.min()) if len(drawdown) else 0.0

    # Yıllıklandırma: gerçek tarih aralığı varsa onu kullan, yoksa 252 günlük varsayım
    if isinstance(original_index, pd.DatetimeIndex) and len(original_index) >= 2:
        days = (original_index[-1] - original_index[0]).days
        years = max(days / 365.25, 1 / 365.25)
    else:
        years = max(n / 252, 1 / 252)
    cagr = (final_equity / initial_capital) ** (1 / years) - 1 if final_equity > 0 else -1.0

    # Risk düzeltilmiş performans (profesyonel standart)
    returns = eq.pct_change().replace([float("inf"), float("-inf")], pd.NA).dropna()
    sharpe = sortino = 0.0
    if len(returns) > 2:
        std = float(returns.std())
        if std > 0:
            sharpe = float(returns.mean()) / std * (252 ** 0.5)
        downside = returns[returns < 0]
        dstd = float(downside.std()) if len(downside) > 1 else 0.0
        if dstd > 0:
            sortino = float(returns.mean()) / dstd * (252 ** 0.5)
    calmar = cagr / abs(max_dd) if max_dd else 0.0

    return {
        "initial_capital": round(initial_capital, 2),
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return * 100, 2),
        "cagr_pct": round(cagr * 100, 2),
        "win_rate_pct": round(win_rate * 100, 2),
        "total_trades": len(exit_trades),
        "winning_trades": len(win_trades),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "trades": trades,
        "equity_curve": equity_curve,
        "dates": [str(d) for d in dates],
        "guard_snapshot": guards.snapshot() if guards is not None else None,
    }
