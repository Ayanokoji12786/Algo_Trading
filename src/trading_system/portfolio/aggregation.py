"""Multi-strategy signal combination (Prompt.md S12; Research.md "Portfolio
logic": compare Trend only, Carry only, Trend + Carry equal ex-ante risk).

Only used for the trend+carry complementarity test -- the production
baseline runs a single active sleeve (Research.md "Start with one active
trend sleeve"), so compute_target_weights in sizing.py remains the path
used by BacktestEngine for the baseline. This module exists so "equal
ex-ante risk per strategy" is implemented once, shared with the
single-strategy code path's own equalization logic, rather than
reimplemented ad hoc for the comparison.
"""
from __future__ import annotations

from trading_system.config.schema import RiskConfig
from trading_system.portfolio.sizing import _scale_and_cap, _within_group_class_weights
from trading_system.strategies.base import Signal


def compute_multi_strategy_target_weights(
    signals_by_strategy: dict[str, list[Signal]],
    risk_config: RiskConfig,
    vol_floor_annualized: float,
) -> dict[str, float]:
    """Equal ex-ante risk budget per strategy (not per instrument, not per
    asset class across strategies), each strategy internally equalized
    across its own asset classes exactly as the single-strategy path does.
    """
    usable_by_strategy = {
        strategy_id: [s for s in signals if s.annualized_vol is not None and s.direction != 0]
        for strategy_id, signals in signals_by_strategy.items()
    }
    usable_by_strategy = {k: v for k, v in usable_by_strategy.items() if v}
    if not usable_by_strategy:
        return {}

    n_strategies = len(usable_by_strategy)
    combined_pre_scale: dict[str, float] = {}
    vol_by_symbol: dict[str, float] = {}
    asset_class_by_symbol: dict[str, str] = {}

    for strategy_id, signals in usable_by_strategy.items():
        strategy_vol = {s.symbol: max(s.annualized_vol, vol_floor_annualized) for s in signals}
        strategy_pre_scale = _within_group_class_weights(signals, strategy_vol)
        for s in signals:
            vol_by_symbol[s.symbol] = strategy_vol[s.symbol]
            asset_class_by_symbol[s.symbol] = s.asset_class
        for symbol, weight in strategy_pre_scale.items():
            combined_pre_scale[symbol] = combined_pre_scale.get(symbol, 0.0) + weight / n_strategies

    return _scale_and_cap(combined_pre_scale, vol_by_symbol, asset_class_by_symbol, risk_config)
