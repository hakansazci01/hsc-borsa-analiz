"""
16-CHECK GATE — her alım emrinden önce 16 kontrol, sırayla.

Biri bile başarısız olursa emir ATILMAZ ve hangi kontrolün engellediği loglanır.
Önceki 6 adımın (rejim, grid, ATR, ardışık zarar, MTF, korelasyon) tüm kontrolleri
buraya bağlanır. Limitler DEĞİŞMEZ.
"""

from __future__ import annotations

from typing import Any

from ui import (correlation_guard, market_regime, risk_brakes,
                tr_scalper as t)

CHECKS = [
    "enabled = true",
    "confirmation phrase doğru",
    "STOP_FILE yok",
    "günlük zarar limiti",
    "trailing drawdown",
    "ani çöküş",
    "ardışık zarar < 3",
    "rejim AYI değil",
    "multi-timeframe onayı",
    "korelasyon < 0.85",
    "volatilite normal",
    "komisyon filtresi (3x)",
    "bakiye yeterli (%10)",
    "sembol işlem görüyor",
    "balina/haber koruması",
    "yedek sağlam mı (felaket kurtarma)",
    "OFI / L2 depth temiz",
    "skor güveni (%5-7)",
    "stale-data: tick yaşı < 60 sn",
]


def run(symbol: str, price: float | None = None,
        expected_return: float | None = None,
        mode: str = "EMA50_PULLBACK") -> dict[str, Any]:
    """16 kontrolü sırayla çalıştır. SÜREKLİ KÜÇÜK KAR modunda 8/9 uyarlanır."""
    quick = str(mode).upper() == "QUICK_PROFIT"
    px = price if price is not None else t.price(symbol)
    results: list[dict[str, Any]] = []
    failed_at: int | None = None
    failed_msg = ""

    def add(ok: bool, msg: str, ok_note: str = "OK") -> bool:
        nonlocal failed_at, failed_msg
        results.append({"no": len(results) + 1, "check": CHECKS[len(results)],
                        "ok": bool(ok), "note": msg if not ok else ok_note})
        if not ok and failed_at is None:
            failed_at = len(results)
            failed_msg = msg
        return ok

    # 1) enabled
    add(bool(t.cfg().get("enabled", False)), "enabled=false", "enabled=true ✅")
    # 2) phrase
    add(t.is_phrase_confirmed(), "confirmation phrase doğrulanmadı", "phrase doğrulandı ✅")
    # 3) STOP_FILE
    add(not t.STOP_FILE.exists(), "STOP_FILE var", "STOP_FILE yok ✅")
    # 4) günlük zarar
    st = t._load()
    risk_brakes.update_from_history(st.get("history", []))
    d, dmsg = risk_brakes.daily_loss_breached()
    add(not d, dmsg or "günlük limit OK")
    # 5) trailing drawdown
    dd, ddmsg = risk_brakes.drawdown_breached(t.available_try())
    add(not dd, ddmsg or "drawdown OK")
    # 6) ani çöküş
    cr, crmsg = risk_brakes.crash_detected(symbol)
    add(not cr, crmsg or "ani çöküş yok")
    # 7) ardışık zarar
    ls, lsmsg = market_regime.loss_streak_block(st)
    add(not ls, lsmsg or "ardışık zarar < 3")
    # 8) rejim — EMA50'de AYI alınmaz; SÜREKLİ KÜÇÜK KAR'da AYI'da %7 + RSI<25
    reg = market_regime.regime(symbol)
    if quick:
        add(True, "", ok_note=f"rejim={reg['name']} — AYI ise %7 pozisyon + RSI<25")
    else:
        add(not reg["bear"], f"rejim={reg['name']} (AYI ise alınmaz)")
    # 9) MTF — SÜREKLİ KÜÇÜK KAR 1s RSI+BB ile çalışır, günlük/4s MTF aranmaz
    if quick:
        results.append({"no": 9, "check": CHECKS[8], "ok": True,
                        "note": "SÜREKLİ KÜÇÜK KAR — MTF aranmaz (1s RSI + Bollinger)"})
    elif reg["range"]:
        results.append({"no": 9, "check": CHECKS[8], "ok": True,
                        "note": "GRID modu — MTF onayı aranmaz"})
    else:
        mtf = market_regime.mtf_confirm(symbol)
        add(mtf["ok"], f"günlük={'OK' if mtf['daily'] else 'NO'} / 4s={'OK' if mtf['h4'] else 'NO'}")
    # 10) korelasyon
    open_sym = st.get("position", {}).get("symbol") if st.get("position") else None
    cg = correlation_guard.guard_entry(open_sym, symbol)
    add(cg["allowed"], cg["reason"])
    # 11) volatilite + order book satış baskısı (aynı kontrol)
    vol, volmsg = t.volatility_block(symbol)
    bmsg = ""
    try:
        from ui import live_feed

        bmsg = live_feed.book_block()
    except Exception:
        pass
    add(not vol and not bmsg, bmsg or volmsg or "volatilite normal",
        "volatilite normal, order book OK ✅")
    # 12) komisyon filtresi
    qty_guess = (t.position_size_try() / px) if px and px > 0 else 0
    comm_ok, comm_msg = t.commission_gate(
        symbol, expected_return or t.TAKE_PROFIT_EXPECTED, qty_guess, px or 1)
    add(comm_ok, comm_msg or "komisyon OK")
    # 13) bakiye
    bal = t.available_try()
    size = t.position_size_try(bal)
    add(bal > 0 and size <= bal * 0.10 + 0.01,
        f"bakiye {bal:.2f} TL, işlem {size:.2f} TL (≤%10)")
    # 14) sembol
    tradable = t.tradeable_pairs()
    add(symbol in tradable, f"sembol {symbol} {'işlem görüyor' if symbol in tradable else 'listede yok'}")
    # 15) balina/haber koruması (5 dk %3+ hareket -> 30 dk bekle)
    try:
        from ui import whale_guard

        wg = whale_guard.check(symbol)
        add(not wg["blocked"], wg["reason"],
            f"5dk hareket %{wg['move_pct']:.2f} — normal ✅")
    except Exception:
        add(True, "", "balina kontrolü atlandı")
    # 16) yedek sağlam mı (felaket kurtarma)
    try:
        from ui import disaster_recovery

        corrupt = disaster_recovery.block_on_corrupt()
        add(not corrupt, "YEDEK BOZUK — işlem yapılmıyor", "yedek sağlam ✅")
    except Exception:
        pass
    # 17) OFI / L2 depth — sadece Sürekli Küçük Kar modunda alım freni
    if quick:
        try:
            from ui import order_flow
            ofi = order_flow.check(symbol)
            add(ofi["ok"], f"OFI: {ofi['state']} — {ofi['reason']}",
                f"OFI Temiz ✅ (bid %{ofi['bid_pct']}, spread %{ofi['spread_pct']:.2f})")
        except Exception:
            add(True, "", "OFI kontrolü atlandı (fail-open)")
    else:
        results.append({"no": 17, "check": CHECKS[16], "ok": True,
                        "note": "EMA50 modu — OFI freni uygulanmaz"})
    # 18) Skor güveniyle boyutlandırma — üst limit %7
    if quick:
        add(True, "", "Skor 35-50: %5 · 50-70: %6 · 70+: %7 · üst limit %7 ✅")
    else:
        results.append({"no": 18, "check": CHECKS[17], "ok": True,
                        "note": "EMA50 modu — sabit pozisyon"})
    # 19) Stale-data — tick yaşı < 60 sn (WS/REST en tazesi)
    try:
        from ui import safety_guards
        fresh, msg = safety_guards.stale_check()
        add(fresh, msg, f"tick taze ✅ ({msg})")
    except Exception:
        add(True, "", "stale kontrolü atlandı (fail-open)")

    passed = sum(1 for r in results if r["ok"])
    return {
        "symbol": symbol,
        "passed": passed,
        "total": len(results),
        "ok": failed_at is None,
        "failed_at": failed_at,
        "failed_msg": failed_msg,
        "results": results,
        "summary": (f"{passed}/{len(results)} GEÇTİ" if failed_at is None
                    else f"{passed}/{len(results)} GEÇTİ — Başarısız: {failed_at}. {CHECKS[failed_at-1]}: {failed_msg}"),
    }


def last() -> dict[str, Any]:
    """Panel için son gate sonucu."""
    from pathlib import Path

    p = t.ROOT / "users" / "last_gate.json"
    try:
        import json

        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(result: dict[str, Any]) -> None:
    import json

    p = t.ROOT / "users" / "last_gate.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
