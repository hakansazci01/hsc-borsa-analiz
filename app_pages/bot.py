"""BIST işlem botu: hisse yazın, gerçek verilerle anında AL/BEKLE/SAT yanıtı verir."""

from __future__ import annotations

import re

import streamlit as st

from ui.ai_analyst import build_digest, gemini_commentary
from ui.batch_analysis import analyze_batch, batch_text, render_batch
from ui.bist_universe import load_companies
from ui.components import real_money_warning
from ui.help_texts import h
from ui.live_data import get_live_snapshot
from ui.market_session import status as session_status
from ui.order_ticket import build_ticket, render_ticket
from ui.paper import open_position
from ui.risk_engine import adjust_decision_for_regime, detect_regime
from ui.signal_display import render_signal_panel
from ui.trade_engine import build_decision


settings = st.session_state.settings
universe = load_companies()

if "bot_messages" not in st.session_state:
    st.session_state.bot_messages = []

st.subheader("BIST işlem botu", divider="gray")
st.caption(
    "Bir BIST hissesi yazın (örn. **THYAO**, **GARAN**, **Aselsan**). Bot; canlı fiyatı, "
    "KAP bildirimlerini, 9 zaman dilimini ve piyasa rejimini kullanıp **AL / BEKLE / SAT** "
    "kararını ve gerekçesini anında döndürür. Ücretsiz akış ~15 dk gecikmelidir; emir gönderilmez."
)
real_money_warning(compact=True)

# ---- Toplu analiz paneli (tarayıcıdan gelen seçim veya çoklu sembol) ----
if st.session_state.get("bot_batch"):
    with st.container(border=True, key="batch_panel"):
        with st.container(horizontal=True, horizontal_alignment="right"):
            st.markdown("#### Toplu sinyal analizi")
            st.caption(
                "Hızlı mod: anlık kotasyon + teknik oy dökümü kullanılır (~7 sn / 12 hisse). "
                "Rejim ve KAP detayı için tek hisseyi sohbette yazın."
            )
            if st.button(
                "Yeniden analiz et", icon=":material/refresh:", key="batch_refresh",
                help="Canlı verileri yeniden çekip tüm hisseleri tekrar değerlendirir.",
            ):
                from ui.live_data import get_live_snapshot as _snap
                from ui.risk_engine import detect_regime as _regime

                _snap.clear()
                _regime.clear()
                st.rerun()
            if st.button("Paneli kapat", icon=":material/close:", key="batch_clear"):
                st.session_state.bot_batch = []
                st.rerun()
        batch_results = analyze_batch(st.session_state.bot_batch, settings, progress=True)
        render_batch(batch_results)

# ---- Belirsiz seçimler için onay paneli ----
if st.session_state.get("pending_symbols"):
    with st.container(border=True, key="disambiguation_panel"):
        st.markdown("#### Seçim onayı")
        st.caption(
            "Şirket adından şu hisseleri anladım. Doğruysa onaylayın; değilse sembolleri düzeltin."
        )
        with st.container(horizontal=True):
            for sym in st.session_state.pending_symbols:
                st.badge(sym, color="orange")
        with st.container(horizontal=True):
            if st.button(
                "Onayla ve analiz et", icon=":material/check:", key="confirm_symbols",
                type="primary",
            ):
                st.session_state.bot_batch = list(st.session_state.pending_symbols)[:12]
                st.session_state.pending_symbols = []
                st.rerun()
            if st.button("İptal", icon=":material/close:", key="cancel_symbols"):
                st.session_state.pending_symbols = []
                st.rerun()
        correction = st.text_input(
            "Sembolleri düzelt (virgülle ayırın)", key="correct_symbols",
            help="Örn. THYAO, GARAN, ASELS",
        )
        if st.button("Düzeltilenleri analiz et", icon=":material/send:", key="analyze_corrected"):
            fixed = [s.strip().upper() for s in correction.split(",") if s.strip().upper() in universe]
            if fixed:
                st.session_state.bot_batch = fixed[:12]
                st.session_state.pending_symbols = []
                st.rerun()
            st.warning("Geçerli BIST sembolü bulunamadı.", icon=":material/warning:")

SUGGESTIONS = {
    ":material/query_stats: THYAO analiz et": "THYAO",
    ":material/account_balance: GARAN analiz et": "GARAN",
    ":material/shield: ASELS analiz et": "ASELS",
    ":material/local_shipping: THYAO almalı mıyım?": "THYAO almalı mıyım?",
    ":material/groups: THYAO, GARAN, ASELS karşılaştır": "THYAO, GARAN, ASELS",
}


def _tr_lower(text: str) -> str:
    """Türkçe I/ı ve İ/i dönüşümünü doğru yapan küçültme."""
    return text.replace("I", "ı").replace("İ", "i").lower()


def _extract_symbol(prompt: str) -> str | None:
    text = prompt.strip().upper()
    for token in re.findall(r"[A-Z0-9]{2,10}", text):
        if token in universe and token != "BIST100":
            return token
    lowered = _tr_lower(prompt.strip())
    for ticker, name in universe.items():
        if lowered and lowered in _tr_lower(name) and len(lowered) > 3:
            return ticker
    return None


def _extract_symbols(prompt: str) -> list[str]:
    """Prompt'ta geçen tüm BIST sembollerini sırayla döndürür."""
    tokens = re.findall(r"[A-Z0-9]{2,10}", prompt.strip().upper())
    found = [t for t in tokens if t in universe and t != "BIST100"]
    seen: set[str] = set()
    unique: list[str] = []
    for ticker in found:
        if ticker not in seen:
            seen.add(ticker)
            unique.append(ticker)
    if len(unique) >= 2:
        return unique

    # "THYAO, GARAN ve ASELS" gibi şirket adları / karışık ifadeler
    parts = [p.strip() for p in prompt.replace(" ve ", ",").split(",") if p.strip()]
    for part in parts:
        low = part.lower()
        if len(low) < 3:
            continue
        for ticker, name in universe.items():
            if low in _tr_lower(name) or ticker.lower() in low:
                if ticker not in seen:
                    seen.add(ticker)
                    unique.append(ticker)
                break
    return unique


def _detect_symbols(prompt: str) -> tuple[list[str], list[str]]:
    """(kesin semboller, şirket adından tahmin edilenler) döndürür.

    Kesin ticker'lar doğrudan analiz edilir; ad eşleşmesi belirsiz olduğu için
    kullanıcı onayına sunulur (sohbet sistemlerinde entity disambiguation deseni).
    """
    text = prompt.strip().upper()
    exact = [t for t in re.findall(r"[A-Z0-9]{2,10}", text)
             if t in universe and t != "BIST100"]
    exact = list(dict.fromkeys(exact))

    ambiguous: list[str] = []
    for part in [p.strip() for p in prompt.replace(" ve ", ",").split(",") if p.strip()]:
        low = _tr_lower(part)
        if len(low) < 4 or re.fullmatch(r"[A-Z0-9 ]{2,10}", part.strip().upper()):
            continue
        for ticker, name in universe.items():
            if low in _tr_lower(name) and ticker not in exact and ticker not in ambiguous:
                ambiguous.append(ticker)
                break
    return exact, ambiguous


def _analyze(symbol: str) -> str:
    st.session_state.ai_comment = None
    try:
        snap = get_live_snapshot(symbol)
    except Exception as exc:
        return f"⚠️ **{symbol}** için veri alınamadı: {exc}"

    decision = build_decision(snap, "Dengeli", settings["risk"], 0.25)
    try:
        regime = detect_regime(symbol)
        decision = adjust_decision_for_regime(decision, regime)
    except Exception:
        regime = None

    st.session_state.bot_last = {
        "symbol": symbol, "decision": decision, "snap": snap, "regime": regime,
    }

    info = snap.get("info", {})
    d = decision["decision"]
    lines = [
        f"### {symbol} · {snap.get('name', symbol)}",
        "",
        f"**KARAR: {d}** — güven **%{decision['confidence']}**",
        "",
        f"- Fiyat: **{info.get('price') or 0:,.2f} ₺** "
        f"(günlük {decision['change_pct']:+.2f}%)",
        f"- Kaynak: {snap.get('quote_source', 'borsapy')} · "
        f"Kotasyon: {info.get('quote_time') or '—'} · "
        f"Seans: {info.get('session') or '—'}",
    ]
    if decision.get("regime"):
        lines.append(f"- Piyasa rejimi: **{decision['regime']}**")
    lines += ["", "**Neden?**"]
    if decision["reasons"]:
        for reason in decision["reasons"][:6]:
            icon = "📈" if reason["tone"] == "positive" else "📉" if reason["tone"] == "negative" else "➖"
            lines.append(f"- {icon} **{reason['source']}:** {reason['text']}")
    else:
        lines.append("- Teknik sinyal veya güncel haber bulunamadı; karar nötr tutuldu.")

    if d in ("AL", "SAT"):
        lines += [
            "",
            "**İşlem parametreleri**",
            f"- Giriş: {decision['price']:,.2f} · Stop: {decision['stop']:,.2f} · "
            f"Hedef: {decision['target']:,.2f}",
            f"- Önerilen pozisyon: %{decision['position_pct']} "
            f"(≈{decision['amount']:,.0f} ₺)",
        ]

    lines += [
        "",
        "⚠️ *Bu analiz teknik veriye dayanır, yatırım tavsiyesi değildir. "
        "Gerçek işlem öncesi KAP ve güncel fiyatı kontrol edin.*",
    ]
    return "\n".join(lines)


if st.session_state.get("bot_pending_symbol"):
    pending_symbol = st.session_state.pop("bot_pending_symbol")
    try:
        pending_answer = _analyze(pending_symbol)
        st.session_state.bot_messages.append({"role": "assistant", "content": pending_answer})
    except Exception:
        pass

for message in st.session_state.bot_messages:
    with st.chat_message(message["role"], avatar=":material/smart_toy:" if message["role"] == "assistant" else None):
        st.markdown(message["content"])

st.caption(":material/info: " + h("bot_chat"))
prompt = st.chat_input(
    "Hisse sembolü veya şirket adı yazın...", submit_mode="disable", key="bot_chat"
)

if not st.session_state.bot_messages:
    picked = st.pills(
        "Hızlı analiz", list(SUGGESTIONS.keys()), key="bot_suggestions",
        help="Bu düğmelerden birine basmak hisseyi yazmış sayılır; bot hemen analiz eder.",
    )
    if picked:
        prompt = SUGGESTIONS[picked]

if prompt:
    st.session_state.bot_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    exact, ambiguous = _detect_symbols(prompt)

    # Yalnızca şirket adı yazıldıysa önce kullanıcıya onaylat (belirsizlik giderimi)
    if not exact and ambiguous:
        st.session_state.pending_symbols = ambiguous
        answer = (
            "Şirket adından birden fazla olası hisse buldum. Lütfen yukarıdaki "
            "**Seçim onayı** panelinden doğru sembolleri onaylayın veya düzeltin."
        )
        with st.chat_message("assistant", avatar=":material/smart_toy:"):
            st.markdown(answer)
        st.session_state.bot_messages.append({"role": "assistant", "content": answer})
        st.rerun()

    if len(exact) > 1:
        st.session_state.bot_batch = exact[:12]
        st.session_state.bot_last = None
        with st.chat_message("assistant", avatar=":material/smart_toy:"):
            with st.status(":shimmer[Çoklu analiz yapılıyor...]", type="compact") as status:
                results = analyze_batch(exact[:12], settings, progress=True)
                answer = batch_text(results)
                status.update(label=f"{len(results)} hisse analiz edildi", state="complete")
            st.markdown(answer)
            if ambiguous:
                st.caption(
                    f"Not: Şirket adından **{', '.join(ambiguous)}** da algılandı; "
                    "onay panelinden ekleyebilirsiniz."
                )
        st.session_state.bot_messages.append({"role": "assistant", "content": answer})
        st.rerun()

    symbol = exact[0] if exact else _extract_symbol(prompt)
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        if symbol:
            with st.status(":shimmer[Canlı veriler toplanıyor...]", type="compact") as status:
                st.caption("WebSocket fiyatı → KAP haberleri → teknik sinyaller → rejim + risk")
                answer = _analyze(symbol)
                status.update(label="Analiz tamamlandı", state="complete")
            st.markdown(answer)
        else:
            answer = (
                "Bu ifadede BIST'te kayıtlı bir hisse bulamadım. "
                "Sembol veya şirket adı yazın (örn. THYAO, Garanti, Aselsan; "
                "veya birden fazla: 'THYAO, GARAN, ASELS'). "
                f"Şu anda **{len(universe)}** BIST şirketi tanıyorum."
            )
            st.markdown(answer)
    st.session_state.bot_messages.append({"role": "assistant", "content": answer})

if st.session_state.get("bot_last"):
    last_signal = st.session_state.bot_last
    render_signal_panel(
        last_signal["decision"], last_signal["snap"],
        last_signal["decision"].get("volatility_pct"),
    )

    # Neden AL/BEKLE/SAT + 1/5/20 günlük K/Z projeksiyonu
    try:
        from ui.core import analysis_args, analyze_symbol
        from ui.decision_explain import render_explanation

        args = analysis_args(settings)
        selected = last_signal["symbol"]
        yahoo_symbol = selected if "." in selected else f"{selected}.IS"
        daily = analyze_symbol(
            yahoo_symbol, args["period"], args["interval"], args["indicators"],
            args["weights"], args["thresholds"], args["risk"],
            args["backtest_cfg"], args["guards"],
        )
        render_explanation(
            selected, last_signal["decision"], last_signal["regime"],
            daily["df"], settings,
        )
    except Exception as exc:
        st.caption(f"Gerekçe ve projeksiyon hesaplanamadı: {exc}")

if st.session_state.get("bot_last"):
    with st.expander("Gemini AI yorumu (isteğe bağlı)", icon=":material/auto_awesome:"):
        st.caption(
            "Yorum, yalnızca yukarıdaki somut verilerden üretilir; botun kararını değiştirmez. "
            "API kullanımı dış servise gönderim içerir."
        )
        if st.button("Yorumu oluştur", key="ai_comment_button", help="Gemini'den kısa Türkçe değerlendirme ister."):
            last = st.session_state.bot_last
            digest = build_digest(last["symbol"], last["decision"], last["snap"], last["regime"])
            text, error = gemini_commentary(digest)
            st.session_state.ai_comment = text or error
        if st.session_state.get("ai_comment"):
            st.markdown(st.session_state.ai_comment)

if st.session_state.get("bot_last"):
    with st.expander(
        "Manuel emir taslağı (broker'a elle giriş için)", icon=":material/receipt:"
    ):
        last = st.session_state.bot_last
        ticket = build_ticket(last["decision"], last["snap"], settings["risk"], settings["profile"])
        render_ticket(ticket)
        session = session_status()
        if not session["in_session"]:
            st.caption(f":material/warning: {session['detail']} Kurgusal işlem yalnızca seans içinde açılabilir.")
        if ticket["qty"] > 0 and st.button(
            "Kurgusal pozisyon aç",
            key=f"paper_open_{last['symbol']}",
            icon=":material/add_circle:",
            disabled=not session["in_session"],
            help="Sinyali kurgusal portföyünüze ekler; gerçek emir gönderilmez. Yalnızca seans içinde.",
        ):
            open_position(
                st.session_state.user, last["symbol"], ticket["qty"], ticket["price"],
                ticket["stop"], ticket["target"], ticket["confidence"],
                f"Bot sinyali: {last['decision']['decision']}",
            )
            st.toast(
                f"{last['symbol']} kurgusal pozisyon açıldı. SAT önerilerini Hesabım sayfasında görebilirsiniz.",
                icon=":material/check:",
            )

with st.expander("Bot nasıl çalışıyor?", icon=":material/help:"):
    st.markdown(
        "1. BIST'te kayıtlı tüm şirketler internetten yüklenir "
        f"(**{len(universe)}** şirket).\n"
        "2. Seçilen hisse için TradingView WebSocket'inden canlı kotasyon alınır.\n"
        "3. KAP bildirimleri olumlu/olumsuz sözlükle taranır.\n"
        "4. 9 zaman dilimindeki teknik sinyaller stratejiye göre birleştirilir.\n"
        "5. Piyasa rejimi (trend + oynaklık) kararı uyarlar; risk motoru pozisyonu sınırlar.\n"
        "6. Sonuç AL / BEKLE / SAT olarak gerekçesiyle sunulur."
    )
