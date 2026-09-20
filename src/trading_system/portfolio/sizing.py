"""Hierarchical risk-equalized position sizing (Research.md "Position sizing"):

    q_i ~ s_i / max(vol_i, vol_floor)                    -- per-instrument
    then equalize ex-ante risk across asset classes       -- not equal notional
    then scale whole portfolio to a fixed vol target
    then cap instrument / asset-class / gross exposure

ASSUMPTION (implementation-level, not from research -- logged here and in
Docs/Implementation_Spec.md S5): portfolio volatility is estimated assuming
zero cross-instrument correlation, i.e. portfolio_vol = sqrt(sum((w_i*vol_i)^2)).
The research specifies vol-targeting but does not specify a covariance
estimator; a real implementation should replace this with an estimated
correlation/covariance matrix once real multi-asset data is available. Using
zero correlation is conservative in the sense that true positive correlation
would make the realized portfolio vol *higher* than this estimate targets.

The single-strategy path (compute_target_weights) and the multi-strategy
path (portfolio/aggregation.py, used only for the trend+carry
complementarity test) share the same pre-scale/scale-and-cap machinery so
the two can never silently diverge in how risk is equalized.
"""
from __future__ import annotations

import math

from trading_system.config.schema import RiskConfig
from trading_system.strategies.base import Signal


def _within_group_class_weights(
    signals: list[Signal], vol_by_symbol: dict[str, float]
) -> dict[str, float]:
    """Steps 1+2: inverse-vol-scale within each asset class, then equalize
    ex-ante risk across asset classes. Output sums to 1 in absolute value
    (assuming at least one usable signal), i.e. it represents *this group's*
    full risk budget, not yet scaled to a portfolio vol target.

    ``vol_by_symbol`` is supplied by the caller (already floored) rather
    than read off the Signal objects here, so this function never needs to
    mutate or extend the (frozen, shared) Signal dataclass.
    """
    raw_risk_unit = {s.symbol: s.direction / vol_by_symbol[s.symbol] for s in signals}
    asset_classes = sorted({s.asset_class for s in signals})
    by_class: dict[str, list[Signal]] = {ac: [] for ac in asset_classes}
    for s in signals:
        by_class[s.asset_class].append(s)

    n_classes = len(asset_classes)
    class_weight: dict[str, float] = {}
    for ac, members in by_class.items():
        class_risk_gross = sum(abs(s.direction) for s in members)
        if class_risk_gross == 0:
            continue
        for s in members:
            class_weight[s.symbol] = (raw_risk_unit[s.symbol] / class_risk_gross) / n_classes
    return class_weight


def _scale_and_cap(
    pre_scale_weight: dict[str, float],
    vol_by_symbol: dict[str, float],
    asset_class_by_symbol: dict[str, str],
    risk_config: RiskConfig,
) -> dict[str, float]:
    if not pre_scale_weight:
        return {}

    # Step 3: scale to the fixed portfolio vol target under the zero-
    # correlation assumption documented above.
    estimated_portfolio_vol = math.sqrt(
        sum((w * vol_by_symbol[sym]) ** 2 for sym, w in pre_scale_weight.items())
    )
    if estimated_portfolio_vol == 0:
        return {}
    scale = risk_config.portfolio_vol_target_annualized / estimated_portfolio_vol
    scaled_weight = {sym: w * scale for sym, w in pre_scale_weight.items()}

    # Step 4: instrument and asset-class caps.
    capped = {
        sym: max(-risk_config.max_instrument_weight, min(risk_config.max_instrument_weight, w))
        for sym, w in scaled_weight.items()
    }
    by_class: dict[str, list[str]] = {}
    for sym in capped:
        by_class.setdefault(asset_class_by_symbol[sym], []).append(sym)
    for symbols in by_class.values():
        class_gross = sum(abs(capped[sym]) for sym in symbols)
        if class_gross > risk_config.max_asset_class_weight and class_gross > 0:
            class_scale = risk_config.max_asset_class_weight / class_gross
            for sym in symbols:
                capped[sym] *= class_scale

    # Gross leverage cap, applied last, independent of statistical vol
    # (Research.md "Position sizing", point 5).
    gross = sum(abs(w) for w in capped.values())
    if gross > risk_config.max_gross_leverage and gross > 0:
        leverage_scale = risk_config.max_gross_leverage / gross
        capped = {sym: w * leverage_scale for sym, w in capped.items()}

    return capped


def compute_target_weights(
    signals: list[Signal],
    risk_config: RiskConfig,
    vol_floor_annualized: float,
) -> dict[str, float]:
    """Return {symbol: fraction_of_capital}, positive = long, negative = short."""
    usable = [s for s in signals if s.annualized_vol is not None and s.direction != 0]
    if not usable:
        return {}

    vol_by_symbol = {s.symbol: max(s.annualized_vol, vol_floor_annualized) for s in usable}
    asset_class_by_symbol = {s.symbol: s.asset_class for s in usable}
    pre_scale = _within_group_class_weights(usable, vol_by_symbol)
    return _scale_and_cap(pre_scale, vol_by_symbol, asset_class_by_symbol, risk_config)
