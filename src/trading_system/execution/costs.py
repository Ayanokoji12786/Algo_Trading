"""Transaction cost model (Research.md "Cost and execution model").

C = commissions + exchange/clearing fees + 1/2 spread + slippage + impact
    + roll costs + financing + taxes

This vertical slice collapses commissions/fees/spread/slippage/impact into a
single per-asset-class bps-of-notional figure (CostConfig.bps_by_asset_class),
scaled by the cost scenario (base/2x/3x). Roll costs, financing, and taxes
are NOT yet modeled -- they require real contract/roll/jurisdiction data
(Implementation_Spec.md S3) and are deferred to the real-data phase. This
simplification must not be silently forgotten: it means every cost figure
this system currently reports is a lower bound, not a complete cost model.
"""
from __future__ import annotations

from trading_system.config.schema import CostConfig


def trade_cost(notional_traded: float, asset_class: str, cost_config: CostConfig) -> float:
    """Dollar cost of trading ``notional_traded`` (absolute value used)."""
    bps = cost_config.cost_bps(asset_class)
    return abs(notional_traded) * bps / 10_000.0
