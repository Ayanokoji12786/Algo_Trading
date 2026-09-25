"""Centralized configuration schema.

Every parameter here maps to a specific line in Docs/Implementation_Spec.md.
Nothing that affects strategy behavior, sizing, costs, or execution should be
a literal embedded in code elsewhere in this package -- it belongs here so a
backtest is reproducible from its config (Prompt.md S28).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Mode = Literal["research", "backtest", "paper", "live"]
RebalanceFrequency = Literal["daily", "weekly"]
CostScenario = Literal["base", "stress_2x", "stress_3x"]


@dataclass(frozen=True)
class TrendStrategyConfig:
    """The frozen 63/126/252-day trend ensemble (Research.md "Core trend signal").

    lookback_days is presented in the research as a specific operationalization
    of the literature's 1-12 month persistence window, not a value taken
    directly from a cited study -- treat it as the frozen baseline to test,
    and sweep its neighborhood (Prompt.md S21) rather than assuming it optimal.
    """

    lookback_days: tuple[int, ...] = (63, 126, 252)
    # 60-day EWMA is explicitly flagged in Research.md as "an appropriate
    # baseline to test", not a fixed requirement -- see Implementation_Spec.md S5.
    vol_window_days: int = 60
    # Floor prevents unrealistic position blow-up when measured vol -> 0.
    vol_floor_annualized: float = 0.01


@dataclass(frozen=True)
class RiskConfig:
    """Portfolio-level risk hierarchy (Research.md "Position sizing")."""

    # Explicitly labeled by the research as "a comparison convention, not a
    # scientifically established optimum" -- kept configurable for that reason.
    portfolio_vol_target_annualized: float = 0.10
    max_instrument_weight: float = 0.20
    max_asset_class_weight: float = 0.40
    max_gross_leverage: float = 4.0


_VALID_COST_SCENARIOS = ("base", "stress_2x", "stress_3x")
_VALID_MODES = ("research", "backtest", "paper", "live")


@dataclass(frozen=True)
class CostConfig:
    """Transaction cost model (Research.md "Cost and execution model").

    bps_by_asset_class values are conservative placeholder estimates, used in
    the absence of a real broker/vendor cost feed (Implementation_Spec.md S5).
    They are never to be reported as measured costs.
    """

    bps_by_asset_class: dict[str, float] = field(
        default_factory=lambda: {
            "equity_index": 1.5,
            "rates": 1.0,
            "fx": 1.0,
            "commodities": 2.0,
        }
    )
    scenario: CostScenario = "base"

    def __post_init__(self) -> None:
        # Fail loud at construction rather than deep inside a backtest
        # loop -- previously an unknown scenario (typo) would silently
        # pass construction, then KeyError from scenario_multiplier() much
        # later, with far less diagnostic value.
        if self.scenario not in _VALID_COST_SCENARIOS:
            raise ValueError(
                f"CostConfig.scenario={self.scenario!r} is not one of "
                f"{_VALID_COST_SCENARIOS!r}."
            )

    def scenario_multiplier(self) -> float:
        return {"base": 1.0, "stress_2x": 2.0, "stress_3x": 3.0}[self.scenario]

    def cost_bps(self, asset_class: str) -> float:
        return self.bps_by_asset_class[asset_class] * self.scenario_multiplier()


@dataclass(frozen=True)
class DataConfig:
    """Universe and date range. Symbols/venues are placeholders until a real
    data vendor is selected (Implementation_Spec.md S6.1); the synthetic
    source uses these purely as labels for asset-class bucketing.
    """

    asset_classes: tuple[str, ...] = ("equity_index", "rates", "fx", "commodities")
    instruments_per_asset_class: int = 4
    start_date: date = date(2000, 1, 1)
    end_date: date = date(2023, 12, 31)
    random_seed: int = 42


@dataclass(frozen=True)
class BacktestConfig:
    """Execution timing and accounting (Research.md "Entry and exit logic",
    "Cost and execution model").
    """

    rebalance_frequency: RebalanceFrequency = "weekly"
    # Signals are computed from information as-of session t-1. The baseline
    # ("no earlier than the next tradable session") executes at session t,
    # i.e. execution_delay_sessions=0. Research requires additionally testing
    # +1 and +2 session delays as a fragility check -- set this to 1 or 2 to
    # run those variants.
    execution_delay_sessions: int = 0
    initial_capital: float = 1_000_000.0

    def __post_init__(self) -> None:
        # The plain BacktestEngine treats any frequency != "daily" as
        # "weekly", so a typo ("weeky", "monthly") would silently run as
        # weekly rather than error. Fail loud instead. Note the plain engine
        # supports only daily/weekly (monthly lives in the blended engine).
        if self.rebalance_frequency not in ("daily", "weekly"):
            raise ValueError(
                f"BacktestConfig.rebalance_frequency={self.rebalance_frequency!r} "
                "must be 'daily' or 'weekly'."
            )
        # A negative delay is look-ahead bias (see execution/simulator.py).
        if self.execution_delay_sessions < 0:
            raise ValueError(
                f"BacktestConfig.execution_delay_sessions="
                f"{self.execution_delay_sessions} must be >= 0 (a negative "
                "delay would execute before the decision date -- look-ahead)."
            )
        if self.initial_capital <= 0:
            raise ValueError(
                f"BacktestConfig.initial_capital={self.initial_capital} must be positive."
            )


@dataclass(frozen=True)
class SystemConfig:
    mode: Mode = "backtest"
    trend: TrendStrategyConfig = field(default_factory=TrendStrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    # Built but inactive per Research.md "Carry satellite" -- activation is
    # gated on empirical tests this system has not yet run.
    carry_enabled: bool = False

    def __post_init__(self) -> None:
        # Validate mode against the full known set (defense in depth: the
        # Literal type protects at type-check time but doesn't fire at
        # runtime, so a typo like "papper" would previously silently pass
        # construction and only surface as a KeyError somewhere weird).
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"SystemConfig.mode={self.mode!r} is not one of {_VALID_MODES!r}."
            )
        if self.mode == "live":
            raise ValueError(
                "Live trading must never be enabled via default config "
                "construction (Prompt.md S34/S35). This is a hard safeguard, "
                "not a parameter to flip casually."
            )
