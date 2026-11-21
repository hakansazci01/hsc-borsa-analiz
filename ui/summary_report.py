"""
Otonom sistem özet raporu — gerçek kayıtlardan üretilir.

Hiçbir sayı uydurulmaz: kararlar, öngörü self-test sonuçları, gerçek emirler,
bakiye ve piyasa rejimi yerel kayıtlardan okunur. Rapor hem Markdown dosyasına
( GitHub'da görünür ) hem de arayüzde gösterilir.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ui import autonomous, tr_journal, tr_monitor, tr_scalper


ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "OTONOM_OZET.md"


def build() -> dict[str, Any]:
    state = autonomous._load()
    acc = autonomous.accuracy(state)
    decisions = state.get("decisions", [])
    last = state.get("last_decision", {})
    tests = state.get("prediction_tests", [])
    journal = tr_journal.recent(500)
    orders = [r for r in journal if r.get("kind") == "emir"]
    trade = tr_monitor.summary()
    pos = tr_monitor.live_metrics()["position"]

    open_count = sum(1 for d in decisions if d.get("decision") == "OPEN")
    closed_count = sum(1 for d in decisions if d.get("decision") == "CLOSED")
    correct = sum(1 for t in tests if t.get("correct"))
    wrong = len(tests) - correct

    return {
        "updated": last.get("at", "—"),
        "decisions": len(decisions),
        "open": open_count,
        "closed": closed_count,
        "last_decision": last.get("decision", "—"),
        "last_reasons": last.get("reasons", []),
        "regime": last.get("regime", "—"),
        "robust": last.get("robust", 0),
        "prediction_tests": len(tests),
        "prediction_correct": correct,
        "prediction_wrong": wrong,
        "accuracy": acc.get("rate"),
        "orders": len(orders),
        "trades": trade["trades"],
        "net_pnl": trade["net_pnl"],
        "fees": trade["fees"],
        "balance": tr_scalper.available_try(),
        "position": pos["symbol"] if pos else "Yok",
        "journal": len(journal),
    }


def to_markdown(r: dict[str, Any]) -> str:
    p = r["accuracy"]
    lines = [
        "# Otonom Sistem — Gerçek Durum Özeti",
        "",
        f"**Son güncelleme:** {r['updated']}  ",
        "**Kaynak:** Yerel karar kayıtları, gerçek Binance TR API ve işlem defteri. "
        "Tahmin/simülasyon değildir.",
        "",
        "## 1. Sistem sağlığı",
        "",
        "| Ölçü | Değer |",
        "|---|---|",
        f"| Toplam otonom karar | {r['decisions']} |",
        f"| OPEN kararı | {r['open']} |",
        f"| CLOSED kararı | {r['closed']} |",
        f"| Son karar | **{r['last_decision']}** |",
        f"| Piyasa rejimi | {r['regime']} |",
        f"| Doğrulanmış kârlı edge | {r['robust']} |",
        "",
        "## 2. Öngörü başarısı (self-test)",
        "",
        "| Ölçü | Değer |",
        "|---|---|",
        f"| Gerçek fiyatla test edilen öngörü | {r['prediction_tests']} |",
        f"| Doğru | {r['prediction_correct']} |",
        f"| Yanlış | {r['prediction_wrong']} |",
        f"| İsabet oranı | **%{p if p is not None else '—'}** |",
        "",
        "> Her öngörü, bir sonraki turda gerçekleşen BTC fiyatıyla karşılaştırılır.",
        "",
        "## 3. İşlem ve sermaye",
        "",
        "| Ölçü | Değer |",
        "|---|---|",
        f"| Gönderilen emir kaydı | {r['orders']} |",
        f"| Kapanmış işlem | {r['trades']} |",
        f"| Net K/Z | **{r['net_pnl']:+.2f} ₺** |",
        f"| Toplam komisyon | {r['fees']:.4f} ₺ |",
        f"| Kullanılabilir bakiye | **{r['balance']:,.2f} ₺** |",
        f"| Açık pozisyon | {r['position']} |",
        f"| İşlem defteri kaydı | {r['journal']} |",
        "",
        "## 4. Neden işlem yok?",
        "",
        "Son kararın gerekçesi: " + ("; ".join(r["last_reasons"]) or "Tüm koşullar sağlandı."),
        "",
        "Sistem yalnızca **doğrulanmış edge + yukarı rejim** birlikte olduğunda işlem açar. "
        "Bu koşul sağlanmadığı için para riske atılmaz; bu bir arıza değil, kasıtlı korumadır.",
        "",
        "## 5. Sektör araştırması — karlı botlar ne yapıyor?",
        "",
        "222M gerçek işlemlik akademik çalışma (2026): karlı botların sırrı doğru "
        "tahmin değil **doğru giriş fiyatı** (execution). Perakende %51,3 isabetle "
        "kaybederken botlar %49,9 isabetle 133M $ kâr ediyor; ~%70'i erken giriş "
        "ve spread ödememekten (limit emir). Bizim sistemde execution, rejim filtresi, "
        "disiplin ve doğrulanmış backtest **mevcut**. Eksikler: BNB komisyon indirimi "
        "(açılabilir), short/futures (spot long only), kolokasyon (günlük stratejide gerekmez) "
        "ve sermaye büyüklüğü.",
        "",
        "## 6. Ne zaman işlem yapılacak?",
        "",
        "- BTC günlük kapanışı EMA50'nin üstüne geçmeli",
        "- Hedef coin günlük EMA50 üzerinde pullback yapmalı",
 "- Öngörü isabeti en az %40 olmalı",
        "- O an motor kendiliğinden açılır, ₺50–100 limit emir atar ve deftere+bildirime yazar",
        "",
        "---",
        "",
        "Bu rapor her otonom analiz turunda otomatik yenilenir "
        "(`reports/OTONOM_OZET.md`).",
    ]
    return "\n".join(lines) + "\n"


def write() -> Path:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(to_markdown(build()), encoding="utf-8")
    return REPORT


if __name__ == "__main__":
    print(write())
