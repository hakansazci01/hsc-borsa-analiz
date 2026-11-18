"""
Yeniden kullanılabilir arayüz bileşenleri: rozetler, göstergeler, grafikler.
Grafikler tema ile uyumlu olduğu için yerel Altair / ECharts kullanılır.
"""

from __future__ import annotations

from functools import reduce
from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from ui.help_texts import h
from ui.insights import SIGNAL_COLORS, signal_label


def real_money_warning(compact: bool = False) -> None:
    """Gerçek para kullanımı için görünür uyarı (bot ve canlı işlem sayfalarında)."""
    body = (
        "Sinyaller gecikmeli veriye dayanır ve istatistiksel olarak doğrulanmamıştır. "
        "Bu bir yatırım tavsiyesi değildir; uygulama emir göndermez."
    )
    if not compact:
        body += (
            " Gerçek para ile işlem öncesi **Denetim ve doğrulama** sayfasındaki kontrol listesini "
            "inceleyin, kağıt işlem ile en az 50-100 sinyal kaydedin ve güncel fiyatı KAP'tan teyit edin."
        )
    st.warning(body, icon=":material/warning:", title="Gerçek para uyarısı")


def signal_badge(signal: str) -> None:
    st.badge(
        signal_label(signal), color=SIGNAL_COLORS.get(signal, "gray"), help=h("signal")
    )


def confidence_gauge(value: int, height: int = 210) -> None:
    st.echarts_chart(
        {
            "series": [
                {
                    "type": "gauge",
                    "startAngle": 205,
                    "endAngle": -25,
                    "min": 0,
                    "max": 100,
                    "radius": "92%",
                    "center": ["50%", "62%"],
                    "progress": {"show": True, "width": 13, "roundCap": True},
                    "axisLine": {"lineStyle": {"width": 13, "roundCap": True}},
                    "pointer": {"show": False},
                    "axisTick": {"show": False},
                    "splitLine": {"show": False},
                    "axisLabel": {"show": False},
                    "anchor": {"show": False},
                    "title": {"show": True, "offsetCenter": [0, "62%"], "fontSize": 12, "color": "#94A3B8"},
                    "detail": {
                        "valueAnimation": True,
                        "formatter": "{value}",
                        "fontSize": 32,
                        "fontWeight": "bolder",
                        "offsetCenter": [0, "18%"],
                    },
                    "data": [{"value": int(value), "name": "Sinyal güveni"}],
                }
            ]
        },
        height=height,
        alt=f"Sinyal güven skoru {value} / 100",
    )


def _price_frame(df: pd.DataFrame, tail: int = 180) -> pd.DataFrame:
    d = df.tail(tail).reset_index().copy()
    d = d.rename(columns={d.columns[0]: "Tarih"})
    d["Tarih"] = pd.to_datetime(d["Tarih"])
    return d


def price_chart(df: pd.DataFrame, trades: list[dict[str, Any]], symbol: str) -> None:
    """Fiyat, SMA'lar, Bollinger bantları ve backtest işlem noktaları."""
    d = _price_frame(df)
    base = alt.Chart(d).encode(x=alt.X("Tarih:T", title=None))

    layers: list[alt.LayerChart] = []
    if {"BB_Lower", "BB_Upper"}.issubset(d.columns):
        layers.append(
            base.mark_area(opacity=0.10, color="#94A3B8").encode(
                y=alt.Y("BB_Lower:Q", title="Fiyat (₺ / $)"),
                y2="BB_Upper:Q",
            )
        )

    for ema_col, ema_color in (("EMA_12", "#38BDF8"), ("EMA_26", "#F472B6")):
        if ema_col in d.columns:
            layers.append(
                base.mark_line(color=ema_color, strokeWidth=1.0, opacity=0.7).encode(
                    y=alt.Y(f"{ema_col}:Q"),
                    tooltip=[alt.Tooltip(f"{ema_col}:Q", title=ema_col, format=".2f")],
                )
            )

    layers.append(
        base.mark_line(color="#E2E8F0", strokeWidth=1.6).encode(
            y=alt.Y("Close:Q", title="Fiyat (₺ / $)"),
            tooltip=[
                alt.Tooltip("Tarih:T", title="Tarih", format="%d %b %Y"),
                alt.Tooltip("Close:Q", title="Kapanış", format=".2f"),
            ],
        )
    )

    for period, color in ((20, "#60A5FA"), (50, "#A78BFA"), (200, "#FBBF24")):
        col = f"SMA_{period}"
        if col in d.columns:
            layers.append(
                base.mark_line(color=color, strokeWidth=1.1, opacity=0.85).encode(
                    y=alt.Y(f"{col}:Q"), tooltip=[alt.Tooltip(f"{col}:Q", title=f"SMA {period}", format=".2f")]
                )
            )

    markers: list[dict[str, Any]] = []
    for t in trades or []:
        if t.get("type") == "ENTRY":
            markers.append({"Tarih": t.get("date"), "Fiyat": t.get("price"), "Tür": "Giriş"})
        elif t.get("type", "").startswith("EXIT"):
            markers.append({"Tarih": t.get("date"), "Fiyat": t.get("price"), "Tür": "Çıkış"})
    if markers:
        m = pd.DataFrame(markers)
        m["Tarih"] = pd.to_datetime(m["Tarih"])
        layers.append(
            alt.Chart(m)
            .mark_point(size=110, filled=True, opacity=0.95)
            .encode(
                x="Tarih:T",
                y=alt.Y("Fiyat:Q"),
                shape=alt.Shape(
                    "Tür:N",
                    scale=alt.Scale(domain=["Giriş", "Çıkış"], range=["triangle-up", "triangle-down"]),
                    title="İşlem",
                ),
                color=alt.Color(
                    "Tür:N",
                    scale=alt.Scale(domain=["Giriş", "Çıkış"], range=["#34D399", "#F87171"]),
                    title="İşlem",
                ),
                tooltip=[alt.Tooltip("Tarih:T", title="Tarih", format="%d %b %Y"), "Tür:N", alt.Tooltip("Fiyat:Q", format=".2f")],
            )
        )

    chart = reduce(lambda a, b: a + b, layers).properties(height=360).interactive()
    st.altair_chart(chart, alt=f"{symbol} fiyat grafiği, hareketli ortalamalar ve işlem noktaları")


def oscillator_charts(df: pd.DataFrame) -> None:
    """Hacim, RSI ve MACD panelleri."""
    d = _price_frame(df, tail=160)
    base = alt.Chart(d).encode(x=alt.X("Tarih:T", title=None))

    if "Volume" in d.columns:
        volume = (
            base.mark_bar(opacity=0.45)
            .encode(
                y=alt.Y("Volume:Q", title="Hacim"),
                color=alt.condition(
                    alt.datum.Close >= alt.datum.Open,
                    alt.value("#34D399"),
                    alt.value("#F87171"),
                ),
                tooltip=[
                    alt.Tooltip("Tarih:T", title="Tarih", format="%d.%m"),
                    alt.Tooltip("Volume:Q", title="Hacim", format=",.0f"),
                ],
            )
            .properties(height=90)
        )
        st.altair_chart(volume, alt="Hacim çubukları: yeşil yükseliş, kırmızı düşüş günleri")
        st.caption("Hacim: yeşil = kapanış açılışın üstünde, kırmızı = altında.")

    rsi_line = base.mark_line(color="#A78BFA", strokeWidth=1.3).encode(
        y=alt.Y("RSI:Q", title="RSI", scale=alt.Scale(domain=[0, 100]))
    )
    overbought = alt.Chart(pd.DataFrame({"seviye": [70]})).mark_rule(color="#F87171", strokeDash=[4, 4]).encode(y="seviye:Q")
    oversold = alt.Chart(pd.DataFrame({"seviye": [30]})).mark_rule(color="#34D399", strokeDash=[4, 4]).encode(y="seviye:Q")
    st.altair_chart(
        (rsi_line + overbought + oversold).properties(height=130),
        alt="RSI göstergesi, 30 ve 70 eşik çizgileriyle",
    )

    hist = base.mark_bar(opacity=0.3, color="#60A5FA").encode(y=alt.Y("MACD_Hist:Q", title="MACD"))
    macd_line = base.mark_line(color="#60A5FA", strokeWidth=1.2).encode(y=alt.Y("MACD:Q"))
    signal_line = base.mark_line(color="#FBBF24", strokeWidth=1.2).encode(y=alt.Y("MACD_Signal:Q"))
    st.altair_chart(
        (hist + macd_line + signal_line).properties(height=130),
        alt="MACD çizgisi, sinyal çizgisi ve histogram",
    )


def equity_comparison(results: list[dict[str, Any]]) -> None:
    """Seçili hisselerin backtest sermaye eğrilerini karşılaştırır."""
    frames: list[pd.DataFrame] = []
    for r in results:
        bt = r.get("backtest")
        if not bt or not bt.get("equity_curve"):
            continue
        symbol = r["info"]["symbol"]
        frames.append(
            pd.DataFrame(
                {
                    "Tarih": pd.to_datetime(bt["dates"]),
                    symbol: bt["equity_curve"],
                }
            )
        )
    if not frames:
        st.info("Karşılaştırılabilir backtest verisi bulunamadı.")
        return
    merged = reduce(lambda a, b: pd.merge(a, b, on="Tarih", how="outer"), frames).sort_values("Tarih")
    st.line_chart(merged.set_index("Tarih"), alt="Hisselere göre backtest sermaye eğrilerinin karşılaştırması")


def score_chart(results: list[dict[str, Any]]) -> None:
    """Hisselerin sinyal puanlarını yön renkleriyle gösterir."""
    rows = []
    for r in results:
        if "info" not in r:
            continue
        info = r["info"]
        rows.append(
            {
                "Hisse": info["symbol"],
                "Puan": float(info["score"]),
                "Sinyal": signal_label(info["signal"]),
            }
        )
    if not rows:
        return
    d = pd.DataFrame(rows)
    color_scale = alt.Scale(
        domain=["Güçlü AL", "AL", "NÖTR", "SAT", "Güçlü SAT"],
        range=["#059669", "#34D399", "#94A3B8", "#F87171", "#DC2626"],
    )
    chart = (
        alt.Chart(d)
        .mark_bar(cornerRadiusEnd=3)
        .encode(
            x=alt.X("Hisse:N", title=None, sort="-y"),
            y=alt.Y("Puan:Q", title="Sinyal puanı", scale=alt.Scale(domain=[-5, 5])),
            color=alt.Color("Sinyal:N", scale=color_scale, title="Sinyal"),
            tooltip=["Hisse:N", alt.Tooltip("Puan:Q", format=".2f"), "Sinyal:N"],
        )
        .properties(height=260)
    )
    st.altair_chart(chart, alt="Hisselerin sinyal puanları, alım-satım yönüne göre renklendirilmiş")


def trades_table(bt: dict[str, Any]) -> None:
    trades = bt.get("trades", []) if bt else []
    if not trades:
        st.caption("Bu dönemde kayıtlı işlem yok.")
        return
    df = pd.DataFrame(trades)[["date", "type", "price", "pnl_pct", "capital"]].copy() if any(
        "pnl_pct" in t for t in trades
    ) else pd.DataFrame(trades)[["date", "type", "price", "capital"]].copy()
    df = df.rename(
        columns={
            "date": "Tarih", "type": "İşlem", "price": "Fiyat",
            "pnl_pct": "K/Z (%)", "capital": "Sermaye",
        }
    )
    st.dataframe(
        df,
        hide_index=True,
        column_config={
            "Tarih": st.column_config.TextColumn(help="İşlemin gerçekleştiği tarih."),
            "İşlem": st.column_config.TextColumn(help="Giriş (ENTRY) veya çıkış (EXIT) işlemi."),
            "Fiyat": st.column_config.NumberColumn(format="%.2f", help="İşlem fiyatı."),
            "K/Z (%)": st.column_config.NumberColumn(format="%.2f", help="Çıkış işleminin kâr/zarar yüzdesi."),
            "Sermaye": st.column_config.NumberColumn(format="%.2f", help="İşlem sonrası kurgusal sermaye."),
        },
        alt="Backtest işlem geçmişi",
    )
