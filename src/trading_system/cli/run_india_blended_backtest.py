"""Runs the India NSE+MCX blended portfolio (EQ_MOM_01 + MCX_TREND_01,
50:50 risk share) against SYNTHETIC data, plus a SEPARATE standalone
MCX_CARRY_01 backtest (never blended, per its own integration rule).

Every number this prints is a pipeline-mechanics check on fabricated data,
exactly like cli/run_backtest.py and cli/run_robustness_suite.py for the
global-futures system -- see Docs/India_Implementation_Spec.md S6.1's
equivalent note. Nothing here is evidence about real NSE/MCX markets.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from trading_system.backtest.blended_engine import BlendedPortfolioEngine, SleeveSpec
from trading_system.backtest.metrics import compute_metrics
from trading_system.backtest.validation_split import split_and_report
from trading_system.config.india_schema import default_india_config
from trading_system.data.combined import CombinedDataSource
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic_curve import SyntheticMCXCurveDataSource
from trading_system.data.synthetic_equity import SyntheticNSEEquityDataSource
from trading_system.experiments.tracker import ExperimentRecord, ExperimentTracker
from trading_system.strategies.carry_activation import evaluate_carry_activation
from trading_system.strategies.cross_sectional_momentum import CrossSectionalMomentumStrategy
from trading_system.strategies.mcx_carry import MCXCarryStrategy
from trading_system.strategies.mcx_trend_sleeve import MCXTrendSleeve

REPORT_DIR = Path("experiments/reports/india_blended_v1")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tracker = ExperimentTracker("experiments/log.jsonl")

    config = default_india_config()
    eq_source = SyntheticNSEEquityDataSource(config.eq_data)
    mcx_source = SyntheticMCXCurveDataSource(config.mcx_data)
    store = PointInTimeStore(CombinedDataSource([eq_source, mcx_source]))
    print(f"Universe: {len(store.universe)} instruments "
          f"({sum(1 for m in store.universe if m.asset_class=='nse_equity')} NSE equities, "
          f"{sum(1 for m in store.universe if m.asset_class=='mcx_commodity')} MCX contracts)")

    eq_mom = CrossSectionalMomentumStrategy(config.eq_mom)
    mcx_trend = MCXTrendSleeve(config.mcx_trend)

    blended_specs = [
        SleeveSpec(
            eq_mom,
            rebalance_frequency="monthly",
            risk_share=config.risk_shares["eq_mom_01"],
            participation_cap_fraction=0.05,
        ),
        SleeveSpec(
            mcx_trend,
            rebalance_frequency="daily",
            risk_share=config.risk_shares["mcx_trend_01"],
            resolve_contracts=True,
        ),
    ]

    print("\n=== BLENDED PORTFOLIO (EQ_MOM_01 + MCX_TREND_01, 50:50) ===")
    blended_engine = BlendedPortfolioEngine(
        store,
        blended_specs,
        config.cost,
        initial_capital=config.initial_capital,
        portfolio_vol_target=config.portfolio_vol_target,
        covariance_window_days=config.covariance_window_days,
    )
    blended_result = blended_engine.run()
    blended_metrics = compute_metrics(blended_result.equity_curve, blended_result.turnover)
    print(json.dumps(blended_metrics, indent=2))

    print("\n=== EQ_MOM_01 STANDALONE (100% risk share) ===")
    eq_only_engine = BlendedPortfolioEngine(
        store,
        [SleeveSpec(eq_mom, rebalance_frequency="monthly", risk_share=1.0, participation_cap_fraction=0.05)],
        config.cost,
        initial_capital=config.initial_capital,
        portfolio_vol_target=config.portfolio_vol_target,
    )
    eq_only_result = eq_only_engine.run()
    eq_only_metrics = compute_metrics(eq_only_result.equity_curve, eq_only_result.turnover)
    print(json.dumps(eq_only_metrics, indent=2))

    print("\n=== MCX_TREND_01 STANDALONE (100% risk share) ===")
    mcx_only_engine = BlendedPortfolioEngine(
        store,
        [SleeveSpec(mcx_trend, rebalance_frequency="daily", risk_share=1.0, resolve_contracts=True)],
        config.cost,
        initial_capital=config.initial_capital,
        portfolio_vol_target=config.portfolio_vol_target,
    )
    mcx_only_result = mcx_only_engine.run()
    mcx_only_metrics = compute_metrics(mcx_only_result.equity_curve, mcx_only_result.turnover)
    print(json.dumps(mcx_only_metrics, indent=2))

    print("\n=== MCX_CARRY_01 STANDALONE (never blended -- own integration rule) ===")
    mcx_carry = MCXCarryStrategy(config.mcx_carry)
    carry_engine = BlendedPortfolioEngine(
        store,
        [SleeveSpec(mcx_carry, rebalance_frequency="daily", risk_share=1.0, resolve_contracts=True)],
        config.cost,
        initial_capital=config.initial_capital,
        portfolio_vol_target=config.portfolio_vol_target,
    )
    carry_result = carry_engine.run()
    carry_metrics = compute_metrics(carry_result.equity_curve, carry_result.turnover)
    print(json.dumps(carry_metrics, indent=2))

    stress_config = dataclasses.replace(config.cost, scenario="stress_2x")
    carry_stress_engine = BlendedPortfolioEngine(
        store,
        [SleeveSpec(mcx_carry, rebalance_frequency="daily", risk_share=1.0, resolve_contracts=True)],
        stress_config,
        initial_capital=config.initial_capital,
        portfolio_vol_target=config.portfolio_vol_target,
    )
    carry_stress_metrics = compute_metrics(carry_stress_engine.run().equity_curve)

    print("\n=== MCX_CARRY_01 activation gate (subset check only) ===")
    activation = evaluate_carry_activation(
        trend_daily_returns=mcx_only_result.equity_curve.pct_change().dropna(),
        carry_daily_returns=carry_result.equity_curve.pct_change().dropna(),
        carry_metrics_base=carry_metrics,
        carry_metrics_stress_2x=carry_stress_metrics,
    )
    print(json.dumps(activation, indent=2))

    print("\n=== Validation split (exact dates per Docs/India_Implementation_Spec.md S1.5) ===")
    split_report = split_and_report(blended_result.equity_curve)
    print(json.dumps(split_report, indent=2, default=str))

    results = {
        "blended": blended_metrics,
        "eq_mom_01_standalone": eq_only_metrics,
        "mcx_trend_01_standalone": mcx_only_metrics,
        "mcx_carry_01_standalone": carry_metrics,
        "mcx_carry_01_activation_gate": activation,
        "validation_split": split_report,
    }
    (REPORT_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str))

    tracker.record(
        ExperimentRecord(
            experiment_id="india_blended_v1",
            hypothesis=(
                "EQ_MOM_01 (NSE cross-sectional momentum) and MCX_TREND_01 (MCX "
                "diversified trend), blended at 50:50 ex-ante risk with a rolling-"
                "covariance vol target, run without error and produce coherent "
                "equity curves on synthetic data; MCX_CARRY_01 is evaluated "
                "standalone and correctly gated from the blend."
            ),
            config={"risk_shares": config.risk_shares, "vol_target": config.portfolio_vol_target},
            data_description="Synthetic NSE equity + MCX multi-expiry commodity data -- NOT real market data.",
            result=results,
            conclusion=(
                "Pipeline runs end-to-end. Numeric outcomes are pipeline-"
                "correctness checks only, per Docs/India_Implementation_Spec.md "
                "S6.1 -- no claim about real NSE/MCX performance can be made "
                "until real exchange data replaces the synthetic sources."
            ),
        )
    )
    print(f"\nReport written to {REPORT_DIR}/results.json")


if __name__ == "__main__":
    main()
