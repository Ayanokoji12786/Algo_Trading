"""Parameter-neighborhood and leave-one-out robustness sweeps
(Prompt.md S21: "prefer robust plateaus over isolated peaks", S24 stress
testing, S16 cost scenarios).

Every sweep function here runs multiple full backtests against the SAME
already-built data source/store (never regenerating synthetic data with
different parameters -- see data/filtered.py's docstring for why that would
contaminate the comparison) and logs each run to the ExperimentTracker, per
Prompt.md S26's requirement not to hide unsuccessful configurations.
"""
from __future__ import annotations

import dataclasses

import pandas as pd

from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.metrics import compute_metrics
from trading_system.config.schema import SystemConfig
from trading_system.data.filtered import FilteredDataSource
from trading_system.data.interfaces import DataSource
from trading_system.data.pit_store import PointInTimeStore
from trading_system.experiments.tracker import ExperimentRecord, ExperimentTracker
from trading_system.strategies.trend import TrendStrategy


def _run_once(config: SystemConfig, store: PointInTimeStore) -> dict[str, float]:
    strategy = TrendStrategy(config.trend)
    result = BacktestEngine(config, store, strategy).run()
    return compute_metrics(result.equity_curve, result.turnover)


def _log(
    tracker: ExperimentTracker | None,
    experiment_id: str,
    hypothesis: str,
    config: SystemConfig,
    varied: dict,
    metrics: dict,
) -> None:
    if tracker is None:
        return
    tracker.record(
        ExperimentRecord(
            experiment_id=experiment_id,
            hypothesis=hypothesis,
            config={"varied": varied},
            data_description="Synthetic data -- pipeline/robustness-mechanics check, not evidence.",
            result=metrics,
            conclusion="Logged as part of a robustness sweep; see the sweep's aggregate table for interpretation.",
        )
    )


def lookback_neighborhood_sweep(
    base_config: SystemConfig,
    store: PointInTimeStore,
    neighborhoods: list[tuple[int, ...]],
    tracker: ExperimentTracker | None = None,
) -> pd.DataFrame:
    rows = []
    for lb in neighborhoods:
        cfg = dataclasses.replace(
            base_config, trend=dataclasses.replace(base_config.trend, lookback_days=lb)
        )
        metrics = _run_once(cfg, store)
        rows.append({"lookback_days": str(lb), **metrics})
        _log(
            tracker,
            "robustness_lookback_sweep",
            "Neighboring lookback horizons should behave similarly to the frozen 63/126/252 baseline (a broad plateau, not an isolated peak).",
            cfg,
            {"lookback_days": lb},
            metrics,
        )
    return pd.DataFrame(rows)


def vol_window_sweep(
    base_config: SystemConfig,
    store: PointInTimeStore,
    windows: list[int],
    tracker: ExperimentTracker | None = None,
) -> pd.DataFrame:
    rows = []
    for w in windows:
        cfg = dataclasses.replace(
            base_config, trend=dataclasses.replace(base_config.trend, vol_window_days=w)
        )
        metrics = _run_once(cfg, store)
        rows.append({"vol_window_days": w, **metrics})
        _log(
            tracker,
            "robustness_vol_window_sweep",
            "Neighboring EWMA vol windows around the 60-day default should behave similarly.",
            cfg,
            {"vol_window_days": w},
            metrics,
        )
    return pd.DataFrame(rows)


def cost_scenario_sweep(
    base_config: SystemConfig,
    store: PointInTimeStore,
    tracker: ExperimentTracker | None = None,
) -> pd.DataFrame:
    rows = []
    for scenario in ("base", "stress_2x", "stress_3x"):
        cfg = dataclasses.replace(
            base_config, cost=dataclasses.replace(base_config.cost, scenario=scenario)
        )
        metrics = _run_once(cfg, store)
        rows.append({"cost_scenario": scenario, **metrics})
        _log(
            tracker,
            "robustness_cost_scenario_sweep",
            "The strategy must remain viable (or its degradation must be reported honestly) under 2x/3x cost stress, per Research.md's cost model requirement.",
            cfg,
            {"cost_scenario": scenario},
            metrics,
        )
    return pd.DataFrame(rows)


def execution_delay_sweep(
    base_config: SystemConfig,
    store: PointInTimeStore,
    delays: list[int] = (0, 1, 2),
    tracker: ExperimentTracker | None = None,
) -> pd.DataFrame:
    rows = []
    for delay in delays:
        cfg = dataclasses.replace(
            base_config,
            backtest=dataclasses.replace(base_config.backtest, execution_delay_sessions=delay),
        )
        metrics = _run_once(cfg, store)
        rows.append({"execution_delay_sessions": delay, **metrics})
        _log(
            tracker,
            "robustness_execution_delay_sweep",
            "Research.md requires testing +1/+2 session execution delays as a fragility check.",
            cfg,
            {"execution_delay_sessions": delay},
            metrics,
        )
    return pd.DataFrame(rows)


def rebalance_frequency_sweep(
    base_config: SystemConfig,
    store: PointInTimeStore,
    tracker: ExperimentTracker | None = None,
) -> pd.DataFrame:
    rows = []
    for freq in ("weekly", "daily"):
        cfg = dataclasses.replace(
            base_config, backtest=dataclasses.replace(base_config.backtest, rebalance_frequency=freq)
        )
        metrics = _run_once(cfg, store)
        rows.append({"rebalance_frequency": freq, **metrics})
        _log(
            tracker,
            "robustness_rebalance_frequency_sweep",
            "Research.md frames weekly as baseline but requires comparing against daily as a robustness/cost experiment.",
            cfg,
            {"rebalance_frequency": freq},
            metrics,
        )
    return pd.DataFrame(rows)


def leave_one_asset_class_out(
    base_config: SystemConfig,
    source: DataSource,
    tracker: ExperimentTracker | None = None,
) -> pd.DataFrame:
    rows = []
    full_store = PointInTimeStore(source)
    rows.append({"excluded_asset_class": "none", **_run_once(base_config, full_store)})
    for asset_class in base_config.data.asset_classes:
        filtered = FilteredDataSource(source, excluded_asset_classes=frozenset({asset_class}))
        store = PointInTimeStore(filtered)
        metrics = _run_once(base_config, store)
        rows.append({"excluded_asset_class": asset_class, **metrics})
        _log(
            tracker,
            "robustness_leave_one_asset_class_out",
            f"Portfolio performance should not collapse when {asset_class} is removed -- if it does, that class was carrying the whole result.",
            base_config,
            {"excluded_asset_class": asset_class},
            metrics,
        )
    return pd.DataFrame(rows)


def leave_one_instrument_out(
    base_config: SystemConfig,
    source: DataSource,
    tracker: ExperimentTracker | None = None,
) -> pd.DataFrame:
    rows = []
    full_store = PointInTimeStore(source)
    rows.append({"excluded_symbol": "none", **_run_once(base_config, full_store)})
    for meta in full_store.universe:
        filtered = FilteredDataSource(source, excluded_symbols=frozenset({meta.symbol}))
        store = PointInTimeStore(filtered)
        metrics = _run_once(base_config, store)
        rows.append({"excluded_symbol": meta.symbol, **metrics})
        _log(
            tracker,
            "robustness_leave_one_instrument_out",
            f"Portfolio performance should not depend heavily on {meta.symbol} alone.",
            base_config,
            {"excluded_symbol": meta.symbol},
            metrics,
        )
    return pd.DataFrame(rows)
