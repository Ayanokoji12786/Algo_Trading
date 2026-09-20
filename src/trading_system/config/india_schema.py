"""Centralized, reproducible config for the India NSE+MCX blended system
(Docs/India_Implementation_Spec.md) -- mirrors config/schema.py's SystemConfig
for the global-futures system: every parameter that affects behavior is a
field here, not a literal buried in strategy/engine code, so a run is
reproducible from this object alone (Prompt.md S28).

Kept as a separate config object from SystemConfig rather than folded into
it -- the two systems have different sleeves, different cost models, and
different data sources; merging them into one schema would either force
irrelevant fields onto both or silently blur which research document a
given field's value actually comes from.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from trading_system.data.synthetic_curve import MCXCurveConfig
from trading_system.data.synthetic_equity import NSEEquityConfig
from trading_system.execution.india_costs import IndiaCostConfig
from trading_system.strategies.cross_sectional_momentum import EQMomConfig
from trading_system.strategies.mcx_carry import MCXCarryConfig
from trading_system.strategies.mcx_trend_sleeve import MCXTrendConfig


@dataclass(frozen=True)
class IndiaSystemConfig:
    eq_data: NSEEquityConfig = field(default_factory=NSEEquityConfig)
    mcx_data: MCXCurveConfig = field(default_factory=MCXCurveConfig)
    eq_mom: EQMomConfig = field(default_factory=EQMomConfig)
    mcx_trend: MCXTrendConfig = field(default_factory=MCXTrendConfig)
    mcx_carry: MCXCarryConfig = field(default_factory=MCXCarryConfig)
    cost: IndiaCostConfig = field(default_factory=IndiaCostConfig)
    # Docs/India_Implementation_Spec.md RISK_01: 50:50 neutral baseline.
    # MCX_CARRY_01 is deliberately absent from this dict -- it must never
    # receive a nonzero share in the blended portfolio until its own
    # standalone OOS test passes (strategies/mcx_carry.py's module docstring).
    risk_shares: dict[str, float] = field(
        default_factory=lambda: {"eq_mom_01": 0.5, "mcx_trend_01": 0.5}
    )
    portfolio_vol_target: float = 0.10
    covariance_window_days: int = 120
    initial_capital: float = 1_000_000.0

    def __post_init__(self) -> None:
        if "mcx_carry_01" in self.risk_shares and self.risk_shares["mcx_carry_01"] != 0.0:
            raise ValueError(
                "mcx_carry_01 must not have a nonzero risk share in the blended "
                "portfolio -- its own research document prohibits blending it "
                "with trend until it independently passes a standalone OOS test "
                "(Docs/India_Implementation_Spec.md S1.1). This is a hard "
                "safeguard, not a parameter to flip casually."
            )


def default_india_config(
    start_date: date = date(2010, 1, 1), end_date: date = date(2023, 12, 31)
) -> IndiaSystemConfig:
    return IndiaSystemConfig(
        eq_data=NSEEquityConfig(start_date=start_date, end_date=end_date),
        mcx_data=MCXCurveConfig(start_date=start_date, end_date=end_date),
    )
