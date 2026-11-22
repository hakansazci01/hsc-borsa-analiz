"""REJİME GÖRE OTOMATİK MOD — kullanıcı mod seçmez.

BOĞA  -> EMA50 Pullback (mevcut strateji, korunur)
YATAY -> SÜREKLİ KÜÇÜK KAR
AYI   -> SÜREKLİ KÜÇÜK KAR, %7 pozisyon + RSI<25 (az işlem)

Ek frenler: günde en fazla 10 işlem, en fazla 3 zararlı işlem.
Açık pozisyon mod değişince KAPATILMAZ; yeni pozisyonlar yeni modla açılır.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "config.yaml"
STATE = ROOT / "users" / "auto_mode_state.json"

EMA50 = "EMA50_PULLBACK"
QUICK = "QUICK_PROFIT"
LABELS = {EMA50: "EMA50 Pullback", QUICK: "SÜREKLİ KÜÇÜK KAR"}
VALID = tuple(LABELS)
MAX_DAY_TRADES = 10
MAX_DAY_LOSSES = 3


def _load_cfg() -> dict[str, Any]:
    try:
        data = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _state() -> dict[str, Any]:
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict[str, Any]) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _log(msg: str) -> None:
    try:
        from ui import autonomous_ops
        autonomous_ops._log(msg)
    except Exception:
        pass


def get() -> str:
    """Elle seçim (geri uyumluluk) — artık otomatik mod kullanılır."""
    mode = str(_load_cfg().get("strategy", {}).get("mode", EMA50)).upper()
    return mode if mode in VALID else EMA50


def label() -> str:
    return LABELS[get()]


def set(mode: str) -> str:
    mode = str(mode).upper()
    if mode not in VALID:
        mode = EMA50
    data = _load_cfg()
    data.setdefault("strategy", {})["mode"] = mode
    CFG.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")
    return mode


def auto_mode(regime_name: str) -> str:
    """BOĞA -> EMA50, YATAY/AYI -> SÜREKLİ KÜÇÜK KAR."""
    name = str(regime_name).upper()
    return EMA50 if ("BOĞA" in name or "BOGA" in name) else QUICK


def current_auto(regime_name: str | None = None) -> tuple[str, str]:
    """Rejimden modu seçer; değişince log yazar. (mod, rejim) döner."""
    if regime_name is None:
        try:
            from ui import market_regime
            regime_name = market_regime.regime("BTC_TRY")["name"]
        except Exception:
            regime_name = "YATAY"
    mode = auto_mode(regime_name)
    st = _state()
    if st.get("mode") != mode:
        old = st.get("mode", "—")
        st.update(mode=mode, regime=regime_name,
                  changed_at=time.strftime("%Y-%m-%d %H:%M:%S"), previous=old)
        _save(st)
        _log(f"REJİM MOD GEÇİŞİ: {regime_name} → {LABELS[mode]} "
             f"(önce: {LABELS.get(old, old)}) — açık pozisyon korundu")
    return mode, str(regime_name)


def bear_params(regime_name: str) -> tuple[float | None, float]:
    """AYI -> %7 pozisyon ve RSI<25; diğerleri -> normal ve RSI<35."""
    if "AYI" in str(regime_name).upper():
        return 0.07, 25.0
    return None, 35.0


def day_guard() -> str | None:
    """Günlük 10 işlem / 3 zararlı işlem freni — dönen metin varsa işlem yok."""
    st = _state()
    today = time.strftime("%Y-%m-%d")
    if st.get("day") != today:
        st.update(day=today, day_trades=0, day_losses=0)
        _save(st)
        _log(f"YENİ GÜN: {today} — işlem sayacı sıfırlandı")
    if int(st.get("day_trades", 0)) >= MAX_DAY_TRADES:
        return f"GÜNLÜK İŞLEM LİMİTİ: {st['day_trades']}/{MAX_DAY_TRADES} — ertesi güne kadar dur"
    if int(st.get("day_losses", 0)) >= MAX_DAY_LOSSES:
        return f"GÜNLÜK ZARAR LİMİTİ: {st['day_losses']}/{MAX_DAY_LOSSES} — ertesi güne kadar dur"
    return None


def day_record(net: float) -> None:
    """Gerçekleşen işlem sonrası sayaçları güncelle."""
    st = _state()
    today = time.strftime("%Y-%m-%d")
    if st.get("day") != today:
        st.update(day=today, day_trades=0, day_losses=0)
    st["day_trades"] = int(st.get("day_trades", 0)) + 1
    if float(net) < 0:
        st["day_losses"] = int(st.get("day_losses", 0)) + 1
    _save(st)
