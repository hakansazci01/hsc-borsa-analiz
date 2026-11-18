"""
İşlem koruma katmanı (freqtrade protections + riskkit SessionManager/DrawdownManager esinli).

Amaç: art arda zarar, aşırı drawdown veya günlük limit aşımında otomatik olarak
 işlem yapmayı durdurmak ve pozisyon boyutunu kademeli küçültmek.

Bu sınıf saf state tutar; ne emir gönderir ne de ağa çıkar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GuardSettings:
    cooldown_bars: int = 2
    stoploss_lookback: int = 20
    stoploss_limit: int = 3
    stoploss_pause_bars: int = 5
    daily_loss_cap_pct: float = 3.0
    drawdown_tier1_pct: float = 3.0
    drawdown_tier2_pct: float = 5.0
    drawdown_halt_pct: float = 8.0
    min_spacing_bars: int = 2

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GuardSettings":
        data = data or {}
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class GuardState:
    high_water_mark: float = 0.0
    last_exit_bar: int = -10**6
    cooldown_until: int = -1
    paused_until: int = -1
    daily_pnl: dict[str, float] = field(default_factory=dict)
    exits: list[dict[str, Any]] = field(default_factory=list)


class RiskGuards:
    def __init__(self, settings: GuardSettings | dict[str, Any] | None = None) -> None:
        self.settings = (
            settings if isinstance(settings, GuardSettings)
            else GuardSettings.from_dict(settings)
        )
        self.state = GuardState()

    def register_bar(self, bar_index: int, equity: float) -> None:
        """Zirve sermayeyi günceller (drawdown kademeleri için)."""
        if equity > self.state.high_water_mark:
            self.state.high_water_mark = equity

    def register_exit(
        self, bar_index: int, day: str, pnl_pct: float, reason: str
    ) -> None:
        """Çıkışı kaydeder, zarar durumunda bekleme sürelerini başlatır."""
        st = self.state
        st.last_exit_bar = bar_index
        st.exits.append(
            {"bar": bar_index, "day": day, "pnl": pnl_pct, "reason": reason}
        )
        st.exits = st.exits[-max(self.settings.stoploss_lookback, 50):]
        st.daily_pnl[day] = st.daily_pnl.get(day, 0.0) + pnl_pct

        if pnl_pct < 0:
            st.cooldown_until = bar_index + self.settings.cooldown_bars

        sl_count = sum(
            1 for e in st.exits[-self.settings.stoploss_lookback:]
            if "stop" in e["reason"].lower() and e["pnl"] < 0
        )
        if sl_count >= self.settings.stoploss_limit:
            st.paused_until = bar_index + self.settings.stoploss_pause_bars

    def evaluate(
        self, bar_index: int, day: str, equity: float
    ) -> dict[str, Any]:
        """İşlem için izin, boyut çarpanı ve engel gerekçelerini döndürür."""
        st = self.state
        s = self.settings
        self.register_bar(bar_index, equity)

        reasons: list[str] = []
        allowed = True
        multiplier = 1.0

        if bar_index < st.paused_until:
            allowed = False
            reasons.append(f"StoplossGuard: {st.paused_until - bar_index} bar bekleniyor")
        if bar_index < st.cooldown_until:
            allowed = False
            reasons.append("Zarar sonrası cooldown")
        if bar_index - st.last_exit_bar < s.min_spacing_bars:
            allowed = False
            reasons.append("Minimum işlem aralığı (min spacing)")
        if st.daily_pnl.get(day, 0.0) <= -abs(s.daily_loss_cap_pct):
            allowed = False
            reasons.append("Günlük zarar limiti aşıldı")

        hwm = st.high_water_mark or equity or 1.0
        drawdown = max(0.0, (hwm - equity) / hwm * 100)
        if drawdown >= s.drawdown_halt_pct:
            allowed = False
            reasons.append(f"Drawdown %{drawdown:.1f} — işlem durduruldu")
        elif drawdown >= s.drawdown_tier2_pct:
            multiplier = 0.25
            reasons.append(f"Drawdown %{drawdown:.1f} — pozisyon %25")
        elif drawdown >= s.drawdown_tier1_pct:
            multiplier = 0.5
            reasons.append(f"Drawdown %{drawdown:.1f} — pozisyon %50")

        return {
            "allowed": allowed,
            "size_multiplier": multiplier,
            "reasons": reasons,
            "drawdown_pct": round(drawdown, 2),
            "daily_pnl_pct": round(st.daily_pnl.get(day, 0.0), 2),
            "cooldown_active": bar_index < st.cooldown_until,
            "paused": bar_index < st.paused_until,
        }

    def snapshot(self) -> dict[str, Any]:
        """Arayüzde gösterilebilir, anahtar değer içermeyen durum özeti."""
        st = self.state
        return {
            "high_water_mark": round(st.high_water_mark, 2),
            "last_exit_bar": st.last_exit_bar,
            "cooldown_until": st.cooldown_until,
            "paused_until": st.paused_until,
            "daily_pnl": {k: round(v, 2) for k, v in st.daily_pnl.items()},
            "exit_count": len(st.exits),
        }
