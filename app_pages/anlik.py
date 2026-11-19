"""Anlık işlem terminali: ŞİMDİ AL / BEKLE (tahmini süre) / ŞİMDİ SAT."""

from __future__ import annotations

import altair as alt
import streamlit as st

from ui import audit_log, data_freshness, format_tr as ftr, notify, paper, trust_gate
from ui.bist_universe import load_companies, ordered_symbols
from ui.components import real_money_warning
from ui.help_texts import h
from ui.intraday import intraday_signal


st.html(
    """
<style>
@keyframes ithIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:none} }
@keyframes ithBeat { 0%,100%{opacity:1} 50%{opacity:.35} }
.ith-verdict {
  animation: ithIn .38s cubic-bezier(.25,1,.5,1) both;
  border-radius: 18px; padding: 20px 22px; border-left: 7px solid;
  margin-bottom: 14px; box-shadow: 0 10px 30px rgba(2,6,23,.35);
}
.ith-buy { border-color:#34D399; background:linear-gradient(120deg,rgba(16,185,129,.18),rgba(15,23,42,.9)); }
.ith-wait{ border-color:#FBBF24; background:linear-gradient(120deg,rgba(245,158,11,.16),rgba(15,23,42,.9)); }
.ith-sell{ border-color:#F87171; background:linear-gradient(120deg,rgba(244,63,94,.18),rgba(15,23,42,.9)); }
.ith-big { font-size: 31px; font-weight: 850; line-height: 1.2; }
.ith-sub { color:#CBD5E1; font-size:13.5px; margin-top:6px; }
.ith-meta { color:#94A3B8; font-size:12px; margin-top:8px; }
.ith-dot { display:inline-block; width:8px;height:8px;border-radius:50%;background:#34D399;margin-right:6px;animation:ithBeat 2s ease-in-out infinite; }
.ith-alert {
  animation: ithIn .35s ease both; border:1px solid rgba(244,63,94,.5);
  border-radius:12px; padding:11px 14px; background:rgba(244,63,94,.12); color:#FECACA;
  font-size:13px; font-weight:700; margin:6px 0;
}
@media (prefers-reduced-motion: reduce){ .ith-verdict,.ith-alert,.ith-dot{animation:none!important} }
</style>
"""
)

st.subheader("Anlık işlem terminali", divider="gray")
st.caption(
    "Seans içinde 1 dakikalık canlı mumlar 5m/15m'e örneklenir. EMA9/20, VWAP, RSI7, "
    "hacim ve üst zaman onayı tek tek değerlendirilir. Karar nettir: **ŞİMDİ AL**, "
    "**BEKLE (yaklaşık kaç dakika)** veya **ŞİMDİ SAT**. Koşullar uymuyorsa uydurma sinyal yoktur."
)
real_money_warning(compact=True)

universe = load_companies()
user = st.session_state.user
settings = st.session_state.settings

with st.container(horizontal=True):
    symbol = st.selectbox(
        "Hisse", ordered_symbols(universe),
        format_func=lambda s: f"{s} · {universe.get(s, s)}",
        key="intraday_symbol", help=h("bist_search"),
    )
    alerts_on = st.toggle(
        "Karar değişince uyarı gönder",
        value=True, key="ith_alerts_on",
        help="ntfy / Telegram / e-posta kanalları açıksa tek seferlik bildirim gider (gecikmeli veri).",
    )


@st.fragment(run_every="15s")
def _render() -> None:
    result = intraday_signal(symbol, settings)
    if not result:
        st.warning(
            "Canlı mum verisi alınamadı. Seans dışında olabilir veya bağlantı yok; "
            "bu sırada işlem önerisi üretmiyorum.",
            icon=":material/warning:",
        )
        return

    snap = data_freshness.snapshot(symbol)
    gate = trust_gate.evaluate(
        symbol,
        {"decision": result["decision"], "confidence": result["confidence"]},
        snap, settings,
    )
    gated = trust_gate.apply_gate(
        {"decision": result["decision"], "confidence": result["confidence"]}, gate
    )
    decision = str(gated["decision"])
    price = float(result["price"])
    confidence = int(gated["confidence"])
    tone = {"AL": "buy", "BEKLE": "wait", "SAT": "sell"}[decision]
    headline = {"AL": "ŞİMDİ AL", "BEKLE": "BEKLE", "SAT": "ŞİMDİ SAT"}[decision]

    # Değişim bildirimi (aynı karar tekrar gönderilmez)
    last_key = "ith_last_decision"
    previous = st.session_state.get(last_key)
    if previous != decision:
        if previous is not None and alerts_on:
            timing = (
                f"Tahmini bekleme ~{result['wait_minutes']} dk"
                if result.get("wait_minutes") else "Koşullar değişti"
            )
            notify.send_notification(
                f"HSC Anlık İşlem · {symbol}: {previous} → {decision}\n"
                f"Fiyat {ftr.money(price)} · {timing}\n"
                "Gecikmeli veri · yatırım tavsiyesi değildir · gerçek emir yok.",
                settings,
            )
        st.session_state[last_key] = decision

    trust_gate.render(gate)

    if result.get("wait_low") and result.get("wait_high"):
        low, high = result["wait_low"], result["wait_high"]
        wait_text = (
            f"Yaklaşık **{low} dakika** bekleyin" if low == high
            else f"Yaklaşık **{low}–{high} dakika** bekleyin"
        )
        if high > result.get("remaining_minutes", 999):
            wait_text += " · seans kapanışına kadar oluşmayabilir"
    else:
        wait_text = "Tetikleyici koşullar yaklaşana kadar bekleyin"
    hold_text = (
        f"Hedefe ulaşım (oynaklığa göre) yaklaşık **{result['hold_minutes']} dk**"
        if result.get("hold_minutes") else "Hedef süresi tahmin edilemedi"
    )
    timing_line = wait_text if decision == "BEKLE" else hold_text

    st.html(
        f'<div class="ith-verdict ith-{tone}">'
        f'<div class="ith-big">{symbol} · {headline}</div>'
        f'<div class="ith-sub"><span class="ith-dot"></span>{timing_line} · '
        f'güven %{confidence} · fiyat {ftr.money(price)}</div>'
        f'<div class="ith-meta">En yakın tetikleyici: {result.get("closest_trigger") or "—"} · '
        f'son güncelleme {result["time"]} · {result.get("phase", result["session"])}</div>'
        f"</div>"
    )
    if decision == "BEKLE":
        st.caption(
            "Bekleme aralığı; fiyatın tetikleyici seviyeye uzaklığı ve son dakikalık oynaklık "
            "kullanılarak hesaplanan **yaklaşık** bir tahmindir, garanti değildir. "
            "1 dakikalık mum hâlâ oluşuyor olabilir; son 5m/15m mum kapanmadan koşullar değişebilir."
        )

    audit_log.append(user, "ANLIK_KARAR", {
        "symbol": symbol,
        "decision": decision,
        "gate": gate["level"],
        "source": gate["source"],
        "idempotency_key": f"ith|{symbol}|{decision}|{gate['decision_id']}",
    })

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fiyat", ftr.money(price))
    m2.metric("Stop", ftr.money(result["stop"]) if result["stop"] else "—")
    m3.metric("Hedef", ftr.money(result["target"]) if result["target"] else "—")
    m4.metric("Güven", f"%{confidence}")

    # Açık kurgusal pozisyonlar ve SAT uyarıları
    positions = paper.evaluate(user, settings)
    sell_alerts = [p for p in positions if p.get("action") == "SAT"]
    if sell_alerts:
        for p in sell_alerts:
            st.html(
                f'<div class="ith-alert">SAT UYARISI · {p["symbol"]} · '
                f'K/Z {ftr.pct(p.get("pnl_pct", 0), sign=True)} · '
                f'{" / ".join(p.get("reasons", [])[:2])}</div>'
            )

    c1, c2 = st.columns([1, 1.25], gap="medium")
    with c1:
        with st.container(border=True):
            st.subheader("Tetikleyici durumu", divider="gray")
            for check in result["checks"]:
                icon = ":material/check_circle:" if check["Geçti"] else ":material/radio_button_unchecked:"
                st.markdown(f"- {icon} **{check['Kontrol']}:** {check['Detay']}")
            st.caption(f"Dakikadaki tipik hareket (ATR/5): {result['per_minute_move']:.2f} ₺")

            if st.button(
                "Kurgusal pozisyon aç",
                icon=":material/add_circle:",
                key="intraday_open",
                disabled=decision == "BEKLE" or result["session"] != "Seans açık",
                help="Yalnızca seans içinde ve yönlü sinyalde; gerçek emir gönderilmez.",
            ):
                risk = settings["risk"]
                qty = float(risk["initial_capital"]) * float(risk["position_size_pct"]) / price
                paper.open_position(
                    user, symbol, round(qty, 2), price,
                    result["stop"], result["target"], confidence,
                    f"Anlık terminal: {decision}",
                )
                st.toast(f"{symbol} kurgusal pozisyon açıldı.", icon=":material/check:")
    with c2:
        with st.container(border=True):
            st.subheader("5 dakikalık canlı grafik", divider="gray")
            d = result["m5"].tail(80).reset_index()
            base = alt.Chart(d).encode(x=alt.X("Tarih:T", title=None))
            vol = base.mark_bar(opacity=0.22, color="#94A3B8").encode(y=alt.Y("Volume:Q", title="Hacim"))
            price_line = base.mark_line(color="#E2E8F0", strokeWidth=1.6).encode(y=alt.Y("Close:Q", title="Fiyat"))
            ema9 = base.mark_line(color="#34D399", strokeWidth=1.2).encode(y=alt.Y("EMA9:Q"))
            ema20 = base.mark_line(color="#FBBF24", strokeWidth=1.2).encode(y=alt.Y("EMA20:Q"))
            vwap = base.mark_line(color="#60A5FA", strokeWidth=1.2, strokeDash=[4, 3]).encode(y=alt.Y("VWAP:Q"))
            st.altair_chart(
                (vol + price_line + ema9 + ema20 + vwap).properties(height=270).interactive(),
                alt=f"{symbol} 5 dakikalık fiyat, EMA9/20 ve VWAP",
            )
            st.caption("Yeşil EMA9 · sarı EMA20 · kesikli mavi VWAP · gri hacim")


_render()
