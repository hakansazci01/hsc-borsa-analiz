"""
Manuel emir taslağı üretici.

AMAÇ: Sinyali, kullanıcının kendi aracı kurum ekranına *elle* girebileceği
net bir emir bilgisine dönüştürmek. Bu modül:
- hiçbir API'ye emir göndermez,
- otomatik alım/satım yapmaz,
- her taslağı "MANUEL / OTMATİK GÖNDERİM YOK" olarak işaretler.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from ui.help_texts import h


def build_ticket(
    decision: dict[str, Any],
    snap: dict[str, Any],
    risk: dict[str, Any],
    profile: str,
) -> dict[str, Any]:
    side = decision.get("decision", "BEKLE")
    info = snap.get("info", {}) or {}
    price = float(decision.get("price") or info.get("price") or 0)
    capital = float(risk.get("initial_capital", 100000))
    position_pct = float(decision.get("position_pct", 0))
    amount = capital * position_pct / 100.0
    qty = int(amount // price) if price > 0 else 0

    stop = decision.get("stop")
    target = decision.get("target")
    risk_per_share = abs(price - float(stop)) if stop else price * float(risk.get("stop_loss_pct", 0.05))
    risk_amount = qty * risk_per_share
    risk_pct = (risk_amount / capital * 100) if capital else 0.0

    # Kademeli hedefler (TP1 / TP2 / TP3): stop mesafesi 1R kabul edilir.
    # Arrowsticks'in TP + TP2 sunumunun risk odaklı karşılığıdır; emir gönderilmez.
    direction_sign = 1 if side == "AL" else -1
    t1 = price + direction_sign * 1.5 * risk_per_share
    t2 = price + direction_sign * 2.5 * risk_per_share
    t3 = price + direction_sign * 4.0 * risk_per_share

    from ui.market_session import status as session_status

    market = session_status()
    session = market["label"]
    quote_session = str(info.get("session") or "unknown")
    quote_time = info.get("quote_time") or "—"
    confidence = int(decision.get("confidence", 0))
    # Tek yetkili kaynak: İstanbul duvar saatine göre seans durumu
    tradeable = side in ("AL", "SAT") and market["in_session"]

    notes: list[str] = []
    if not market["in_session"]:
        notes.append(f"{market['detail']} Kurgusal emir yalnızca seans içinde açılır.")
    if quote_session not in ("regular", "open") and market["in_session"]:
        notes.append("Kotasyon kaynağı seans dışı veri döndürüyor; fiyatı teyit edin.")
    if confidence < 60:
        notes.append(f"Güven %{confidence} düşük. Bu sinyal tek başına emir sebebi değildir.")
    if decision.get("regime") in ("Yüksek oynaklık", "Düşüş"):
        notes.append(f"Rejim riski: {decision['regime']}. Pozisyon zaten azaltıldı.")
    if not tradeable:
        notes.append("Karar BEKLE: emir taslağı yalnızca bilgilendirme amaçlıdır.")
    notes.append("BIST'te lot büyüklüğünü (genelde 100 adet) ve minimum emir miktarını brokerınızdan doğrulayın.")
    if 0 < qty < 100:
        notes.append(f"Hesaplanan {qty} adet bir lotun altındadır; broker'da bu miktarda emir geçmeyebilir.")
    notes.append("Bu taslak yatırım tavsiyesi değildir; emir sizin sorumluluğunuzdadır.")

    lines = [
        "=== MANUEL EMİR TASLAĞI — OTOMATİK GÖNDERİM YOK ===",
        f"Oluşturma: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        f"Sembol      : {snap.get('symbol', '—')} ({snap.get('name', '')})",
        f"Karar       : {side}",
        f"Emir tipi   : Piyasa / Limit (broker'da siz seçin)",
        f"Hesaplanan fiyat : {price:,.2f} ₺",
        f"Adet        : {qty} (lot büyüklüğünü broker'dan doğrulayın)",
        f"Tahmini tutar: {amount:,.2f} ₺",
        f"Stop        : {stop if stop else '—'}",
        f"Hedef       : {target if target else '—'}",
        f"Kademeli hedefler (1R = stop mesafesi):",
        f"  TP1 (1.5R) : {t1:,.2f} ₺",
        f"  TP2 (2.5R) : {t2:,.2f} ₺",
        f"  TP3 (4.0R) : {t3:,.2f} ₺",
        f" Risk       : {risk_pct:.2f}% sermaye / {risk_amount:,.2f} ₺",
        f"Profil      : {profile}",
        f"Güven       : %{confidence}",
        f"Veri        : {snap.get('quote_source', '—')} · Kotasyon: {quote_time}",
        "",
        "KONTROL NOTLARI:",
    ]
    lines += [f"- {n}" for n in notes]
    lines += ["", "Bu belge otomatik emir değildir. Aracı kuruma elle giriş için referanstır."]

    return {
        "symbol": snap.get("symbol"),
        "name": snap.get("name"),
        "side": side,
        "price": price,
        "qty": qty,
        "amount": amount,
        "stop": stop,
        "target": target,
        "t1": round(t1, 4),
        "t2": round(t2, 4),
        "t3": round(t3, 4),
        "risk_per_share": round(risk_per_share, 4),
        "risk_pct": round(risk_pct, 2),
        "confidence": confidence,
        "session": session,
        "quote_time": quote_time,
        "notes": notes,
        "text": "\n".join(lines),
        "tradeable": tradeable and session in ("regular", "open") and confidence >= 60,
    }


def render_ticket(ticket: dict[str, Any]) -> None:
    """Taslağı arayüzde gösterir; kopyalanabilir metin ve CSV indirme sunar."""
    st.warning(
        "Bu bir **manuel emir taslağıdır**. Sistem emir göndermez; alım/satımı yalnızca "
        "kendi aracı kurum ekranınızdan siz yaparsınız.",
        icon=":material/warning:",
        title="Otomatik emir yok",
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sembol", ticket["symbol"] or "—", help=h("bist_search"))
    c2.metric("Yön", ticket["side"], help=h("signal"))
    c3.metric("Adet", ticket["qty"], help="Hesaplanan kurgusal adet; broker'da lot ve likiditeyi kontrol edin.")
    c4.metric("Risk", f"%{ticket['risk_pct']}", help="Bu işlemde sermayenin ne kadarının riske girdiği.")

    st.code(ticket["text"], language="text")

    with st.expander("Kademeli kâr hedefleri (TP1 / TP2 / TP3)", icon=":material/flag:"):
        st.caption(
            "Stop mesafesi 1R kabul edilerek hesaplanır. Bu seviyeler referanstır; "
            "pozisyonu kademeli kapatıp kapatmamak tamamen sizin kararınızdır."
        )
        st.markdown(
            f"- **TP1 · 1.5R:** {ticket['t1']:,.2f} ₺  \n"
            f"- **TP2 · 2.5R:** {ticket['t2']:,.2f} ₺  \n"
            f"- **TP3 · 4.0R:** {ticket['t3']:,.2f} ₺"
        )

    import pandas as pd

    csv = pd.DataFrame([{
        "Sembol": ticket["symbol"], "Karar": ticket["side"], "Fiyat": ticket["price"],
        "Adet": ticket["qty"], "Tutar": ticket["amount"], "Stop": ticket["stop"],
        "Hedef": ticket["target"], "TP1 (1.5R)": ticket["t1"], "TP2 (2.5R)": ticket["t2"],
        "TP3 (4R)": ticket["t3"], "Risk %": ticket["risk_pct"],
        "Güven": ticket["confidence"], "Kotasyon": ticket["quote_time"],
    }]).to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        "Taslağı CSV indir", data=csv, file_name=f"emir_taslagi_{ticket['symbol']}.csv",
        mime="text/csv", icon=":material/download:", key=f"ticket_dl_{ticket['symbol']}",
        help="Taslağı kendi kayıtlarınız için indirir; hiçbir yere göndermez.",
    )

    for note in ticket["notes"]:
        st.caption(f"- {note}")
