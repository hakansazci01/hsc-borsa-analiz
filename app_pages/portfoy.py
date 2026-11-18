"""Portföy ve backtest: kurgusal dağılım planı, getiri karşılaştırması, işlem geçmişi."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui import components, insights
from ui.core import analysis_args, scan_market
from ui.help_texts import h


settings = st.session_state.settings
args = analysis_args(settings)
profile = settings["profile"]

results = list(
    scan_market(
        tuple(settings["symbols"]),
        args["period"], args["interval"], args["indicators"], args["weights"],
        args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
    )
)
plan = insights.allocation_plan(results, profile, settings["risk"])

# ---- Dağılım planı ----
st.subheader("Akıllı portföy planı", divider="gray")
st.caption(
    f"**{profile}** profiline göre, güven eşiğini geçen AL sinyalleri arasından "
    "güven skoruna göre ağırlıklandırılmış kurgusal (paper) dağılım."
)
if plan:
    equity_series = [
        r["backtest"].get("equity_curve", [])
        for r in results if "backtest" in r and r["backtest"].get("equity_curve")
    ]
    equity_spark = (
        [sum(values) / len(equity_series) for values in zip(*equity_series)]
        if equity_series else []
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Önerilen pozisyon", len(plan), border=True,
              icon=":material/leaderboard:", help="Güven eşiğini geçen ve profil limitlerine uyan hisse sayısı.")
    c2.metric("Toplam tahsis", f"{sum(c['allocated'] for c in plan):,.0f}", border=True,
              icon=":material/account_balance:", chart_data=equity_spark or None,
              chart_type="area", help="Önerilen hisselere ayrılan toplam kurgusal tutar.")
    c3.metric("Sermaye", f"{float(settings['risk']['initial_capital']):,.0f}", border=True,
              icon=":material/savings:", help=h("capital"))

    plan_df = pd.DataFrame(plan).rename(
        columns={
            "symbol": "Hisse", "signal": "Sinyal", "confidence": "Güven",
            "allocated": "Tahsis", "weight_pct": "Ağırlık %",
            "stop": "Stop", "target": "Hedef", "amount": "Pozisyon tutarı",
        }
    )
    plan_df = plan_df[["Hisse", "Sinyal", "Güven", "Ağırlık %", "Tahsis", "Stop", "Hedef"]]

    alloc_col, pie_col = st.columns([1.4, 1], gap="medium")
    with alloc_col:
        st.dataframe(
            plan_df,
            hide_index=True,
            column_config={
                "Güven": st.column_config.ProgressColumn("Güven", min_value=0, max_value=100, format="%d", help=h("confidence")),
                "Ağırlık %": st.column_config.NumberColumn("Ağırlık %", format="%.1f", help="Güven skoruna göre hesaplanan portföy ağırlığı."),
                "Tahsis": st.column_config.NumberColumn("Tahsis", format="%,.0f", help="Bu hisseye ayrılan kurgusal tutar."),
                "Stop": st.column_config.NumberColumn("Stop", format="%.2f", help=h("stop_loss")),
                "Hedef": st.column_config.NumberColumn("Hedef", format="%.2f", help=h("take_profit")),
            },
            alt="Risk profiline göre önerilen hisse ağırlıkları ve işlem seviyeleri",
        )
    with pie_col:
        st.echarts_chart(
            {
                "tooltip": {"trigger": "item", "valueFormatter": "compact"},
                "series": [
                    {
                        "type": "pie",
                        "radius": ["42%", "72%"],
                        "avoidLabelOverlap": True,
                        "itemStyle": {"borderRadius": 4, "borderColor": "#0F172A", "borderWidth": 2},
                        "label": {"formatter": "{b}: {d}%", "color": "#E2E8F0"},
                        "data": [{"value": c["allocated"], "name": c["symbol"]} for c in plan],
                    }
                ],
            },
            height=260,
            alt="Önerilen portföyün hisse bazında dağılımı",
        )
else:
    st.info(
        "Seçili profil için şu anda önerilecek bir pozisyon yok. "
        "Ayarlar sayfasından profili değiştirebilir veya sinyallerin güncellenmesini bekleyebilirsiniz.",
        icon=":material/info:",
    )

# ---- Getiri karşılaştırması ----
st.subheader("Backtest karşılaştırması", divider="gray")
components.equity_comparison(results)

rows = []
for r in results:
    if "info" not in r:
        continue
    bt = r["backtest"]
    rows.append({
        "Hisse": r["info"]["symbol"],
        "Toplam getiri %": bt.get("total_return_pct", 0),
        "Yıllık getiri %": bt.get("cagr_pct", 0),
        "Kazanma %": bt.get("win_rate_pct", 0),
        "İşlem": bt.get("total_trades", 0),
        "Maks. düşüş %": bt.get("max_drawdown_pct", 0),
    })
if rows:
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "Toplam getiri %": st.column_config.NumberColumn(format="%.2f", help="Backtest boyunca toplam kurgusal getiri."),
            "Yıllık getiri %": st.column_config.NumberColumn(format="%.2f", help="Yıllıklandırılmış bileşik getiri (CAGR)."),
            "Kazanma %": st.column_config.NumberColumn(format="%.2f", help=h("win_rate")),
            "Maks. düşüş %": st.column_config.NumberColumn(format="%.2f", help=h("max_drawdown")),
        },
        alt="Hisselerin backtest performans metrikleri",
    )

# ---- İşlem geçmişi ----
st.subheader("İşlem geçmişi", divider="gray")
available = [r["info"]["symbol"] for r in results if "info" in r]
if available:
    chosen = st.selectbox("Hisse seçin", available, key="portfolio_trades_symbol", help=h("trades"))
    chosen_res = next(r for r in results if r.get("info", {}).get("symbol") == chosen)
    components.trades_table(chosen_res["backtest"])

st.caption("Tutarlar kurgusal sermaye üzerinden hesaplanmıştır; yatırım tavsiyesi değildir.")
