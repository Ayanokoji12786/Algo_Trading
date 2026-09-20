"""Runs the frozen baseline trend strategy against SYNTHETIC data end to end.

This proves the pipeline (data -> features -> strategy -> portfolio ->
backtest -> metrics) works and is leakage-safe. It is NOT a claim about the
researched trend hypothesis -- see Docs/Implementation_Spec.md S6.1. Real
replication requires real contract-level data, which this system does not
yet have.
"""
from __future__ import annotations

import dataclasses
import json

from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.metrics import compute_metrics
from trading_system.config.defaults import default_config
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.experiments.tracker import ExperimentRecord, ExperimentTracker
from trading_system.strategies.trend import TrendStrategy


def main() -> None:
    config = default_config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)
    strategy = TrendStrategy(config.trend)

    engine = BacktestEngine(config, store, strategy)
    result = engine.run()
    metrics = compute_metrics(result.equity_curve, result.turnover)

    print("=== SYNTHETIC-DATA PIPELINE CHECK (not a performance claim) ===")
    print(json.dumps(metrics, indent=2))

    tracker = ExperimentTracker("experiments/log.jsonl")
    tracker.record(
        ExperimentRecord(
            experiment_id="baseline_synthetic_v1",
            hypothesis=(
                "The frozen 63/126/252 trend ensemble, vol-scaled and "
                "risk-equalized, executes without look-ahead and produces a "
                "coherent equity curve on synthetic regime-switching data."
            ),
            config={
                "trend": dataclasses.asdict(config.trend),
                "risk": dataclasses.asdict(config.risk),
                "cost": dataclasses.asdict(config.cost),
                "data": {**dataclasses.asdict(config.data), "start_date": str(config.data.start_date), "end_date": str(config.data.end_date)},
                "backtest": dataclasses.asdict(config.backtest),
            },
            data_description="Synthetic regime-switching random walks (see data/synthetic.py) -- NOT real market data.",
            result=metrics,
            conclusion=(
                "Pipeline runs end-to-end and is a code-correctness check "
                "only. No claim about the real-world trend hypothesis can "
                "be made until real contract-level data is wired in."
            ),
        )
    )


if __name__ == "__main__":
    main()
