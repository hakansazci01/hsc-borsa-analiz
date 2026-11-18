"""
Goruntuleme katmani: fiyat + gostergeler ve sinyal isaretleri cizer.
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_symbol(
    df: pd.DataFrame,
    symbol: str,
    signal_info: dict,
    cfg: dict,
) -> str | None:
    """
    Tek bir hisse icin 3 panelli grafik cizer ve kaydeder.

    Panel 1: Fiyat, SMA20/50/200, Bollinger Bantlari, AL/SAT isaretleri
    Panel 2: RSI
    Panel 3: MACD

    Dondurur: kaydedilen dosya yolu veya None.
    """
    viz_cfg = cfg.get("visualize", {})
    if not viz_cfg.get("save_charts", True):
        return None

    chart_dir = viz_cfg.get("chart_dir", "charts")
    os.makedirs(chart_dir, exist_ok=True)

    fig, axes = plt.subplots(
        3, 1, figsize=(12, 10), sharex=True,
        gridspec_kw={"height_ratios": [3, 1, 1]}
    )
    fig.suptitle(
        f"{symbol} - Teknik Analiz & Sinyal: {signal_info['signal']} "
        f"(Puan: {signal_info['score']})",
        fontsize=14,
        fontweight="bold",
    )

    dates = df.index if isinstance(df.index, pd.DatetimeIndex) else range(len(df))

    # ---- Panel 1: Fiyat ----
    ax1 = axes[0]
    ax1.plot(dates, df["Close"], label="Kapanis", color="black", linewidth=1.5)
    for p in (20, 50, 200):
        col = f"SMA_{p}"
        if col in df.columns:
            ax1.plot(dates, df[col], label=f"SMA {p}", alpha=0.7)
    if "BB_Upper" in df.columns and "BB_Lower" in df.columns:
        ax1.plot(dates, df["BB_Upper"], label="BB Ust", color="gray", alpha=0.4, linestyle="--")
        ax1.plot(dates, df["BB_Lower"], label="BB Alt", color="gray", alpha=0.4, linestyle="--")
        ax1.fill_between(dates, df["BB_Upper"], df["BB_Lower"], color="gray", alpha=0.1)

    window = df.tail(60)
    buy_mask = window["Close"] <= window.get("BB_Lower", window["Close"])
    sell_mask = window["Close"] >= window.get("BB_Upper", window["Close"])
    ax1.scatter(window.index[buy_mask], window.loc[buy_mask, "Close"], marker="^", color="green", s=70, label="AL", zorder=5)
    ax1.scatter(window.index[sell_mask], window.loc[sell_mask, "Close"], marker="v", color="red", s=70, label="SAT", zorder=5)

    ax1.set_ylabel("Fiyat")
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)

    # ---- Panel 2: RSI ----
    ax2 = axes[1]
    ax2.plot(dates, df["RSI"], label="RSI (14)", color="purple", linewidth=1.2)
    ax2.axhline(70, color="red", linestyle="--", alpha=0.5)
    ax2.axhline(30, color="green", linestyle="--", alpha=0.5)
    ax2.set_ylabel("RSI")
    ax2.set_ylim(0, 100)
    ax2.grid(True, alpha=0.3)

    # ---- Panel 3: MACD ----
    ax3 = axes[2]
    ax3.plot(dates, df["MACD"], label="MACD", color="blue", linewidth=1)
    ax3.plot(dates, df["MACD_Signal"], label="Sinyal", color="orange", linewidth=1)
    ax3.bar(dates, df["MACD_Hist"], label="Histogram", alpha=0.3, width=0.8)
    ax3.axhline(0, color="black", linewidth=0.5)
    ax3.set_ylabel("MACD")
    ax3.grid(True, alpha=0.3)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    path = os.path.join(chart_dir, f"{symbol}_signal.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path