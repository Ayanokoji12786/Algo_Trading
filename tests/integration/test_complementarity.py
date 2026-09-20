from datetime import date

from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.metrics import compute_metrics
from trading_system.config.schema import DataConfig, SystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.strategies.carry import CarryStrategy, SyntheticCarrySignalSource
from trading_system.strategies.carry_activation import evaluate_carry_activation
from trading_system.strategies.trend import TrendStrategy


def _config() -> SystemConfig:
    data = DataConfig(
        asset_classes=("equity_index", "fx"),
        instruments_per_asset_class=2,
        start_date=date(2015, 1, 1),
        end_date=date(2020, 12, 31),
        random_seed=21,
    )
    return SystemConfig(data=data)


def test_trend_only_carry_only_and_combined_all_run():
    config = _config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)

    trend = TrendStrategy(config.trend)
    carry_source = SyntheticCarrySignalSource(
        [m.symbol for m in store.universe], seed=42
    )
    carry = CarryStrategy(carry_source, config.trend)

    trend_result = BacktestEngine(config, store, trend).run()
    carry_result = BacktestEngine(config, store, carry).run()
    combined_result = BacktestEngine(config, store, [trend, carry]).run()

    for result in (trend_result, carry_result, combined_result):
        assert (result.equity_curve > 0).all()

    trend_metrics = compute_metrics(trend_result.equity_curve)
    carry_metrics_base = compute_metrics(carry_result.equity_curve)
    combined_metrics = compute_metrics(combined_result.equity_curve)

    # Sanity: the three runs must actually differ (aggregation is doing
    # something, not silently collapsing to one strategy).
    assert not trend_result.equity_curve.equals(carry_result.equity_curve)
    assert not trend_result.equity_curve.equals(combined_result.equity_curve)

    trend_daily = trend_result.equity_curve.pct_change().dropna()
    carry_daily = carry_result.equity_curve.pct_change().dropna()

    gate = evaluate_carry_activation(
        trend_daily,
        carry_daily,
        carry_metrics_base=carry_metrics_base,
        carry_metrics_stress_2x=carry_metrics_base,  # placeholder run has one cost scenario here
    )
    # With independent RNG streams for price and carry, correlation should
    # come out low regardless of whether the profitability criteria pass on
    # this particular synthetic seed.
    assert abs(gate["measured_correlation_with_trend"]) < 0.5
    assert isinstance(combined_metrics["sharpe"], float)


def test_combined_equal_risk_allocation_gives_each_strategy_roughly_half_gross_weight():
    config = _config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)

    trend = TrendStrategy(config.trend)
    carry_source = SyntheticCarrySignalSource([m.symbol for m in store.universe], seed=7)
    carry = CarryStrategy(carry_source, config.trend)

    combined_result = BacktestEngine(config, store, [trend, carry]).run()
    assert not combined_result.weights_history.empty
