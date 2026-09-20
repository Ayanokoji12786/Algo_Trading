from __future__ import annotations

import pandas as pd

from trading_system.config.schema import TrendStrategyConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.features.trend_signal import composite_trend_score
from trading_system.features.volatility import ewma_annualized_vol
from trading_system.strategies.base import Signal


class TrendStrategy:
    """The frozen 63/126/252-day time-series-momentum ensemble.

    generate_signals(store, as_of) only ever calls store.history_as_of(...),
    so it structurally cannot see data timestamped after ``as_of`` --
    Prompt.md S7's point-in-time requirement is enforced by PointInTimeStore,
    not by discipline in this class.
    """

    strategy_id = "trend_63_126_252"

    def __init__(self, config: TrendStrategyConfig):
        self._config = config

    def generate_signals(
        self, store: PointInTimeStore, as_of: pd.Timestamp
    ) -> list[Signal]:
        signals: list[Signal] = []
        for meta in store.universe:
            history = store.history_as_of(meta.symbol, as_of)
            if history.empty:
                continue
            close = history["close"]
            score = composite_trend_score(close, self._config.lookback_days)
            if score is None:
                continue
            vol = ewma_annualized_vol(close, self._config.vol_window_days)
            signals.append(
                Signal(
                    symbol=meta.symbol,
                    asset_class=meta.asset_class,
                    direction=score,
                    strategy_id=self.strategy_id,
                    timestamp=as_of,
                    annualized_vol=vol,
                )
            )
        return signals
