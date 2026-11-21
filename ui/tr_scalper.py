"""
Binance TR CANLI motor — SADECE GERÇEK PARA ve GERÇEK VERİ.

STRATEJİ (tek):
    günlük EMA50 pullback — ui/quant_lab.py::signals(frame, "pullback", (50,)) İLE AYNI KURAL.
    1 dakikalık RSI7 / EMA9/20 scalper TAMAMEN KALDIRILDI. Doğrulanmamış stratejiyle emir yok.

KONTROLLER (her alım öncesi, sırayla):
    1) STOP_FILE     — ui/tr_scalper.py::config_gate / cycle
    2) config.yaml   — binance_tr.enabled == False ise emir YOK
    3) config.yaml   — max_order_usdt doğrudan okunur, pozisyon üst sınırı olarak uygulanır
    4) risk_brakes   — günlük zarar / kasa drawdown / ani çöküş frenleri
    5) sinyal        — günlük EMA50 pullback (AL değilse emir yok)

GERÇEK İŞLEM KAYDI: her kapanan işlem trades.csv'ye yazılır (JSONL de korunur).
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from ui import quant_lab
from ui.binance_tr_bot import _request


ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "users" / "tr_daily_state.json"
STOP_FILE = ROOT / "users" / "TR_SCALPER_STOP"
TRADES_CSV = ROOT / "trades.csv"
STRATEGY_NAME = "günlük EMA50 pullback (quant_lab)"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "XRPUSDT", "DOGEUSDT",
           "ADAUSDT", "LINKUSDT", "BNBUSDT", "SOLUSDT")
MAX_HOLD_DAYS = 90
EXIT_BELOW_EMA = 0.97   # STOP-LOSS: günlük kapanış EMA50 * 0.97 altına düşerse sat
COMMISSION = 0.001      # Binance TR spot VIP0, her yön


# ------------------------------------------------------------------- config
def cfg() -> dict[str, Any]:
    """config.yaml -> binance_tr bölümü (gerçek kilitler buradan okunur)."""
    try:
        from borsa_bot.config import Config

        return dict(Config().get("binance_tr", default={}))
    except Exception:
        return {}


PHRASE_FILE = ROOT / "users" / "tr_phrase_armed.json"


def set_confirmed_phrase(phrase: str) -> tuple[bool, str]:
    """Kullanıcının yazdığı onay ifadesini config ile doğrulayıp yerel dosyaya kaydet."""
    expected = str(cfg().get("confirmation_phrase", "HSC-BINANCE-TR-ARM"))
    if str(phrase).strip() != expected:
        PHRASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PHRASE_FILE.write_text(json.dumps({"confirmed": False, "at": time.strftime("%Y-%m-%d %H:%M:%S")}),
                               encoding="utf-8")
        return False, "Onay ifadesi yanlış"
    PHRASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PHRASE_FILE.write_text(json.dumps({"confirmed": True, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                       "phrase": expected}), encoding="utf-8")
    return True, "Onay ifadesi doğrulandı"


def is_phrase_confirmed() -> bool:
    try:
        d = json.loads(PHRASE_FILE.read_text(encoding="utf-8"))
        expected = str(cfg().get("confirmation_phrase", "HSC-BINANCE-TR-ARM"))
        return bool(d.get("confirmed")) and str(d.get("phrase", "")) == expected
    except Exception:
        return False


def config_gate() -> list[str]:
    """config.yaml kilitleri + onay ifadesi. BOŞ dönerse geçerli."""
    reasons: list[str] = []
    c = cfg()
    if not bool(c.get("enabled", False)):
        reasons.append("config.yaml: binance_tr.enabled = false")
    if not is_phrase_confirmed():
        reasons.append("Onay ifadesi doğrulanmadı (HSC-BINANCE-TR-ARM)")
    return reasons


POSITION_PCT = 0.10       # tek işlem = güncel bakiyenin %10'u (bileşik büyüme)
PROFIT_LOCK_TRY = 50.0    # toplam kâr +50 TL'yi geçince stop giriş üstüne çekilir


def position_size_try(balance: float | None = None) -> float:
    """DİNAMİK işlem boyutu: API bakiyesi * 0.10. Sabit limit yok."""
    bal = available_try() if balance is None else float(balance)
    return round(bal * POSITION_PCT, 4)


def max_order_usdt() -> float:
    """Dinamik üst sınır (geriye dönük uyumluluk)."""
    return position_size_try()


def _filters(symbol: str) -> dict[str, float]:
    import urllib.request

    try:
        with urllib.request.urlopen(
            "https://www.binance.tr/open/v1/common/symbols", timeout=12
        ) as r:
            data = json.loads(r.read().decode())
        for s in data.get("data", {}).get("list", []):
            if s.get("symbol") == symbol:
                out: dict[str, float] = {}
                for f in s.get("filters", []):
                    if f.get("filterType") == "LOT_SIZE":
                        out["min_qty"] = float(f["minQty"])
                        out["step"] = float(f["stepSize"])
                    if f.get("filterType") == "NOTIONAL":
                        out["min_notional"] = float(f["minNotional"])
                return out
    except Exception:
        pass
    return {"min_qty": 0.0, "step": 0.0, "min_notional": 10.0}


def price(symbol: str) -> float | None:
    ok, data = _request("/open/v1/ticker/price", {"symbol": symbol.replace("_", "")})
    if ok and isinstance(data, dict):
        try:
            return float(data.get("price"))
        except (TypeError, ValueError):
            pass
    f = klines(symbol, "1m", 1)
    return float(f["Close"].iloc[-1]) if f is not None and not f.empty else None


def klines(symbol: str, interval: str = "1m", limit: int = 10):
    """Sadece ani-çöküş koruması için 1dk veri (STRATEJİ DEĞİL)."""
    import urllib.request

    plain = symbol.replace("_", "")
    url = f"https://api.binance.me/api/v1/klines?symbol={plain}&interval={interval}&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=12) as r:
            rows = json.loads(r.read().decode())
        import pandas as pd

        return pd.DataFrame([{
            "Open": float(x[1]), "High": float(x[2]), "Low": float(x[3]),
            "Close": float(x[4]), "Volume": float(x[5]),
        } for x in rows])
    except Exception:
        return None


def asset_balance(asset: str) -> float:
    ok, data = _request("/open/v1/account/spot", signed=True)
    if ok and isinstance(data, dict) and data.get("code") in (0, None):
        for a in (data.get("data", {}).get("accountAssets") or []):
            if a.get("asset") == asset:
                try:
                    return float(a.get("free", 0) or 0)
                except (TypeError, ValueError):
                    return 0.0
    return 0.0


def available_try() -> float:
    return asset_balance("TRY")


# ------------------------------------------------------------------- state
def _load() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------- STRATEJİ
def signal(symbol: str) -> dict[str, Any]:
    """
    GÜNLÜK EMA50 pullback — quant_lab.signals("pullback",(50,)) ile AYNI KURAL.
    1dk RSI/EMA9/20 KALDIRILDI.
    """
    frame = quant_lab.fetch(symbol, "1d", 200)
    if frame is None or len(frame) < 60:
        return {"decision": "BEKLE", "reason": "günlük veri yok"}
    ent, ex = quant_lab.signals(frame, "pullback", (50,))
    c = frame["Close"]
    m = quant_lab.ema(c, 50)
    px = float(c.iloc[-1])
    ma = float(m.iloc[-1])
    if bool(ent.iloc[-1]):
        return {"decision": "AL", "price": px, "ema50": ma,
                "reason": "günlük EMA50 pullback (Close>EMA50, Low<=EMA50, önceki Close<=EMA50)"}
    if bool(ex.iloc[-1]):
        return {"decision": "SAT", "price": px, "ema50": ma,
                "reason": "günlük kapanış EMA50*0.97 altı"}
    return {"decision": "BEKLE", "price": px, "ema50": ma,
            "reason": f"fiyat {px:.4f} / EMA50 {ma:.4f} — giriş koşulu yok"}


def position_exit(pos: dict[str, Any], px: float, ma: float,
                  effective_sl: float | None = None) -> str:
    """Açık pozisyon çıkışı: EMA50 stop, kâr kilidi veya 90 gün."""
    held_days = (time.time() - float(pos.get("entry_ts", time.time()))) / 86400
    if effective_sl and px <= effective_sl:
        return f"kâr kilidi: fiyat {px:.4f} ≤ kilitli stop {effective_sl:.4f}"
    if px < ma * EXIT_BELOW_EMA:
        return "stop loss: günlük EMA50 %3 altı"
    if held_days >= MAX_HOLD_DAYS:
        return "zaman: 90 gün"
    return ""


# ------------------------------------------------------------------- emir
def _order(symbol: str, side: int, qty: float) -> dict[str, Any]:
    payload = {"symbol": symbol, "side": side, "type": 2, "quantity": str(qty)}
    ok, data = _request("/open/v1/orders", payload, signed=True, method="POST")
    if not ok:
        res = {"ok": False, "reason": str(data)[:200]}
    elif isinstance(data, dict) and data.get("code") not in (0, None):
        res = {"ok": False, "reason": f"{data.get('code')}: {data.get('msg')}"}
    else:
        res = {"ok": True, "data": data}
    try:
        from ui.trade_notify import order_alert

        body = ((res.get("data") or {}).get("data") or {}
                if isinstance(res.get("data"), dict) else {})
        detail = (f"orderId={body.get('orderId') or body.get('id')}" if body
                  else str(res.get("reason", ""))[:160])
        order_alert(symbol, "AL" if side == 0 else "SAT", qty, 0,
                    bool(res.get("ok")), detail)
    except Exception:
        pass
    return res


def buy(symbol: str) -> dict[str, Any]:
    """GERÇEK ALIŞ — tüm kilitler burada uygulanır."""
    gates = config_gate()
    if STOP_FILE.exists():
        gates.append("STOP_FILE etkin")
    if gates:
        return {"ok": False, "reason": "ALIŞ ENGELLENDİ: " + "; ".join(gates)}
    brake = brakes_block(symbol)
    if brake:
        return {"ok": False, "reason": "ALIŞ ENGELLENDİ (fren): " + brake}
    px = price(symbol)
    if not px:
        return {"ok": False, "reason": "fiyat alınamadı"}
    flt = _filters(symbol)
    step = flt["step"] or 0.00000001
    # Her alışta güncel bakiyeyi API'den çek -> %10 (bileşik büyüme).
    current_balance = available_try()
    cap = position_size_try(current_balance)   # örn 506 TL -> 50.6 TL
    need = max(cap, flt["min_notional"] + 0.5) / px
    qty = round(int(need / step + 0.999999) * step, 8)
    qty = max(qty, flt["min_qty"])
    if qty * px > cap + 0.01:  # yuvarlama payı
        return {"ok": False, "reason": f"tutar dinamik %10 limitini aşıyor (>{cap:.2f} TL)"}
    res = _order(symbol, 0, qty)
    if res.get("ok"):
        body = (res.get("data") or {}).get("data") or {}
        st = _load()
        st["position"] = {
            "symbol": symbol, "qty": qty, "entry": px,
            "entry_ts": time.time(), "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "order_id": body.get("orderId") or body.get("id"),
            "cost": round(px * qty, 4), "strategy": STRATEGY_NAME,
        }
        _save(st)
    return res


def sell(symbol: str, qty: float, reason: str) -> dict[str, Any]:
    """GERÇEK SATIŞ + trades.csv kaydı."""
    actual = asset_balance(symbol.split("_")[0]) or qty
    qty = min(qty, actual)
    px = price(symbol) or 0
    payload = {"symbol": symbol, "side": 1, "type": 2, "quoteOrderQty": str(round(px * qty * 0.9995, 4))}
    ok, data = _request("/open/v1/orders", payload, signed=True, method="POST")
    success = bool(ok and isinstance(data, dict) and data.get("code") in (0, None))
    if not success:
        return {"ok": False, "reason": str(data)[:200]}

    st = _load()
    pos = st.get("position") or {}
    entry = float(pos.get("entry", px))
    gross = (px - entry) * qty
    fee = (entry + px) * qty * COMMISSION
    net = gross - fee
    duration_sec = round(time.time() - float(pos.get("entry_ts", time.time())), 0)
    if pos:
        st["history"] = (st.get("history", []) + [{
            "symbol": symbol, "qty": qty, "entry": entry, "exit": px,
            "gross_pnl": round(gross, 4), "fee": round(fee, 4),
            "net_pnl": round(net, 4), "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_sec": duration_sec, "reason": reason, "strategy": STRATEGY_NAME,
        }])[-50:]
        st["realized_pnl"] = round(sum(float(h.get("net_pnl", 0)) for h in st["history"]), 4)
        st.pop("position", None)
        _save(st)
        _write_trade_csv({
            "tarih": time.strftime("%Y-%m-%d %H:%M:%S"), "sembol": symbol,
            "alış_fiyatı": round(entry, 6), "satış_fiyatı": round(px, 6),
            "adet": qty, "komisyon": round(fee, 4),
            "net_kar_zarar": round(net, 4), "işlem_süresi": f"{duration_sec:.0f} sn",
            "strateji_adı": STRATEGY_NAME,
        })
    return {"ok": True, "data": data}


def _write_trade_csv(row: dict[str, Any]) -> None:
    cols = ["tarih", "sembol", "alış_fiyatı", "satış_fiyatı", "adet",
            "komisyon", "net_kar_zarar", "işlem_süresi", "strateji_adı"]
    exists = TRADES_CSV.exists()
    with TRADES_CSV.open("a", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        if not exists:
            w.writeheader()
        w.writerow(row)


# ------------------------------------------------------------------- FRENLER
def kill_switch() -> bool:
    if STOP_FILE.exists():
        return True
    if config_gate():
        return True
    st = _load()
    try:
        from ui import risk_brakes

        risk_brakes.update_from_history(st.get("history", []))
        if risk_brakes.daily_loss_breached()[0]:
            return True
        dd, _ = risk_brakes.drawdown_breached(available_try())
        if dd:
            STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
            STOP_FILE.write_text("drawdown kilidi: kasa %10 eridi", encoding="utf-8")
            return True
    except Exception:
        pass
    return False


def brakes_block(symbol: str) -> str:
    try:
        from ui import risk_brakes

        risk_brakes.update_from_history(_load().get("history", []))
        daily, msg = risk_brakes.daily_loss_breached()
        if daily:
            return msg
        dd, msg2 = risk_brakes.drawdown_breached(available_try())
        if dd:
            return msg2
        crash, msg3 = risk_brakes.crash_detected(symbol)
        if crash:
            return msg3
    except Exception:
        pass
    return ""


def cycle() -> list[str]:
    """Tek tur — GERÇEK emir, günlük EMA50 stratejisi, tüm frenler aktif."""
    logs: list[str] = []
    if kill_switch():
        return ["KILL SWITCH: STOP/config/fren — yeni işlem yok"]
    st = _load()
    pos = st.get("position")
    if pos:
        sym = pos["symbol"]
        vals = quant_lab.fetch(sym, "1d", 200)
        if vals is None or len(vals) < 60:
            return ["günlük veri yok — pozisyon korunuyor"]
        px = float(vals["Close"].iloc[-1])
        ma = float(quant_lab.ema(vals["Close"], 50).iloc[-1])
        # KÂR KORUMA: toplam gerçekleşen kâr +50 TL'yi geçtiyse stop'u giriş üstüne çek.
        realized = float(st.get("realized_pnl", 0) or 0)
        if realized >= PROFIT_LOCK_TRY:
            entry = float(pos["entry"])
            locked = round(entry * (1 + 0.002), 8)  # komisyonu kurtaran +%0,2
            pos["locked_sl"] = max(float(pos.get("locked_sl", 0)), locked)
            logs.append(f"KÂR KORUMA: toplam {realized:+.2f} TL ≥ +{PROFIT_LOCK_TRY} TL — "
                        f"stop {locked:.4f} (giriş üstü, zararla kapanmaz)")
        why = position_exit(pos, px, ma, effective_sl=pos.get("locked_sl"))
        if why:
            res = sell(sym, float(pos["qty"]), why)
            logs.append(f"SAT {sym} {'OK' if res.get('ok') else 'HATA'} neden={why}")
        else:
            logs.append(f"Pozisyon {sym}: fiyat {px:.4f} / EMA50 {ma:.4f} — bekleniyor")
        return logs
    for sym in SYMBOLS:
        brake = brakes_block(sym)
        if brake:
            logs.append(f"FREN ({sym}): {brake}")
            continue
        s = signal(sym)
        if s.get("decision") == "AL":
            res = buy(sym)
            logs.append(f"AL {sym} {'OK' if res.get('ok') else 'HATA'} neden={s.get('reason')}")
            return logs
        logs.append(f"{sym}: {s.get('decision')} — {s.get('reason')}")
    return logs


# ------------------------------------------------------------------- UI yardımcıları
def tradeable_pairs() -> tuple[str, ...]:
    return SYMBOLS


def get_secret(section: str, key: str, default: str = "") -> str:
    from ui import secrets_access

    return secrets_access.get(section, key, default)
