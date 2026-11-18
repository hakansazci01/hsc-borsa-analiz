"""
Kagit para (paper trading) portfoy durumu takibi.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    stop_price: float
    target_price: float


@dataclass
class Portfolio:
    initial_capital: float
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    trades: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = self.initial_capital

    def equity(self, current_prices: dict[str, float]) -> float:
        pos_value = sum(
            p.qty * current_prices.get(p.symbol, p.entry_price)
            for p in self.positions.values()
        )
        return self.cash + pos_value

    def can_open(self, symbol: str, max_positions: int) -> bool:
        if symbol in self.positions:
            return False
        return len(self.positions) < max_positions