"""
Kullanıcı tanımlı fiyat seviyesi alarmları (kurgusal / bilgilendirme amaçlı).

Platformlardaki "fiyat X üzerine çıkarsa haber ver" özelliğinin paper-only
karşılığıdır. Gerçek emir vermez; yalnızca gecikmeli veriyle koşul gerçekleştiğinde
mevcut bildirim kanallarından tek seferlik uyarı gönderir.

Kayıt: users/<kullanici>/price_alerts.json (tek kullanıcı, yerel).
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui import audit_log, auth, notify


FILE = "price_alerts.json"


def _path(username: str):
    return auth.user_dir(username) / FILE


def load(username: str) -> list[dict[str, Any]]:
    data = auth.read_json(_path(username), [])
    return data if isinstance(data, list) else []


def save(username: str, rules: list[dict[str, Any]]) -> None:
    auth.write_json(_path(username), rules[-50:])


def add(username: str, symbol: str, direction: str, price: float, note: str = "") -> bool:
    rules = load(username)
    rule = {
        "id": f"{symbol}|{direction}|{price}|{int(auth._now().__hash__())}",
        "symbol": symbol.upper(),
        "direction": "above" if direction == "above" else "below",
        "price": round(float(price), 4),
        "note": str(note)[:200],
        "created": auth._now(),
        "triggered": False,
        "triggered_at": None,
    }
    rules.append(rule)
    save(username, rules)
    audit_log.append(username, "FIYAT_ALARMI_KURULDU", {
        "symbol": symbol, "decision": direction, "source": "kullanici",
        "idempotency_key": f"alertadd|{rule['id']}",
    })
    return True


def remove(username: str, rule_id: str) -> None:
    save(username, [r for r in load(username) if r.get("id") != rule_id])


def check(
    username: str,
    quotes: dict[str, float],
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Aktif kuralları güncel fiyatlarla kontrol eder, tetiklenenleri döndürür."""
    rules = load(username)
    triggered: list[dict[str, Any]] = []
    changed = False
    for rule in rules:
        if rule.get("triggered"):
            continue
        symbol = str(rule.get("symbol", "")).upper()
        price = quotes.get(symbol)
        if price is None or not isinstance(price, (int, float)):
            continue
        level = float(rule.get("price", 0))
        hit = price >= level if rule.get("direction") == "above" else price <= level
        if not hit:
            continue
        rule["triggered"] = True
        rule["triggered_at"] = auth._now()
        rule["last_price"] = float(price)
        changed = True
        triggered.append(dict(rule))
        audit_log.append(username, "FIYAT_ALARMI_TETIKLENDI", {
            "symbol": symbol,
            "decision": rule["direction"],
            "source": "gecikmeli kotasyon",
            "idempotency_key": f"alertfire|{rule.get('id')}",
        })

    if changed:
        save(username, rules)
        if triggered:
            lines = [
                "HSC Fiyat Alarmı (bilgilendirmedir, işlem sinyali değildir)",
                "",
            ]
            for item in triggered:
                lines.append(
                    f"- {item['symbol']}: {item['direction']} {item['price']:,.2f} ₺ "
                    f"(son fiyat {item.get('last_price', 0):,.2f} ₺) · {item['created']}"
                )
            lines += ["", "Veri ~15 dk gecikmeli olabilir; KAP/aracı kurumdan teyit edin.",
                      "Yatırım tavsiyesi değildir; gerçek emir gönderilmez."]
            try:
                notify.send_notification("\n".join(lines), settings)
            except Exception:
                pass
    return triggered


def render_panel(username: str, symbol: str, price: float) -> None:
    """Anlık terminalde alarm kurma / listeleme paneli."""
    with st.container(border=True):
        st.subheader("Fiyat alarmı", divider="gray")
        st.caption(
            "Seçili hissenin belirlediğin seviyeye ulaşması halinde tek seferlik uyarı gider. "
            "Bu bir işlem sinyali değil, bilgilendirmedir; veri gecikmeli olabilir."
        )
        c1, c2, c3 = st.columns([1.2, 1, 1])
        direction = c1.selectbox("Koşul", ["above", "below"],
                                 format_func=lambda x: "Üzerine çıkarsa" if x == "above" else "Altına inerse",
                                 key="price_alert_dir")
        level = c2.number_input("Seviye (₺)", min_value=0.01, value=float(price),
                                step=max(0.01, round(float(price) * 0.01, 2)),
                                key="price_alert_level")
        note = c3.text_input("Not", key="price_alert_note")
        if st.button("Alarm kur", icon=":material/notifications:", key="price_alert_add"):
            add(username, symbol, direction, level, note)
            st.toast(f"{symbol} için alarm kuruldu.", icon=":material/check:")
            st.rerun()

    rules = [r for r in load(username) if not r.get("triggered")]
    with st.expander(f"Aktif alarmlar ({len(rules)})", icon=":material/notifications:"):
        if not rules:
            st.caption("Aktif alarm yok.")
            return
        for rule in rules:
            col1, col2 = st.columns([3, 1])
            label = "Üzerine çıkarsa" if rule.get("direction") == "above" else "Altına inerse"
            col1.markdown(f"**{rule['symbol']}** · {label} **{float(rule['price']):,.2f} ₺**"
                          f" · {rule.get('note') or '—'}")
            if col2.button("Sil", key=f"price_alert_del_{rule.get('id')}"):
                remove(username, str(rule.get("id")))
                st.rerun()
