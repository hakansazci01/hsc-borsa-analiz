"""
Karar gerekçesi + zaman ufuklu K/Z projeksiyonu.

Üç soruya cevap verir:
1) Neden AL / BEKLE / SAT?  -> faktör katkıları (explainability)
2) Benzer sinyallerde geçmişte ne oldu? -> 1/5/20 gün ileri getiri + MFE/MAE
3) Bundan sonra 1/5/20 günde ne kadar K/Z olabilir? -> GBM Monte Carlo bantları + stop/hedef olasılığı

Hiçbiri garanti değildir; istatistiksel profil ve olasılık gösterir.
"""

from __future__ import annotations

from typing import Any

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from borsa_bot.indicators import add_cross_flags, compute_indicators
from borsa_bot.signals import _score, score_to_signal


HORIZONS = (1, 5, 20)


def factor_breakdown(
    decision: dict[str, Any],
    regime: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Kararın hangi faktörlerden beslendiğini işaretli katkılarla açıklar."""
    factors: list[dict[str, Any]] = []
    tech = decision.get("technical", {}) or {}

    buy = int(tech.get("buy_votes", 0) or 0)
    sell = int(tech.get("sell_votes", 0) or 0)
    neutral = int(tech.get("neutral_votes", 0) or 0)
    total = max(buy + sell + neutral, 1)
    factors.append({
        "Faktör": "Teknik oy uzlaşısı",
        "Katkı": round((buy - sell) / total, 2),
        "Neden": f"Göstergeler {buy} AL / {sell} SAT / {neutral} nötr oy verdi.",
    })

    for item in tech.get("timeframes", [])[:6]:
        value = float(item.get("value", 0))
        if value:
            factors.append({
                "Faktör": f"Zaman dilimi {item['timeframe']}",
                "Katkı": round(value / 2, 2),
                "Neden": (
                    f"{item['recommendation']}: AL {item['buy']} / SAT {item['sell']} "
                    f"(ağırlık {item.get('weight', 1)})"
                ),
            })

    news_score = float((decision.get("news") or {}).get("score", 0) or 0)
    if abs(news_score) > 0.001:
        factors.append({
            "Faktör": "KAP haber duyarımı",
            "Katkı": round(news_score, 2),
            "Neden": (
                "Öne çıkan duyurular olumlu yönde." if news_score > 0
                else "Öne çıkan duyurular olumsuz yönde."
            ),
        })

    if regime:
        risk = regime.get("regime") in ("Düşüş", "Yüksek oynaklık")
        factors.append({
            "Faktör": "Piyasa rejimi",
            "Katkı": -0.6 if risk else 0.3,
            "Neden": f"{regime.get('regime')} rejimi tespit edildi; "
                     + ("pozisyon azaltıldı/BEKLE'ye çevrildi." if risk else "sinyal daha güvenilir sayıldı."),
        })

    return factors


@st.cache_data(ttl="1h", max_entries=60, show_spinner=False)
def analog_stats(
    df: pd.DataFrame,
    indicators: Any,
    weights: Any,
    thresholds: Any,
    direction: str,
    horizons: tuple[int, ...] = HORIZONS,
) -> tuple[dict[str, Any], ...]:
    """Geçmişte aynı yönde sinyal üretilen günlerde ileri getiri/MFE/MAE profili."""
    prepared = add_cross_flags(compute_indicators(df, dict(indicators)))
    close = prepared["Close"].astype(float)
    signals: list[str] = []
    n = len(prepared)
    for i in range(n):
        row = prepared.iloc[i]
        prev = prepared.iloc[i - 1] if i > 0 else row
        raw, _ = _score(row, prev, dict(weights), dict(thresholds), has_prev=i > 0)
        sig, _ = score_to_signal(raw, dict(weights), dict(thresholds))
        signals.append(sig)

    wanted = ("BUY", "STRONG_BUY", "AL") if direction == "AL" else ("SELL", "STRONG_SELL", "SAT")
    rows: list[dict[str, Any]] = []
    for h in horizons:
        returns: list[float] = []
        mfes: list[float] = []
        maes: list[float] = []
        for i, sig in enumerate(signals[:-h]):
            if sig not in wanted:
                continue
            entry = float(close.iloc[i])
            if entry <= 0:
                continue
            future = close.iloc[i + 1:i + h + 1]
            if len(future) < h:
                continue
            returns.append((float(future.iloc[-1]) / entry - 1) * 100)
            mfes.append((float(future.max()) / entry - 1) * 100)
            maes.append((float(future.min()) / entry - 1) * 100)

        if not returns:
            rows.append({"ufuk": h, "Ornek": 0, "Kazanma %": 0, "Ortalama %": 0,
                         "Medyan %": 0, "MFE %": 0, "MAE %": 0, "En iyi %": 0, "En kotu %": 0})
            continue
        arr = np.array(returns)
        rows.append({
            "ufuk": h,
            "Ornek": len(arr),
            "Kazanma %": round(float((arr > 0).mean() * 100), 1),
            "Ortalama %": round(float(arr.mean()), 2),
            "Medyan %": round(float(np.median(arr)), 2),
            "MFE %": round(float(np.mean(mfes)), 2),
            "MAE %": round(float(np.mean(maes)), 2),
            "En iyi %": round(float(arr.max()), 2),
            "En kotu %": round(float(arr.min()), 2),
        })
    return tuple(rows)


@st.cache_data(ttl="15m", max_entries=80, show_spinner=False)
def monte_carlo_horizon(
    price: float,
    daily_vol_pct: float,
    stop_pct: float,
    target_pct: float,
    direction: str,
    days: int = 20,
    sims: int = 1200,
    seed: int = 42,
) -> dict[str, Any]:
    """GBM ile fiyat yolları; ufuk bazlı K/Z bantları ve stop/hedef olasılığı."""
    rng = np.random.default_rng(seed)
    vol = max(daily_vol_pct, 0.5) / 100.0
    drift = -0.5 * vol * vol
    steps = rng.normal(drift, vol, size=(sims, days))
    paths = price * np.exp(np.cumsum(steps, axis=1))

    sign = 1 if direction == "AL" else -1
    pnl = (paths / price - 1) * 100 * sign
    med = np.median(pnl, axis=0)
    p05 = np.percentile(pnl, 5, axis=0)
    p95 = np.percentile(pnl, 95, axis=0)

    stop_level = price * (1 - sign * stop_pct)
    target_level = price * (1 + sign * target_pct)
    hit_stop = (paths <= stop_level) if sign == 1 else (paths >= stop_level)
    hit_target = (paths >= target_level) if sign == 1 else (paths <= target_level)
    stop_first = np.zeros(sims, dtype=bool)
    target_first = np.zeros(sims, dtype=bool)
    for d in range(days):
        newly_stop = hit_stop[:, d] & ~stop_first & ~target_first
        newly_target = hit_target[:, d] & ~target_first & ~stop_first
        stop_first |= newly_stop
        target_first |= newly_target

    horizon_rows = []
    for d in (1, 5, 20):
        if d > days:
            continue
        horizon_rows.append({
            "gun": d,
            "Beklenen %": round(float(np.mean(pnl[:, d - 1])), 2),
            "Iyi senaryo %": round(float(p95[d - 1]), 2),
            "Kotu senaryo %": round(float(p05[d - 1]), 2),
            "Kar olasiligi %": round(float((pnl[:, d - 1] > 0).mean() * 100), 1),
        })

    return {
        "median": med.tolist(),
        "p05": p05.tolist(),
        "p95": p95.tolist(),
        "horizons": tuple(horizon_rows),
        "stop_prob": round(float(stop_first.mean() * 100), 1),
        "target_prob": round(float(target_first.mean() * 100), 1),
        "days": days,
    }


def render_explanation(
    symbol: str,
    decision: dict[str, Any],
    regime: dict[str, Any] | None,
    df: pd.DataFrame,
    settings: dict[str, Any],
) -> None:
    st.subheader("Neden bu karar? · Ne kadar K/Z?", divider="gray")

    factors = factor_breakdown(decision, regime)
    with st.container(border=True):
        st.markdown("#### Karar gerekçesi (faktör katkıları)")
        if factors:
            fdf = pd.DataFrame(factors)
            chart = (
                alt.Chart(fdf)
                .mark_bar()
                .encode(
                    x=alt.X("Katkı:Q", title="Karara etkisi (-1 SAT yönü / +1 AL yönü)"),
                    y=alt.Y("Faktör:N", sort="-x", title=None),
                    color=alt.condition(
                        alt.datum.Katkı >= 0, alt.value("#34D399"), alt.value("#F87171")
                    ),
                    tooltip=["Faktör:N", alt.Tooltip("Katkı:Q", format="+.2f"), "Neden:N"],
                )
                .properties(height=max(140, len(fdf) * 30))
            )
            st.altair_chart(chart, alt="AL BEKLE SAT kararına etki eden faktörlerin katkıları")
            for f in factors:
                st.markdown(f"- **{f['Faktör']}** ({f['Katkı']:+.2f}): {f['Neden']}")
        else:
            st.caption("Kararı açıklayan faktör bulunamadı.")

    decision_name = decision.get("decision", "BEKLE")
    direction = "AL" if decision_name == "AL" else "SAT" if decision_name == "SAT" else "BEKLE"

    with st.container(border=True):
        st.markdown("#### Geçmişte benzer sinyallerde ne oldu?")
        st.caption(
            "Aynı yönde sinyal üretilen geçmiş günlerde, girişten sonraki 1/5/20 günde "
            "fiyatın nasıl hareket ettiği (MFE: en iyi an, MAE: en kötü an)."
        )
        if direction == "BEKLE":
            st.info("Karar BEKLE olduğu için benzer AL/SAT sinyali istatistiği üretilmiyor.", icon=":material/info:")
        else:
            stats = analog_stats(
                df, settings["indicators"], settings["signal_weights"],
                settings.get("signal", settings.get("signal_thresholds", {})), direction,
            )
            sdf = pd.DataFrame(stats).rename(columns={
                "ufuk": "Ufuk (gün)", "Ornek": "Örnek", "Kazanma %": "Kazanma %",
                "Ortalama %": "Ort. getiri %", "Medyan %": "Medyan %",
                "MFE %": "MFE %", "MAE %": "MAE %",
                "En iyi %": "En iyi %", "En kotu %": "En kötü %",
            })
            st.dataframe(
                sdf, hide_index=True,
                column_config={
                    "Ort. getiri %": st.column_config.NumberColumn(format="%+.2f"),
                    "Medyan %": st.column_config.NumberColumn(format="%+.2f"),
                    "MFE %": st.column_config.NumberColumn(format="%+.2f"),
                    "MAE %": st.column_config.NumberColumn(format="%+.2f"),
                },
                alt="Benzer sinyallerin 1/5/20 günlük getiri ve MFE MAE profili",
            )
            if sdf.iloc[0]["Örnek"] < 10:
                st.warning("Örnek sayısı az (<10); istatistik güvenilir değil.", icon=":material/warning:")

    with st.container(border=True):
        st.markdown("#### Ne kadar sürede ne kadar K/Z? (Monte Carlo)")
        st.caption(
            "Günlük oynaklıkla 1.200 olası fiyat yolu simüle edilir. Bantlar %5–%95 "
            "arasındaki aralığı gösterir; stop/hedef olasılıkları 20 günlük penceredir."
        )
        if direction == "BEKLE":
            st.info("BEKLE kararında işlem projeksiyonu yapılmaz.", icon=":material/info:")
        else:
            price = float(decision.get("price") or 0)
            # Günlük oynaklık, 5-dakikalık bar oynaklığından değil günlük getirilerden hesaplanır
            daily_vol = float(df["Close"].astype(float).pct_change().std() * 100) if "Close" in df else 2.0
            daily_vol = float(np.nan_to_num(daily_vol, nan=2.0))
            risk = settings["risk"]
            stop_pct = float(risk.get("stop_loss_pct", 0.05))
            target_pct = float(risk.get("take_profit_pct", 0.10))
            mc = monte_carlo_horizon(
                price, daily_vol, stop_pct, target_pct, direction,
                days=20, sims=1200,
            )
            hdf = pd.DataFrame(mc["horizons"]).rename(columns={
                "gun": "Gün", "Beklenen %": "Beklenen K/Z %",
                "Iyi senaryo %": "İyi senaryo %", "Kotu senaryo %": "Kötü senaryo %",
                "Kar olasiligi %": "Kâr olasılığı %",
            })
            st.dataframe(
                hdf, hide_index=True,
                column_config={
                    "Beklenen K/Z %": st.column_config.NumberColumn(format="%+.2f"),
                    "İyi senaryo %": st.column_config.NumberColumn(format="%+.2f"),
                    "Kötü senaryo %": st.column_config.NumberColumn(format="%+.2f"),
                },
                alt="1/5/20 günlük beklenen kâr/zarar ve olasılıklar",
            )
            c1, c2 = st.columns(2)
            c1.metric("Hedefe ulaşma olasılığı", f"%{mc['target_prob']}", icon=":material/flag:")
            c2.metric("Stop'a gelme olasılığı", f"%{mc['stop_prob']}", icon=":material/shield:")

            band = pd.DataFrame({
                "Gün": list(range(1, mc["days"] + 1)),
                "Medyan %": mc["median"],
                "İyi (95%) %": mc["p95"],
                "Kötü (5%) %": mc["p05"],
            })
            base = alt.Chart(band).encode(x=alt.X("Gün:Q", title="İşlem sonrası gün"))
            area = base.mark_area(opacity=0.18, color="#60A5FA").encode(
                y=alt.Y("Kötü (5%) %:Q", title="K/Z %"),
                y2="İyi (95%) %:Q",
            )
            line = base.mark_line(color="#34D399", strokeWidth=2).encode(y=alt.Y("Medyan %:Q"))
            st.altair_chart(
                (area + line).properties(height=220),
                alt="20 günlük beklenen K/Z bandı (medyan ve %5-%95 aralığı)",
            )

    st.caption(
        "Bu projeksiyonlar geçmiş oynaklık ve benzer sinyal istatistiklerine dayanır; "
        "geleceği garanti etmez. Yatırım tavsiyesi değildir."
    )
