"""Strategy interface (Prompt.md S9): market data -> features -> strategy ->
signal. Each strategy is independently inspectable and produces a stream of
Signal objects; strategies are never merged into one opaque model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

from trading_system.data.pit_store import PointInTimeStore


@dataclass(frozen=True)
class Signal:
    symbol: str
    asset_class: str
    direction: float  # in [-1, 1]; sign and magnitude both carry meaning
    strategy_id: str
    timestamp: pd.Timestamp
    annualized_vol: float | None = None
    # "Confidence if justified" (Prompt.md S9) -- the trend baseline has no
    # research-justified confidence measure, so this stays None rather than
    # being filled with an arbitrary number.
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Strategy(Protocol):
    strategy_id: str

    def generate_signals(
        self, store: PointInTimeStore, as_of: pd.Timestamp
    ) -> list[Signal]:
        ...
