"""EQ_MOM_01 -- NSE cross-sectional equity momentum
(Docs/India_Implementation_Spec.md S1.1).

    return_6m  = close_t / close_t-126 - 1
    return_12m = close_t / close_t-252 - 1
    vol_252    = std(log daily returns, 252) * sqrt(252)
    mom6_adj   = return_6m / vol_252
    mom12_adj  = return_12m / vol_252
    score      = 0.5*zscore_cross_section(mom6_adj) + 0.5*zscore_cross_section(mom12_adj)

Baseline selection is top-30 by score, inverse-volatility-weighted, with a
single-name cap and a sector cap. This is architecturally different from
this system's other strategies: it needs the WHOLE eligible universe's
values on the same date at once (a cross-sectional score), not just one
instrument in isolation, and it fully sizes itself (selection + weighting +
caps) rather than emitting generic per-instrument Signals for a separate
sizing step -- see portfolio/blend.py's docstring for why sleeves are
combined post-hoc rather than through the single-strategy Signal/sizing path
used by the global-futures trend system.

KNOWN SIMPLIFICATION (documented, not silent): the research specifies
point-in-time Nifty 200 membership (never today's constituents projected
backward). This system has no real historical index-constituent data yet
(Docs/India_Implementation_Spec.md S5), so "eligible universe" here is
simply every instrument in the supplied store's universe that has reached
the minimum history requirement -- appropriate for the fixed, non-delisting
synthetic universe this is tested against, but not a substitute for a real
effective-dated membership table.

NOT YET IMPLEMENTED (flagged in Docs/India_Implementation_Spec.md S5): the
rank-buffer hysteresis challenger (retain incumbents until rank < 45) --
only the plain top-N baseline is implemented. The liquidity participation
cap is implemented separately (portfolio/participation.py) since it needs
NAV/trade-size context this stateless per-date function doesn't have.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from trading_system.data.pit_store import PointInTimeStore
from trading_system.features.cross_sectional import zscore_cross_section
from trading_system.features.returns import log_return
from trading_system.features.volatility import realized_annualized_vol


@dataclass(frozen=True)
class EQMomConfig:
    lookback_6m_days: int = 126
    lookback_12m_days: int = 252
    vol_window_days: int = 252
    min_history_days: int = 252
    top_n: int = 30
    single_name_cap: float = 0.05
    sector_cap: float = 0.25
    weight_6m: float = 0.5
    weight_12m: float = 0.5
    # Restricts this sleeve to instruments of this asset class. Required
    # once the store's universe is shared with other sleeves (e.g. the
    # blended NSE+MCX portfolio) -- without this filter, the strategy would
    # happily compute "momentum" over MCX commodity/index symbols too, which
    # is a scope bug, not a feature (caught via an integration test after it
    # produced exactly this symptom in a manual smoke test).
    eligible_asset_class: str = "nse_equity"


class CrossSectionalMomentumStrategy:
    sleeve_id = "eq_mom_01"

    def __init__(self, config: EQMomConfig):
        self._config = config

    def compute_weights(
        self, store: PointInTimeStore, as_of: pd.Timestamp
    ) -> dict[str, float]:
        cfg = self._config
        mom6: dict[str, float] = {}
        mom12: dict[str, float] = {}
        vol: dict[str, float] = {}
        sector_by_symbol: dict[str, str] = {}

        for meta in store.universe:
            if meta.asset_class != cfg.eligible_asset_class:
                continue
            history = store.history_as_of(meta.symbol, as_of)
            if len(history) < cfg.min_history_days:
                continue
            close = history["close"]
            r6 = log_return(close, cfg.lookback_6m_days)
            r12 = log_return(close, cfg.lookback_12m_days)
            v = realized_annualized_vol(close, cfg.vol_window_days)
            if r6 is None or r12 is None or v is None or v <= 0:
                continue
            # Convert log return to simple return to match the research's
            # `close_t/close_t-L - 1` definition exactly.
            simple_r6 = float(np.exp(r6) - 1)
            simple_r12 = float(np.exp(r12) - 1)
            mom6[meta.symbol] = simple_r6 / v
            mom12[meta.symbol] = simple_r12 / v
            vol[meta.symbol] = v
            sector_by_symbol[meta.symbol] = meta.sector

        if not mom6:
            return {}

        z6 = zscore_cross_section(mom6)
        z12 = zscore_cross_section(mom12)
        score = {
            sym: cfg.weight_6m * z6[sym] + cfg.weight_12m * z12[sym] for sym in mom6
        }

        ranked = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
        selected = [sym for sym, _ in ranked[: cfg.top_n]]
        if not selected:
            return {}

        raw = {sym: 1.0 / vol[sym] for sym in selected}
        total = sum(raw.values())
        weights = {sym: w / total for sym, w in raw.items()}

        # Single-name cap.
        weights = {sym: min(w, cfg.single_name_cap) for sym, w in weights.items()}

        # Sector cap, proportional scale-down (no redistribution to other
        # names -- consistent with how portfolio/sizing.py's caps behave).
        by_sector: dict[str, list[str]] = {}
        for sym in weights:
            by_sector.setdefault(sector_by_symbol[sym], []).append(sym)
        for sector_syms in by_sector.values():
            sector_gross = sum(weights[s] for s in sector_syms)
            if sector_gross > cfg.sector_cap and sector_gross > 0:
                scale = cfg.sector_cap / sector_gross
                for s in sector_syms:
                    weights[s] *= scale

        return weights
