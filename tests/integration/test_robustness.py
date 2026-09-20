import tempfile
from datetime import date
from pathlib import Path

from trading_system.backtest import robustness
from trading_system.backtest.dsr import deflated_sharpe_ratio
from trading_system.config.schema import DataConfig, SystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.experiments.tracker import ExperimentTracker


def _small_config() -> SystemConfig:
    data = DataConfig(
        asset_classes=("equity_index", "fx"),
        instruments_per_asset_class=2,
        start_date=date(2015, 1, 1),
        end_date=date(2019, 12, 31),
        random_seed=11,
    )
    return SystemConfig(data=data)


def test_lookback_and_vol_sweeps_produce_a_row_per_variant():
    config = _small_config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)

    lookback_df = robustness.lookback_neighborhood_sweep(
        config, store, neighborhoods=[(42, 84, 168), (63, 126, 252), (84, 168, 336)]
    )
    assert len(lookback_df) == 3
    assert set(lookback_df["lookback_days"]) == {"(42, 84, 168)", "(63, 126, 252)", "(84, 168, 336)"}

    vol_df = robustness.vol_window_sweep(config, store, windows=[40, 60, 90])
    assert len(vol_df) == 3


def test_cost_and_delay_sweeps_show_expected_direction():
    config = _small_config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)

    cost_df = robustness.cost_scenario_sweep(config, store).set_index("cost_scenario")
    # Higher-cost scenarios must never produce a *higher* total return than
    # the base scenario for an identical signal/position sequence.
    assert cost_df.loc["stress_3x", "total_return"] <= cost_df.loc["base", "total_return"]

    delay_df = robustness.execution_delay_sweep(config, store, delays=[0, 1, 2])
    assert len(delay_df) == 3


def test_leave_one_out_sweeps_run_for_every_bucket_and_instrument():
    config = _small_config()
    source = SyntheticFuturesDataSource(config.data)

    ac_df = robustness.leave_one_asset_class_out(config, source)
    assert set(ac_df["excluded_asset_class"]) == {"none", "equity_index", "fx"}

    inst_df = robustness.leave_one_instrument_out(config, source)
    full_store = PointInTimeStore(source)
    expected_symbols = {"none"} | {m.symbol for m in full_store.universe}
    assert set(inst_df["excluded_symbol"]) == expected_symbols


def test_sweeps_are_logged_to_the_experiment_tracker():
    config = _small_config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "log.jsonl"
        tracker = ExperimentTracker(log_path)
        robustness.cost_scenario_sweep(config, store, tracker=tracker)
        records = tracker.all_records()
        assert len(records) == 3  # base, stress_2x, stress_3x -- none hidden


def test_dsr_can_be_computed_from_a_real_sweep():
    config = _small_config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)

    sweep = robustness.lookback_neighborhood_sweep(
        config,
        store,
        neighborhoods=[(42, 84, 168), (63, 126, 252), (84, 168, 336), (100, 200, 300)],
    )
    strategy_returns = store.close_matrix().pct_change().mean(axis=1).dropna()
    result = deflated_sharpe_ratio(
        trial_sharpes=sweep["sharpe"],
        selected_sharpe=float(sweep.loc[sweep["lookback_days"] == "(63, 126, 252)", "sharpe"].iloc[0]),
        daily_returns=strategy_returns,
    )
    assert result["n_trials"] == 4
    assert 0.0 <= result["deflated_sharpe_probability"] <= 1.0
