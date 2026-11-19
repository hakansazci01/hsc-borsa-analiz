"""BIST işlem botu: hisse yazın, gerçek verilerle anında AL/BEKLE/SAT yanıtı verir."""

from __future__ import annotations

import re

import streamlit as st

from ui import assistant
from ui.ai_analyst import build_digest, gemini_commentary
from ui.batch_analysis import analyze_batch, batch_text, render_batch
from ui.bist_universe import load_companies
from ui.components import real_money_warning
from ui.help_texts import h
from ui.live_data import get_live_snapshot
from ui.market_session import status as session_status
from ui.order_ticket import build_ticket, render_ticket
from ui.paper import evaluate as paper_evaluate, open_position
from ui.risk_engine import adjust_decision_for_regime, detect_regime
from ui.signal_display import render_signal_panel
from ui.trade_engine import build_decision


settings = st.session_state.settings
universe = load_companies()

if "bot_messages" not in st.session_state:
    st.session_state.bot_messages = []

st.subheader("BIST işlem botu", divider="gray")
st.caption(
    "Bir BIST hissesi yazın (örn. **THYAO**, **GARAN**, **Aselsan**) veya sorun: "
    "*'Portföyümü incele', 'Neden bu sinyal?', 'Riskim ne?', 'Verinin kaynağı nedir?'*. "
    "Bot gecikmeli veriyle **AL / BEKLE / SAT** sinyalini iki yönlü gerekçesiyle açıklar; "
    "kesinlik, canlı fiyat ve gerçek emir **vermez**."
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

DISCLAIMER_FOOTER = (
    "Bu bir karar destek yorumudur; **yatırım tavsiyesi değildir**. "
    "Gerçek emir gönderilmez, kurgusal işlem yapılır."
)


def _answer_footer(intent: str = "general", symbol: str | None = None) -> None:
    """Her yanıtın altına aynı uyarıyı ve bağlamlı takip önerilerini koyar."""
    st.caption(DISCLAIMER_FOOTER)
    keys = assistant.suggestions(intent, symbol)[:3]
    if keys:
        cols = st.columns(len(keys), gap="small")
        for col, text in zip(cols, keys):
            with col:
                if st.button(
                    text,
                    key=f"bot_follow_{abs(hash(text)) % 100000}_{len(st.session_state.bot_messages)}",
                    use_container_width=True,
                ):
                    st.session_state.bot_next_prompt = text
                    st.rerun()


def _render_answer(answer: str, intent: str = "general", symbol: str | None = None) -> None:
    """Yanıtı tutarlı bir kart olarak gösterir ve bağlamlı takip önerileri sunar."""
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        st.markdown(answer)
        _answer_footer(intent, symbol)
    st.session_state.bot_messages.append({"role": "assistant", "content": answer})


def _intent_answer(intent: str, prompt: str) -> str:
    """Hisse sembolü olmayan, insan odaklı sorulara deterministik yanıt üretir."""
    from ui import performance, smart_guide

    user = st.session_state.user
    last = st.session_state.get("bot_last")

    if intent == "capabilities":
        return (
            assistant.LIMITS_TEXT
            + "\n\nŞunları yapabilirim:\n"
            + "- **AL / BEKLE / SAT** sinyalini gerekçesiyle açıklamak\n"
            + "- Kurgusal portföyündeki **yoğunlaşma ve riski** özetlemek\n"
            + "- Piyasa **rejimini** ve BIST 100'a göre durumu anlatmak\n"
            + "- Verinin **kaynağını ve yaşını** göstermek\n"
            + "- Teknik terimleri sade dille açıklamak\n\n"
            + "Yapamayacağım şeyler: canlı fiyat, yön garantisi, gerçek emir ve yatırım tavsiyesi."
        )

    if intent == "portfolio":
        positions = paper_evaluate(user, settings)
        if not positions:
            return (
                "Kurgusal portföyünde açık pozisyon yok. Bir sinyale dayanarak "
                "**Kurgusal pozisyon aç** düğmesiyle örnek bir pozisyon oluşturabilirsin; "
                "sonra buradan riskini ve yoğunlaşmanı birlikte inceleyebilirim."
            )
        total = sum(float(p.get("pnl_amount", 0) or 0) for p in positions)
        sells = [p for p in positions if p.get("action") == "SAT"]
        concentration: dict[str, float] = {}
        for p in positions:
            symbol_key = str(p.get("symbol", "—"))
            concentration[symbol_key] = concentration.get(symbol_key, 0.0) + abs(float(p.get("pnl_amount", 0) or 0))
        top = sorted(concentration.items(), key=lambda kv: kv[1], reverse=True)[:3]
        summary = performance.summarize(performance.read_records(user))
        return (
            f"**Kurgusal portföyün:** {len(positions)} açık pozisyon, "
            f"açık K/Z **{total:+,.0f} ₺**. "
            + (f"**{len(sells)}** pozisyon için SAT önerisi var. " if sells else "SAT önerisi yok. ")
            + ("En çok hareket eden hisseler: "
               + ", ".join(f"{s} ({v:,.0f} ₺)" for s, v in top) + ". " if top else "")
            + (f"Kapanan {summary['total']} sinyalin net R'i {summary['net_r']:+.2f}R. "
               if summary else "")
            + "\n\nBu bir **portföy özetidir**, işlem önerisi değildir. "
            "Yoğunlaşma tek bir hisse veya sektörde riski artırır."
        )

    if intent == "why":
        if not last:
            return "Önce bir hisse analiz et; sonra 'neden bu sinyal?' diye sorabilirim."
        decision = last["decision"]
        snap = last["snap"]
        regime = last.get("regime") or {}
        action = str(decision.get("decision", "BEKLE"))
        rec = {"action": action, "confidence": decision.get("confidence", 0)}
        info = {
            "signal": "BUY" if action == "AL" else "SELL" if action == "SAT" else "NEUTRAL",
            "score": decision.get("score"),
            "rsi": (snap.get("info") or {}).get("rsi"),
        }
        return assistant.two_sided_rationale(rec, info, {}, regime)

    if intent == "risk":
        risk = settings.get("risk", {})
        if not last:
            return (
                "Riskini değerlendirmek için önce bir hisse analiz etmelisin. "
                f"Genel ayarların: zarar durdurma **%{float(risk.get('stop_loss_pct', 0.05)) * 100:.0f}**, "
                f"işlem başına sermaye **%{float(risk.get('position_size_pct', 0.10)) * 100:.0f}**. "
                "Bunlar kurgusal risk ayarlarıdır, garanti değildir."
            )
        decision = last["decision"]
        return (
            f"**{last['symbol']} için risk çerçevesi:** "
            f"giriş {decision.get('price', 0):,.2f} ₺, "
            f"stop {decision.get('stop') or '—'}, hedef {decision.get('target') or '—'}. "
            f"Stop mesafesi, işlem başına sermayenin %{float(risk.get('position_size_pct', 0.10)) * 100:.0f}'i "
            "ile sınırlı tutuluyor. Unutma: **stop her zaman tam fiyattan gerçekleşmez**; "
            "gecikmeli veri ve boşluklar (gap) bu riski artırır."
        )

    if intent == "suitability":
        profile = settings.get("profile", "Dengeli")
        positions = paper_evaluate(user, settings)
        return (
            f"Risk profilin **{profile}**. Bu bir tavsiye değil, **uyumluluk kontrolüdür**: "
            f"Kurgusal portföyünde {len(positions)} açık pozisyon var. "
            "Tek bir hisseye/portföyün büyük kısmına yoğunlaşmak, belirttiğin profille "
            "uyumsuz olabilir. Profilini Ayarlar sayfasından değiştirebilirsin."
        )

    if intent == "changes":
        regime = smart_guide.market_regime()
        pick = smart_guide.top_pick(settings, regime)
        text = f"Piyasa rejimi: **{regime.get('regime', 'Yatay')}** (güven %{int(regime.get('confidence', 0) or 0)}). "
        if isinstance(pick, dict) and pick.get("plain"):
            text += pick["plain"]
        else:
            text += "İzleme listenizde bugün güven eşiğini geçen net bir alım adayı yok; BEKLE uygun."
        return text + "\n\nBu bilgi gecikmeli veriye dayanır; KAP'tan teyit etmeden işlem kararı verme."

    if intent == "benchmark":
        from ui.benchmark import bist100_benchmark

        bench = bist100_benchmark()
        if not bench:
            return "BIST 100 karşılaştırma verisi şu an alınamadı; veri geldiğinde tekrar sor."
        return (
            f"BIST 100, son dönemde **{float(bench.get('total_return_pct', 0)):+.1f}%** "
            f"değerlendi (kaynak: borsapy endeks, gecikmeli). "
            "Bir hissenin yükselmesi bazen tüm piyasanın yükselmesinden kaynaklanır; "
            "kararı değerlendirirken bu farkı (alfa) göz önünde bulundur."
        )

    if intent == "provenance":
        if not last:
            return "Önce bir hisse analiz et; kaynak ve veri yaşı bilgisini birlikte göstereyim."
        snap = last["snap"]
        info = snap.get("info") or {}
        return (
            f"**Kaynak:** {snap.get('quote_source', '—')} · "
            f"**Kotasyon zamanı:** {info.get('quote_time') or 'belirtilmemiş'} · "
            f"**Seans:** {info.get('session') or '—'}. "
            "Ücretsiz veri akışı ~15 dakika gecikmeli olabilir; kesin fiyat için "
            "KAP veya aracı kurum ekranına bakmalısın."
        )

    return (
        "Sorunu hisse analizi, portföy, risk, gerekçe veya veri kaynağı olarak yönlendirebilirim. "
        "Örnek: 'Portföyümü incele', 'THYAO neden AL?', 'Verinin kaynağı nedir?'"
    )


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
        return (
            f"⚠️ **{symbol}** için güncel veri alınamadı. İnternet bağlantısını ve "
            "seans durumunu kontrol edip birazdan tekrar deneyin. "
            "Bu sırada yorum üretmiyorum; eksik veriyle tahmin yapmak yanıltıcı olur."
        )

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
    "Hisse, portföy, risk veya 'neden?' yazın...", submit_mode="disable", key="bot_chat"
)
chip_prompt = st.session_state.pop("bot_next_prompt", None)
if chip_prompt:
    prompt = chip_prompt

if not st.session_state.bot_messages:
    picked = st.pills(
        "Hızlı analiz", list(SUGGESTIONS.keys()), key="bot_suggestions",
        help="Bu düğmelerden birine basmak hisseyi yazmış sayılır; bot hemen analiz eder.",
    )
    if picked:
        prompt = SUGGESTIONS[picked]

with st.container(horizontal=True, horizontal_alignment="right"):
    if st.button("Sohbeti temizle", icon=":material/delete_sweep:", key="bot_clear_chat"):
        st.session_state.bot_messages = []
        st.session_state.bot_last = None
        st.session_state.bot_batch = []
        st.rerun()

if prompt:
    st.session_state.bot_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    guard = assistant.guard_check(prompt)
    intent = assistant.detect_intent(prompt)
    exact, ambiguous = _detect_symbols(prompt)

    # Güvenlik/kısıt yanıtları: emir, kesinlik, canlı fiyat, tahmin, onay bekleyen sorular
    if guard:
        _render_answer(guard, "general")
        st.stop()

    # Hisse sembolü içermeyen, insan odaklı sorular
    if not exact and intent in (
        "capabilities", "portfolio", "why", "risk", "suitability",
        "changes", "benchmark", "provenance",
    ):
        _render_answer(_intent_answer(intent, prompt), intent)
        st.stop()

    # Yalnızca şirket adı yazıldıysa önce kullanıcıya onaylat (belirsizlik giderimi)
    if not exact and ambiguous:
        st.session_state.pending_symbols = ambiguous
        st.session_state.bot_last = None
        answer = (
            "Şirket adından birden fazla olası hisse buldum. Lütfen yukarıdaki "
            "**Seçim onayı** panelinden doğru sembolleri onaylayın veya düzeltin."
        )
        _render_answer(answer, "general")
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
            _answer_footer("why", exact[0])
        st.session_state.bot_messages.append({"role": "assistant", "content": answer})
        st.rerun()

    symbol = exact[0] if exact else _extract_symbol(prompt)
    with st.chat_message("assistant", avatar=":material/smart_toy:"):
        if symbol:
            with st.status(":shimmer[Canlı veriler toplanıyor...]", type="compact") as status:
                st.caption("WebSocket fiyatı → KAP haberleri → teknik sinyaller → rejim + risk")
                answer = _analyze(symbol)
                if intent == "why" and st.session_state.get("bot_last"):
                    _last = st.session_state.bot_last
                    _d = _last["decision"]
                    _action = str(_d.get("decision", "BEKLE"))
                    _rec = {"action": _action, "confidence": _d.get("confidence", 0)}
                    _info = {
                        "signal": "BUY" if _action == "AL" else "SELL" if _action == "SAT" else "NEUTRAL",
                        "score": _d.get("score"),
                        "rsi": (_last["snap"].get("info") or {}).get("rsi"),
                    }
                    answer = assistant.two_sided_rationale(_rec, _info, {}, _last.get("regime") or {})
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
        _answer_footer("why", symbol)
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
            if text:
                st.session_state.ai_comment = "**Gemini yorumu:**\n\n" + text
            else:
                # Anahtar yoksa/hata varsa boşbir reddetme değil, işe yarar yerel özet.
                _last = st.session_state.bot_last
                _d = _last["decision"]
                _action = str(_d.get("decision", "BEKLE"))
                _rec = {"action": _action, "confidence": _d.get("confidence", 0)}
                _info = {
                    "signal": "BUY" if _action == "AL" else "SELL" if _action == "SAT" else "NEUTRAL",
                    "score": _d.get("score"),
                    "rsi": (_last["snap"].get("info") or {}).get("rsi"),
                }
                st.session_state.ai_comment = (
                    "**Yerel özet (Gemini kapalı veya erişilemez):**\n\n"
                    + assistant.two_sided_rationale(_rec, _info, {}, _last.get("regime") or {})
                    + f"\n\n*Servis durumu: {error}*"
                )
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
