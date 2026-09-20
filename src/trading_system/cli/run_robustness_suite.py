"""Runs the full robustness/validation suite against SYNTHETIC data:
parameter-neighborhood sweeps, cost/delay/rebalance sweeps, leave-one-out
tests, subperiod and holdout attribution, the trend+carry complementarity
check, and a Deflated Sharpe Ratio correction over everything tried.

Every number this script prints is a pipeline-mechanics check, not evidence
about the real trend hypothesis -- see Docs/Implementation_Spec.md S6.1.
Nothing here should be read as "the strategy works" or "the strategy fails."
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pandas as pd

from trading_system.backtest import robustness
from trading_system.backtest.attribution import subperiod_breakdown, train_test_split_metrics
from trading_system.backtest.dsr import deflated_sharpe_ratio
from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.metrics import compute_metrics
from trading_system.backtest.monte_carlo import (
    block_bootstrap_returns,
    summarize_simulations,
    trade_order_permutation,
)
from trading_system.backtest.pbo import probability_of_backtest_overfitting
from trading_system.config.defaults import default_config
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.experiments.tracker import ExperimentRecord, ExperimentTracker
from trading_system.strategies.carry import CarryStrategy, SyntheticCarrySignalSource
from trading_system.strategies.carry_activation import evaluate_carry_activation
from trading_system.strategies.trend import TrendStrategy

REPORT_DIR = Path("experiments/reports/robustness_suite_v1")


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    tracker = ExperimentTracker("experiments/log.jsonl")

    config = default_config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)

    _print_header("BASELINE (frozen 63/126/252, weekly, base cost, delay=0)")
    baseline_strategy = TrendStrategy(config.trend)
    baseline_result = BacktestEngine(config, store, baseline_strategy).run()
    baseline_metrics = compute_metrics(baseline_result.equity_curve, baseline_result.turnover)
    print(json.dumps(baseline_metrics, indent=2))

    all_trial_sharpes: list[float] = [baseline_metrics["sharpe"]]

    _print_header("Lookback neighborhood sweep")
    lookback_df = robustness.lookback_neighborhood_sweep(
        config,
        store,
        neighborhoods=[(42, 84, 168), (52, 105, 210), (63, 126, 252), (75, 150, 300), (84, 168, 336)],
        tracker=tracker,
    )
    print(lookback_df.to_string(index=False))
    lookback_df.to_csv(REPORT_DIR / "lookback_sweep.csv", index=False)
    all_trial_sharpes.extend(lookback_df["sharpe"].tolist())

    _print_header("Vol window sweep")
    vol_df = robustness.vol_window_sweep(config, store, windows=[40, 50, 60, 75, 90], tracker=tracker)
    print(vol_df.to_string(index=False))
    vol_df.to_csv(REPORT_DIR / "vol_window_sweep.csv", index=False)
    all_trial_sharpes.extend(vol_df["sharpe"].tolist())

    _print_header("Cost scenario sweep (base / 2x / 3x)")
    cost_df = robustness.cost_scenario_sweep(config, store, tracker=tracker)
    print(cost_df.to_string(index=False))
    cost_df.to_csv(REPORT_DIR / "cost_scenario_sweep.csv", index=False)
    all_trial_sharpes.extend(cost_df["sharpe"].tolist())

    _print_header("Execution delay sweep (0 / 1 / 2 sessions)")
    delay_df = robustness.execution_delay_sweep(config, store, delays=[0, 1, 2], tracker=tracker)
    print(delay_df.to_string(index=False))
    delay_df.to_csv(REPORT_DIR / "execution_delay_sweep.csv", index=False)
    all_trial_sharpes.extend(delay_df["sharpe"].tolist())

    _print_header("Rebalance frequency sweep (weekly / daily)")
    rebal_df = robustness.rebalance_frequency_sweep(config, store, tracker=tracker)
    print(rebal_df.to_string(index=False))
    rebal_df.to_csv(REPORT_DIR / "rebalance_frequency_sweep.csv", index=False)
    all_trial_sharpes.extend(rebal_df["sharpe"].tolist())

    _print_header("Leave-one-asset-class-out")
    lo_ac_df = robustness.leave_one_asset_class_out(config, source, tracker=tracker)
    print(lo_ac_df.to_string(index=False))
    lo_ac_df.to_csv(REPORT_DIR / "leave_one_asset_class_out.csv", index=False)
    all_trial_sharpes.extend(lo_ac_df["sharpe"].tolist())

    _print_header("Leave-one-instrument-out")
    lo_inst_df = robustness.leave_one_instrument_out(config, source, tracker=tracker)
    print(lo_inst_df.to_string(index=False))
    lo_inst_df.to_csv(REPORT_DIR / "leave_one_instrument_out.csv", index=False)
    all_trial_sharpes.extend(lo_inst_df["sharpe"].tolist())

    _print_header("Subperiod (yearly) breakdown of the baseline")
    subperiods = subperiod_breakdown(baseline_result.equity_curve, freq="YE")
    print(subperiods.to_string())
    subperiods.to_csv(REPORT_DIR / "subperiod_breakdown.csv")

    _print_header("In-sample vs. untouched holdout (final 20% of the date range)")
    holdout = train_test_split_metrics(baseline_result.equity_curve, baseline_result.turnover, holdout_fraction=0.2)
    print(json.dumps(holdout, indent=2))
    (REPORT_DIR / "holdout_split.json").write_text(json.dumps(holdout, indent=2))

    _print_header("Trend + Carry complementarity (carry is a SYNTHETIC PLACEHOLDER -- see Docs/Implementation_Spec.md S3)")
    carry_source = SyntheticCarrySignalSource([m.symbol for m in store.universe], seed=999)
    carry_strategy = CarryStrategy(carry_source, config.trend)
    carry_result = BacktestEngine(config, store, carry_strategy).run()
    combined_result = BacktestEngine(config, store, [baseline_strategy, carry_strategy]).run()

    carry_metrics_base = compute_metrics(carry_result.equity_curve, carry_result.turnover)
    stress_config = dataclasses.replace(
        config, cost=dataclasses.replace(config.cost, scenario="stress_2x")
    )
    carry_result_stress = BacktestEngine(stress_config, store, carry_strategy).run()
    carry_metrics_stress = compute_metrics(carry_result_stress.equity_curve)
    combined_metrics = compute_metrics(combined_result.equity_curve, combined_result.turnover)

    activation = evaluate_carry_activation(
        trend_daily_returns=baseline_result.equity_curve.pct_change().dropna(),
        carry_daily_returns=carry_result.equity_curve.pct_change().dropna(),
        carry_metrics_base=carry_metrics_base,
        carry_metrics_stress_2x=carry_metrics_stress,
    )
    print("carry-only:", json.dumps(carry_metrics_base, indent=2))
    print("trend+carry combined:", json.dumps(combined_metrics, indent=2))
    print("activation gate (subset check only):", json.dumps(activation, indent=2))
    (REPORT_DIR / "carry_complementarity.json").write_text(
        json.dumps(
            {
                "carry_only_base_cost": carry_metrics_base,
                "carry_only_2x_cost": carry_metrics_stress,
                "trend_plus_carry_combined": combined_metrics,
                "activation_gate": activation,
            },
            indent=2,
        )
    )

    _print_header("Deflated Sharpe Ratio (multiple-testing correction over every trial above)")
    trial_sharpes = pd.Series(all_trial_sharpes)
    dsr = deflated_sharpe_ratio(
        trial_sharpes=trial_sharpes,
        selected_sharpe=baseline_metrics["sharpe"],
        daily_returns=baseline_result.equity_curve.pct_change().dropna(),
    )
    print(json.dumps(dsr, indent=2))
    (REPORT_DIR / "deflated_sharpe_ratio.json").write_text(json.dumps(dsr, indent=2))

    _print_header("Probability of Backtest Overfitting (CSCV over the lookback-neighborhood trials)")
    trial_returns = robustness.lookback_neighborhood_returns(
        config,
        store,
        neighborhoods=[(42, 84, 168), (52, 105, 210), (63, 126, 252), (75, 150, 300), (84, 168, 336)],
    )
    pbo_result = probability_of_backtest_overfitting(trial_returns, n_splits=10)
    print(json.dumps(pbo_result, indent=2))
    (REPORT_DIR / "pbo.json").write_text(json.dumps(pbo_result, indent=2))

    _print_header("Monte Carlo: block-bootstrap returns and trade-order permutation (baseline)")
    baseline_daily_returns = baseline_result.equity_curve.pct_change().dropna()
    block_sims = block_bootstrap_returns(
        baseline_daily_returns, n_simulations=500, block_size=21, seed=7
    )
    block_summary = summarize_simulations(block_sims, rolling_window=252)
    print("block-bootstrap:", json.dumps(block_summary, indent=2))

    # Trade-order permutation needs per-trade P&L, which this cost-only trade
    # log doesn't carry directly -- approximate with realized daily P&L on
    # days a trade occurred as a stand-in "trade outcome" sequence. This is a
    # documented simplification, not a precise per-trade P&L reconstruction.
    trade_dates = baseline_result.trade_log["date"].unique()
    trade_day_returns = baseline_daily_returns.reindex(pd.to_datetime(trade_dates)).dropna()
    permuted_sims = trade_order_permutation(trade_day_returns, n_simulations=500, seed=11)
    permuted_summary = summarize_simulations(permuted_sims, rolling_window=min(60, len(trade_day_returns)))
    print("trade-order permutation:", json.dumps(permuted_summary, indent=2))

    monte_carlo_results = {"block_bootstrap": block_summary, "trade_order_permutation": permuted_summary}
    (REPORT_DIR / "monte_carlo.json").write_text(json.dumps(monte_carlo_results, indent=2))

    tracker.record(
        ExperimentRecord(
            experiment_id="robustness_suite_v1_summary",
            hypothesis="Summary record for the full robustness suite run against synthetic data.",
            config={"n_trials_in_dsr_correction": len(trial_sharpes)},
            data_description="Synthetic data throughout -- pipeline/robustness-mechanics check, not evidence.",
            result={"baseline": baseline_metrics, "dsr": dsr, "pbo": pbo_result},
            conclusion=(
                "All sweeps executed without error. Numeric outcomes are not "
                "interpretable as evidence about the real trend hypothesis "
                "until real contract-level data replaces the synthetic "
                "source (Docs/Implementation_Spec.md S6.1/S8)."
            ),
        )
    )
    print(f"\nCSV/JSON artifacts written to {REPORT_DIR}/")


if __name__ == "__main__":
    main()
