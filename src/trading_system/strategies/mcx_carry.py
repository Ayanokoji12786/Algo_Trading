"""MCX_CARRY_01 -- MCX commodity curve carry
(Docs/India_Implementation_Spec.md S1.1).

    curve_slope = 365/(expiry2 - expiry1 in days) * ln(F2/F1)
    carry       = -curve_slope        (backwardation -> positive carry score)

Standalone ranking/directional signal ONLY. Per the research's explicit
integration rule, this strategy's output must NEVER be fed into the blended
portfolio (portfolio/blend.py) until its own standalone out-of-sample test
passes independently -- there is deliberately no code path connecting this
class to backtest/blended_engine.py's sleeve list. It is built and tested
for its own standalone backtest only.

ASSUMPTION (not specified by the research beyond the signal formula itself,
logged here per Prompt.md S3's format): sizing uses the same inverse-
volatility-then-normalize pattern as the other sleeves (front-contract
realized vol as the risk denominator), since the research specifies the
carry score and its cross-sectional standardization but not an exact
position-sizing formula for the standalone test. This should be validated
or replaced once real MCX curve data exists.

SIMPLIFICATION (documented, not silent): when fewer than
`min_commodities_for_cross_section` commodities have simultaneous front/next
data on a given date, the research's fallback is "each commodity's own
rolling historical percentile." That per-commodity rolling-percentile
fallback is NOT implemented here -- on such dates this strategy simply
produces no signal for that date (returns whatever cross-sectional subset
is available, or {} if below the minimum), which is a conservative but
incomplete stand-in flagged in Docs/India_Implementation_Spec.md S5.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.roll import front_and_next_contracts
from trading_system.features.cross_sectional import zscore_cross_section
from trading_system.features.volatility import realized_annualized_vol


@dataclass(frozen=True)
class MCXCarryConfig:
    min_commodities_for_cross_section: int = 3
    vol_window_days: int = 60
    vol_floor_annualized: float = 0.01


class MCXCarryStrategy:
    sleeve_id = "mcx_carry_01"

    def __init__(self, config: MCXCarryConfig):
        self._config = config

    def compute_weights(
        self, store: PointInTimeStore, as_of: pd.Timestamp
    ) -> dict[str, float]:
        cfg = self._config
        underlyings = sorted({m.underlying for m in store.universe if m.underlying})

        raw_carry: dict[str, float] = {}
        vol_by_underlying: dict[str, float] = {}
        for underlying in underlyings:
            front, next_ = front_and_next_contracts(underlying, as_of.date(), store.universe)
            if front is None or next_ is None:
                continue
            f1 = store.close_as_of(front.symbol, as_of)
            f2 = store.close_as_of(next_.symbol, as_of)
            if f1 is None or f2 is None or f1 <= 0 or f2 <= 0:
                continue
            days_between = (next_.expiry_date - front.expiry_date).days
            if days_between <= 0:
                continue
            slope = (365.0 / days_between) * np.log(f2 / f1)
            raw_carry[underlying] = -slope

            front_history = store.history_as_of(front.symbol, as_of)["close"]
            vol = realized_annualized_vol(front_history, cfg.vol_window_days)
            if vol is not None:
                vol_by_underlying[underlying] = vol

        if len(raw_carry) < cfg.min_commodities_for_cross_section:
            return {}

        eligible = {u: raw_carry[u] for u in raw_carry if u in vol_by_underlying}
        if not eligible:
            return {}

        carry_z = zscore_cross_section(eligible)
        raw_weight = {
            u: carry_z[u] / max(vol_by_underlying[u], cfg.vol_floor_annualized)
            for u in eligible
        }
        gross = sum(abs(w) for w in raw_weight.values())
        if gross == 0:
            return {}
        return {u: w / gross for u, w in raw_weight.items()}
