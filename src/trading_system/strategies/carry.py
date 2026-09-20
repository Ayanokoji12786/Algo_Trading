"""Cross-asset carry satellite (Research.md "Carry satellite").

Built but OFF by default (SystemConfig.carry_enabled = False). Carry needs
asset-class-appropriate inputs this system does not have real data for yet:
FX interest-rate differentials, bond term spreads, commodity futures-curve
slope/roll yield, equity dividend yield (Docs/Implementation_Spec.md S3).

CarryStrategy consumes scores through the CarrySignalSource protocol so a
real vendor-backed implementation slots in later without touching this
class. SyntheticCarrySignalSource below is a clearly-labeled placeholder
used ONLY to exercise the module's wiring (disabled flag, activation gate,
complementarity test) end to end. It is fabricated data, independent of the
price series' own randomness, and must never be read as evidence about real
carry returns -- see the module-level warning repeated on the class itself.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd

from trading_system.config.schema import TrendStrategyConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.features.volatility import ewma_annualized_vol
from trading_system.strategies.base import Signal


class CarrySignalSource(Protocol):
    def carry_score_as_of(self, symbol: str, as_of: pd.Timestamp) -> float | None:
        """A value in [-1, 1], analogous to the trend composite score, but
        derived from asset-class-appropriate carry information (rate
        differential, term spread, roll yield, dividend yield) rather than
        price trend. Must only use information available as of ``as_of``.
        """
        ...


class SyntheticCarrySignalSource:
    """FABRICATED PLACEHOLDER -- not derived from any real term-structure,
    rate, or yield data. Exists solely so CarryStrategy and the activation
    gate can be exercised end to end before a real carry data source exists.
    Uses its own independent RNG stream (seeded separately from price data)
    so the complementarity test has something genuinely uncorrelated to
    check against, by construction -- this is a test fixture, not a claim
    that real carry is uncorrelated with real trend.
    """

    def __init__(self, symbols: list[str], seed: int = 999):
        self._rng_by_symbol = {
            sym: np.random.default_rng(seed + hash(sym) % (2**16)) for sym in symbols
        }
        self._cache: dict[tuple[str, pd.Timestamp], float] = {}

    def carry_score_as_of(self, symbol: str, as_of: pd.Timestamp) -> float | None:
        key = (symbol, as_of)
        if key not in self._cache:
            rng = self._rng_by_symbol[symbol]
            self._cache[key] = float(np.clip(rng.normal(0.0, 0.4), -1.0, 1.0))
        return self._cache[key]


class CarryStrategy:
    strategy_id = "carry_satellite"

    def __init__(self, carry_source: CarrySignalSource, vol_config: TrendStrategyConfig):
        self._carry_source = carry_source
        self._vol_config = vol_config

    def generate_signals(
        self, store: PointInTimeStore, as_of: pd.Timestamp
    ) -> list[Signal]:
        signals = []
        for meta in store.universe:
            score = self._carry_source.carry_score_as_of(meta.symbol, as_of)
            if score is None:
                continue
            history = store.history_as_of(meta.symbol, as_of)
            if history.empty:
                continue
            vol = ewma_annualized_vol(history["close"], self._vol_config.vol_window_days)
            signals.append(
                Signal(
                    symbol=meta.symbol,
                    asset_class=meta.asset_class,
                    direction=score,
                    strategy_id=self.strategy_id,
                    timestamp=as_of,
                    annualized_vol=vol,
                    metadata={"family": "carry", "data_status": "SYNTHETIC_PLACEHOLDER"},
                )
            )
        return signals
