"""MCX_TREND_01 -- MCX diversified time-series trend
(Docs/India_Implementation_Spec.md S1.1).

    signal_L    = sign(log(index_t / index_t-L))   for L in [21, 63, 126, 252]
    trend_score = mean(signal_L)
    volatility  = 60-trading-day REALIZED vol (baseline; EWMA is a challenger)
    raw_weight  = trend_score / volatility
    weight      = raw_weight / sum(|raw_weight|)   (single flat bucket -- no
                                                     per-asset-class split,
                                                     unlike the global-futures
                                                     trend sleeve's hierarchical
                                                     equalization)

Reuses features.trend_signal.composite_trend_score unchanged (it already
generalizes to an arbitrary lookback tuple) with the 4-horizon set this
research specifies -- deliberately NOT reusing strategies/trend.py's
TrendStrategy class directly, because that class's Signal objects feed
portfolio/sizing.py's hierarchical asset-class equalization, which is the
WRONG sizing rule here (MCX_TREND_01 specifies flat cross-asset
normalization within one bucket). Sharing the feature function but not the
strategy/sizing class keeps each research document's frozen sizing rule
intact without forcing them through one shared code path that only fits one
of them.

Reads prices from each commodity's `{COMMODITY}_INDEX` symbol (the
return-linked continuous series) for signal generation ONLY -- per the
research's explicit "keep two separate objects" requirement, P&L is
computed elsewhere (backtest/blended_engine.py) from the actual dated
contract via data/roll.py's roll rule, never from this index series.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_system.data.pit_store import PointInTimeStore
from trading_system.features.trend_signal import composite_trend_score
from trading_system.features.volatility import realized_annualized_vol


@dataclass(frozen=True)
class MCXTrendConfig:
    lookback_days: tuple[int, ...] = (21, 63, 126, 252)
    vol_window_days: int = 60
    vol_floor_annualized: float = 0.01


class MCXTrendSleeve:
    sleeve_id = "mcx_trend_01"

    def __init__(self, config: MCXTrendConfig):
        self._config = config

    def compute_weights(
        self, store: PointInTimeStore, as_of: pd.Timestamp
    ) -> dict[str, float]:
        cfg = self._config
        raw: dict[str, float] = {}
        for meta in store.universe:
            if meta.asset_class != "mcx_commodity_index":
                continue
            # Skip index metas without an ``underlying`` label: the weights
            # dict is keyed by underlying, and multiple index symbols with
            # empty underlying would silently collide under one "" key,
            # producing a single mixed signal that isn't traceable to any
            # commodity. Same filter as MCXCarryStrategy uses.
            if not meta.underlying:
                continue
            history = store.history_as_of(meta.symbol, as_of)
            if history.empty:
                continue
            close = history["close"]
            score = composite_trend_score(close, cfg.lookback_days)
            if score is None:
                continue
            vol = realized_annualized_vol(close, cfg.vol_window_days)
            if vol is None:
                continue
            raw[meta.underlying] = score / max(vol, cfg.vol_floor_annualized)

        gross = sum(abs(w) for w in raw.values())
        if gross == 0:
            return {}
        return {underlying: w / gross for underlying, w in raw.items()}
