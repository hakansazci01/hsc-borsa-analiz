"""Strateji laboratuvarı: walk-forward doğrulama, parametre duyarlılığı, koruma durumu."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from ui.bist_universe import load_companies, ordered_symbols
from ui.components import real_money_warning
from ui.core import analysis_args, analyze_symbol
from ui.help_texts import h
from ui.scientific import (
    deflated_sharpe, data_quality, pbo_cscv, permutation_test, purged_walk_forward,
)
from ui.validation import grid_trials, parameter_sensitivity, summarize, walk_forward


settings = st.session_state.settings
args = analysis_args(settings)
universe = load_companies()

st.subheader("Strateji laboratuvarı", divider="gray")
st.caption(
    "Sinyal kuralının görülmemiş dönemlerde çalışıp çalışmadığını (walk-forward) ve "
    "ayarlara ne kadar bağlı olduğunu (duyarlılık) ölçer. Bu, kârlılık garantisi değil, "
    "aşırı uyum (overfitting) kontrolüdür."
)
real_money_warning(compact=True)

symbol = st.selectbox(
    "Hisse", ordered_symbols(universe),
    format_func=lambda s: f"{s} · {universe.get(s, s)}",
    key="lab_symbol", help=h("bist_search"),
)

try:
    res = analyze_symbol(
        f"{symbol}.IS" if symbol != "BIST100" and "." not in symbol else symbol,
        args["period"], args["interval"], args["indicators"], args["weights"],
        args["thresholds"], args["risk"], args["backtest_cfg"], args["guards"],
    )
    df = res["df"]
except Exception as exc:
    st.error(f"Veri alınamadı: {exc}", icon=":material/error:")
    st.stop()

# ---- Walk-forward ----
with st.container(border=True):
    st.subheader("Walk-forward doğrulama", divider="gray")
    st.caption(
        "Veri ardışık eğitim/test pencerelerine bölünür. Aynı kural eğitimde ve hiç "
        "görülmemiş test döneminde çalıştırılır; test sonuçları pozitif ve tutarlıysa kural daha güvenilirdir."
    )
    wf = walk_forward(
        df, args["indicators"], args["weights"], args["thresholds"],
        args["risk"], args["backtest_cfg"], args["guards"], windows=4,
    )
    if wf:
        wf_df = pd.DataFrame(wf)
        st.dataframe(wf_df, hide_index=True, alt="Eğitim ve test dönemlerinin karşılaştırması")
        test_returns = [float(r["Test getiri %"]) for r in wf]
        positive = sum(1 for v in test_returns if v > 0)
        c1, c2, c3 = st.columns(3)
        c1.metric("Pozitif test penceresi", f"{positive}/{len(wf)}", help="Kaç test döneminde kural pozitif getiri üretti.")
        c2.metric("Ortalama test getiri", f"{sum(test_returns)/len(test_returns):+.2f}%")
        c3.metric("En kötü test", f"{min(test_returns):+.2f}%")
        if positive == 0:
            st.warning("Hiçbir test penceresinde pozitif getiri yok. Kural bu hisse için görülmemiş dönemlere taşınamıyor.", icon=":material/warning:")
    else:
        st.info("Walk-forward için en az 60 günlük veri gerekir.", icon=":material/info:")

# ---- Parametre duyarlılığı ----
with st.container(border=True):
    st.subheader("Parametre duyarlılığı (aşırı uyum kontrolü)", divider="gray")
    st.caption(
        "AL eşiği ve gösterge ağırlıkları değiştirilerek aynı kural tekrar çalıştırılır. "
        "İyi bir strateji tek bir 'sihirli' ayarda değil, geniş bir platoda pozitif kalır."
    )
    sens = parameter_sensitivity(
        df, args["indicators"], args["weights"], args["thresholds"],
        args["risk"], args["backtest_cfg"], args["guards"],
    )
    if sens:
        sens_df = pd.DataFrame(sens)
        st.dataframe(sens_df, hide_index=True, alt="Farklı eşik ve ağırlıklarda strateji sonuçları")
        pivot = sens_df.pivot(
            index="AL eşiği", columns="Ağırlık çarpanı", values="Getiri %"
        ).reset_index().melt(id_vars="AL eşiği", var_name="Ağırlık", value_name="Getiri")
        heat = (
            alt.Chart(pivot)
            .mark_rect()
            .encode(
                x=alt.X("AL eşiği:O", title="AL eşiği"),
                y=alt.Y("Ağırlık:O", title="Ağırlık çarpanı"),
                color=alt.Color("Getiri:Q", title="Getiri %", scale=alt.Scale(scheme="redyellowgreen", domainMid=0)),
                tooltip=["AL eşiği:O", "Ağırlık:O", alt.Tooltip("Getiri:Q", format=".2f")],
            )
            .properties(height=220)
        )
        st.altair_chart(heat, alt="Parametre ızgarasında getiri dağılımı")
        summary = summarize(sens, "Getiri %")
        st.metric("Pozitif ayar oranı", f"%{summary['positive_pct']}", help="Izgaradaki kaç ayar kombinasyonu pozitif getiri verdi.")
        if summary["stable"]:
            st.success("Sonuçlar geniş bir ayar aralığında pozitif — aşırı uyum riski düşük.", icon=":material/verified:")
        else:
            st.warning(
                f"Pozitif sonuçlar az sayıda ayarda toplanıyor. En iyi ayar: "
                f"AL eşiği {summary['best']['AL eşiği']}, ağırlık ×{summary['best']['Ağırlık çarpanı']} — "
                "bu bir aşırı uyum işareti olabilir.",
                icon=":material/warning:",
            )

# ---- Koruma katmanı ----
with st.container(border=True):
    st.subheader("Koruma katmanı durumu", divider="gray")
    st.caption(
        "Cooldown, stoplossGuard, günlük zarar limiti ve drawdown kademeleri "
        "backtest sırasında aktiftir; kural işlem açılmasını engellediğinde ilgili neden kaydedilir."
    )
    snap = res["backtest"].get("guard_snapshot")
    if snap:
        st.json(snap, expanded=False)
        guard_display = dict(args["guards"] or {})
        st.caption(
            f"Ayarlar: cooldown {guard_display.get('cooldown_bars', 2)} bar · "
            f"stop guard {guard_display.get('stoploss_limit', 3)}/{guard_display.get('stoploss_lookback', 20)} · "
            f"günlük limit %{guard_display.get('daily_loss_cap_pct', 3)} · "
            f"drawdown durma %{guard_display.get('drawdown_halt_pct', 8)}"
        )
    else:
        st.caption("Koruma katmanı bu analizde etkin değil.")

# ---- Bilimsel doğrulama ----
with st.container(border=True):
    st.subheader("Bilimsel doğrulama (quant standartları)", divider="gray")
    st.caption(
        "Bailey & López de Prado yöntemleri: çoklu test düzeltmesi (DSR), "
        "aşırı uyum olasılığı (PBO/CSCV), permütasyon testi ve purge/embargo'lu walk-forward."
    )

    trials = grid_trials(
        df, args["indicators"], args["weights"], args["thresholds"],
        args["risk"], args["backtest_cfg"], args["guards"],
    )
    dsr = deflated_sharpe(list(trials))
    pbo = pbo_cscv(list(trials), slices=8)

    d1, d2 = st.columns(2)
    with d1:
        st.metric("Deflated Sharpe", dsr.get("dsr", "—"), help="Çoklu test düzeltmesinden sonra gerçek edge olasılığı.")
        st.caption(f"Gözlenen SR {dsr.get('observed_sr','—')} · eşik {dsr.get('hurdle_sr','—')} · {dsr.get('n_trials','—')} deneme")
        st.caption(dsr.get("verdict", dsr.get("reason", "")))
    with d2:
        st.metric("PBO (aşırı uyum)", pbo.get("pbo", "—"), help="En iyi in-sample stratejinin out-of-sample'da ortalamanın altında kalma olasılığı.")
        st.caption(f"{pbo.get('combinations','—')} kombinasyon · {pbo.get('slices','—')} dilim · {pbo.get('trials','—')} deneme")
        st.caption(pbo.get("verdict", pbo.get("reason", "")))

    champion = max(trials, key=lambda r: float(r.mean() / r.std(ddof=1)) if r.std(ddof=1) > 0 else 0.0) if trials else None
    if champion is not None:
        perm = permutation_test(champion)
        st.metric("Permütasyon p-değeri", perm.get("p_value", "—"), help="Getiriler rastgele karıştırıldığında bu sonucun çıkma olasılığı.")
        st.caption(perm.get("verdict", perm.get("reason", "")))

    purged = purged_walk_forward(
        df, args["indicators"], args["weights"], args["thresholds"],
        args["risk"], args["backtest_cfg"], args["guards"],
        windows=4, purge_bars=20, embargo_bars=5,
    )
    if purged:
        st.dataframe(
            pd.DataFrame(purged),
            hide_index=True,
            alt="Purge ve embargo uygulanmış walk-forward sonuçları",
        )
        st.caption("Purge: eğitim sonu 20 bar çıkarıldı · Embargo: test başı 5 bar atlandı (etiket sızıntısı önlemi).")

    dq = data_quality(df)
    if dq["ok"]:
        st.success(f"Veri kalitesi geçerli ({dq['rows']} bar).", icon=":material/check_circle:")
    else:
        st.warning("Veri kalitesi uyarıları: " + "; ".join(dq["issues"]), icon=":material/warning:")

