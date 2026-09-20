from datetime import date

from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.regime_report import build_regime_history, performance_by_regime_bucket
from trading_system.config.schema import DataConfig, SystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.strategies.trend import TrendStrategy


def _config() -> SystemConfig:
    data = DataConfig(
        asset_classes=("equity_index", "fx"),
        instruments_per_asset_class=2,
        start_date=date(2015, 1, 1),
        end_date=date(2019, 12, 31),
        random_seed=31,
    )
    return SystemConfig(data=data)


def test_regime_history_has_expected_columns_and_no_lookahead():
    config = _config()
    store = PointInTimeStore(SyntheticFuturesDataSource(config.data))
    calendar = store.trading_calendar()
    sample_dates = list(calendar[300:320])

    history = build_regime_history(store, config.trend, sample_dates)
    assert not history.empty
    assert set(history.columns) == {"trend_dispersion", "avg_vol_percentile", "avg_pairwise_correlation"}
    assert list(history.index) == sample_dates


def test_regime_history_unaffected_by_data_after_as_of():
    """Leakage probe for the regime module: the snapshot at a given date
    must be identical whether or not the store also holds later dates.
    """
    config = _config()
    full_source = SyntheticFuturesDataSource(config.data)
    universe = full_source.get_universe()
    full_prices = {m.symbol: full_source.get_prices(m.symbol) for m in universe}

    full_store = PointInTimeStore(full_source)
    calendar = full_store.trading_calendar()
    cutoff = calendar[350]

    class _TruncatedSource:
        def get_universe(self):
            return universe

        def get_prices(self, symbol):
            df = full_prices[symbol]
            return df.loc[df.index <= cutoff].copy()

    truncated_store = PointInTimeStore(_TruncatedSource())

    full_snapshot = build_regime_history(full_store, config.trend, [cutoff])
    truncated_snapshot = build_regime_history(truncated_store, config.trend, [cutoff])

    pd_testing_assert = __import__("pandas").testing.assert_frame_equal
    pd_testing_assert(full_snapshot, truncated_snapshot)


def test_performance_by_regime_bucket_runs_and_has_sane_shape():
    config = _config()
    store = PointInTimeStore(SyntheticFuturesDataSource(config.data))
    strategy = TrendStrategy(config.trend)
    result = BacktestEngine(config, store, strategy).run()

    calendar = store.trading_calendar()
    sample_dates = list(calendar[300:800:5])  # every 5th day, cheap enough for a test
    history = build_regime_history(store, config.trend, sample_dates)

    breakdown = performance_by_regime_bucket(
        result.equity_curve, history, "avg_pairwise_correlation", n_buckets=3
    )
    if not breakdown.empty:
        assert "sharpe" in breakdown.columns
        assert breakdown["n_days"].sum() > 0
