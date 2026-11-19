"""Sinyal performansı: şeffaf sonuç defteri, R çarpanı ve kümülatif eğri."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from ui import performance
from ui.components import real_money_warning
from ui.help_texts import h


st.subheader("Sinyal performansı — şeffaf sonuç defteri", divider="gray")
st.caption(
    "Kapanan **her** kurgusal sinyal giriş, stop, hedef, çıkış, R çarpanı ve gerekçesiyle "
    "kaydedilir. Kazananlar ve kaybedenler aynı yöntemle hesaplanır; gizlenen veya sonradan "
    "seçilen sonuç yoktur. Bu, sinyallerin gerçekten işe yarayıp yaramadığını görmenin en dürüst yoludur."
)
real_money_warning(compact=True)

user = st.session_state.user
records = performance.read_records(user)
summary = performance.summarize(records)

if not summary:
    st.info(
        "Henüz kapanan kurgusal sinyal yok. Bir sinyale dayanarak kurgusal pozisyon açıp "
        "**Hesabım** sayfasından kapattığınızda sonucu burada göreceksiniz.",
        icon=":material/info:",
    )
    st.stop()

# ---- Maliyet modu (komisyon + spread + kayma) ----
use_costs = st.toggle(
    "Maliyetleri dahil et (komisyon + spread + kayma)",
    value=True, key="perf_cost_mode",
    help=h("journal_costs"),
)
costly = use_costs and bool(summary.get("costs_applied"))
if use_costs and not summary.get("costs_applied"):
    st.caption("Bu kayıtlar maliyet alanı olmadan oluşturulmuş; maliyetli sonuç brüt ile aynı.")

# ---- Özet KPI'lar ----
def _pf(value: float) -> str:
    return "∞" if value == float("inf") else f"{value:.2f}"


with st.container(horizontal=True, wrap=True):
    st.metric("Kapanan sinyal", summary["total"], border=True,
              icon=":material/leaderboard:", help=h("signal_ledger"))
    st.metric("Kazanma oranı",
              f"%{summary['win_rate_after_costs_pct'] if costly else summary['win_rate_pct']}",
              border=True, icon=":material/emoji_events:", help=h("win_rate"))
    st.metric("Net R",
              f"{summary['net_r_after_costs'] if costly else summary['net_r']:+.2f}R",
              border=True, icon=":material/trending_up:", help=h("net_r"))
    st.metric("Ortalama R",
              f"{summary['avg_r_after_costs'] if costly else summary['avg_r']:+.3f}R",
              border=True, icon=":material/equalizer:", help=h("r_multiple"))
    st.metric("Kâr faktörü",
              _pf(summary["profit_factor_after_costs"] if costly else summary["profit_factor"]),
              border=True, help=h("profit_factor"))
    st.metric("Maks. düşüş",
              f"{summary['max_drawdown_after_costs_r'] if costly else summary['max_drawdown_r']:.2f}R",
              border=True, help=h("max_drawdown"))

st.caption(
    f"**{summary['wins']} kâr / {summary['losses']} zarar / {summary['breakeven']} başa baş** · "
    f"Beklenti **{summary['expectancy_r']:+.3f}R**/sinyal · "
    f"Kazanma/kayıp oranı **{summary['payoff']:.2f}** · "
    f"En iyi **{summary['best_r']:+.2f}R** / en kötü **{summary['worst_r']:+.2f}R** · "
    f"Seri **{summary['current_streak']:+d}** "
    f"(en uzun kâr {summary['best_win_streak']}, zarar {summary['best_loss_streak']})"
)
if costly:
    st.caption(f"Toplam varsayımsal işlem maliyeti: **{summary['total_costs']:,.2f} ₺** · "
               f"Maliyet sonrası kazanma oranı **%{summary['win_rate_after_costs_pct']}** · "
               f"Maliyet sonrası kâr faktörü **{_pf(summary['profit_factor_after_costs'])}**")

# ---- Kümülatif R eğrisi ve drawdown ----
curve = pd.DataFrame(summary["curve"])
c1, c2 = st.columns([2, 1], gap="medium")
with c1:
    with st.container(border=True):
        st.subheader("Kümülatif sonuç (R)", divider="gray")
        base = alt.Chart(curve).encode(
            x=alt.X("no:Q", title="Kapanan sinyal sayısı"),
            tooltip=[
                alt.Tooltip("no:Q", title="Sinyal no"),
                alt.Tooltip("sembol:N", title="Hisse"),
                alt.Tooltip("kumulatif_r:Q", title="Kümülatif R", format="+.2f"),
                alt.Tooltip("zaman:N", title="Zaman"),
            ],
        )
        area = base.mark_area(opacity=0.18, color="#34D399").encode(
            y=alt.Y("kumulatif_r:Q", title="Kümülatif R")
        )
        line = base.mark_line(color="#34D399", strokeWidth=2).encode(y=alt.Y("kumulatif_r:Q"))
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(
            color="#94A3B8", strokeDash=[4, 4]
        ).encode(y="y:Q")
        st.altair_chart(
            (area + line + zero).properties(height=280),
            alt="Her kapanan sinyalden sonra kümülatif R çarpanı",
        )
        st.caption("Yükselen çizgi toplam R kazancı; düşüşler seri kayıpları gösterir.")
with c2:
    with st.container(border=True):
        st.subheader("Zirveden düşüş (R)", divider="gray")
        dd = alt.Chart(curve).encode(
            x=alt.X("no:Q", title="Sinyal no"),
            y=alt.Y("dusus:Q", title="Düşüş (R)"),
            tooltip=[alt.Tooltip("no:Q", title="Sinyal no"),
                     alt.Tooltip("dusus:Q", title="Düşüş (R)", format=".2f")],
        ).mark_area(opacity=0.7, color="#F87171")
        st.altair_chart(dd.properties(height=280), alt="Kümülatif R zirvesinden düşüş (drawdown)")
        st.caption(f"En derin düşüş: **{summary['max_drawdown_r']:.2f}R**")

# ---- Tüm sonuçlar (kayıplar dahil) ----
with st.container(border=True):
    st.subheader("Tüm kapanan sinyaller", divider="gray")
    st.caption("Eskiye doğru sıralanır. Kaybettiren işlemler de aynı tabloda, aynı ölçümle yer alır.")

    rows = []
    for rec in reversed(records):
        rows.append({
            "Tarih": rec.get("time", ""),
            "Hisse": rec.get("symbol", ""),
            "Yön": rec.get("direction", "AL"),
            "Giriş": rec.get("entry"),
            "Stop": rec.get("stop"),
            "Hedef": rec.get("target"),
            "Çıkış": rec.get("exit"),
            "R": rec.get("r_multiple"),
            "Net R": rec.get("net_r_multiple", rec.get("r_multiple")),
            "Maliyet ₺": rec.get("cost_amount", 0),
            "K/Z %": rec.get("pnl_pct"),
            "Güven": rec.get("confidence"),
            "Sonuç": rec.get("outcome", "—"),
            "Çıkış nedeni": rec.get("exit_reason", ""),
            "Giriş sinyali": rec.get("entry_signal", ""),
        })
    table = pd.DataFrame(rows)

    def _color(value: object) -> str:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if value > 0:
                return "background-color: #065F46; color: white; font-weight: 600;"
            if value < 0:
                return "background-color: #991B1B; color: white; font-weight: 600;"
            return ""
        text = str(value)
        if "KÂR" in text or text.startswith("+"):
            return "background-color: #065F46; color: white; font-weight: 600;"
        if "ZARAR" in text or text.startswith("-"):
            return "background-color: #991B1B; color: white; font-weight: 600;"
        return ""

    shown = table if use_costs else table.drop(columns=["Net R", "Maliyet ₺"])
    color_cols = ["Sonuç", "R"] + (["Net R"] if use_costs else [])
    styled = shown.style.map(_color, subset=color_cols)
    st.dataframe(
        styled,
        hide_index=True,
        column_config={
            "Tarih": st.column_config.TextColumn("Tarih", width="medium"),
            "Hisse": st.column_config.TextColumn("Hisse", width="small"),
            "Yön": st.column_config.TextColumn("Yön", width="small"),
            "Giriş": st.column_config.NumberColumn("Giriş", format="%.2f"),
            "Stop": st.column_config.NumberColumn("Stop", format="%.2f"),
            "Hedef": st.column_config.NumberColumn("Hedef", format="%.2f"),
            "Çıkış": st.column_config.NumberColumn("Çıkış", format="%.2f"),
            "R": st.column_config.NumberColumn("R", format="%+.2f", help=h("r_multiple")),
            "K/Z %": st.column_config.NumberColumn("K/Z %", format="%+.2f"),
            "Güven": st.column_config.ProgressColumn("Güven", min_value=0, max_value=100, format="%d"),
            "Sonuç": st.column_config.TextColumn("Sonuç", width="small"),
            "Çıkış nedeni": st.column_config.TextColumn("Çıkış nedeni", width="medium"),
            "Giriş sinyali": st.column_config.TextColumn("Giriş sinyali", width="medium"),
        },
        alt="Kapanan tüm kurgusal sinyallerin sonuç defteri",
    )
    st.download_button(
        "Defteri CSV indir",
        data=table.to_csv(index=False).encode("utf-8-sig"),
        file_name="sinyal_performans.csv",
        mime="text/csv",
        icon=":material/download:",
    )

# ---- Hisse / yön dökümü ----
b1, b2 = st.columns(2, gap="medium")
with b1:
    st.subheader("Hisse bazında", divider="gray")
    st.dataframe(
        pd.DataFrame(performance.breakdown(records, "symbol")),
        hide_index=True,
        column_config={
            "symbol": "Hisse",
            "Sinyal": st.column_config.NumberColumn("Sinyal", format="%d"),
            "Kazanma %": st.column_config.NumberColumn("Kazanma %", format="%.1f"),
            "Net R": st.column_config.NumberColumn("Net R", format="%+.2f"),
            "Ort. R": st.column_config.NumberColumn("Ort. R", format="%+.3f"),
        },
        alt="Hisse bazında sinyal performansı",
    )
with b2:
    st.subheader("Yön bazında", divider="gray")
    st.dataframe(
        pd.DataFrame(performance.breakdown(records, "direction")),
        hide_index=True,
        column_config={
            "direction": "Yön",
            "Sinyal": st.column_config.NumberColumn("Sinyal", format="%d"),
            "Kazanma %": st.column_config.NumberColumn("Kazanma %", format="%.1f"),
            "Net R": st.column_config.NumberColumn("Net R", format="%+.2f"),
            "Ort. R": st.column_config.NumberColumn("Ort. R", format="%+.3f"),
        },
        alt="Yön bazında sinyal performansı",
    )

with st.expander("R çarpanı ve bu defter nasıl hesaplanıyor?", icon=":material/help:"):
    st.markdown(
        "**R çarpanı**, işlemde alınan riske (stop mesafesine) göre ölçülen kâr/zarardır. "
        "Giriş 100 ₺, stop 95 ₺, çıkış 110 ₺ ise risk 5 ₺, kâr 10 ₺ olduğundan sonuç **+2R**'dır. "
        "Stop mesafesi geçerli yoksa ayarlardaki zarar-durdurma yüzdesi kullanılır ve kayıtta "
        "hangi yöntemin uygulandığı belirtilir. Bu sayede farklı fiyat ve oynaklıktaki hisseler "
        "adil biçimde karşılaştırılabilir."
    )
    st.markdown(
        "**Kâr faktörü** toplam kârın toplam zarara oranıdır (1 üzeri kârlı). "
        "**Beklenti** her sinyalde ortalama kaç R kazanıldığını gösterir. "
        "**Maksimum düşüş** kümülatif R zirvesinden görülen en büyük gerilemedir."
    )
    st.warning(
        "Bu defter kurgusal sinyallerin kaydıdır. Spread, komisyon, swap ve kayma (slippage) "
        "dahil **değildir**; canlı koşullarda sonuçlar farklı olabilir. Geçmiş performans "
        "gelecek sonuçların güvenilir göstergesi değildir. Kazanma oranı tek başına yeterli "
        "değildir; kâr faktörü ve beklentiyle birlikte okunmalıdır.",
        icon=":material/warning:",
    )
