import dataclasses
from datetime import date

from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.metrics import compute_metrics
from trading_system.config.schema import DataConfig, SystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.strategies.trend import TrendStrategy


def _small_config() -> SystemConfig:
    data = DataConfig(
        asset_classes=("equity_index", "fx"),
        instruments_per_asset_class=2,
        start_date=date(2015, 1, 1),
        end_date=date(2019, 12, 31),
        random_seed=7,
    )
    return SystemConfig(data=data)


def test_pipeline_runs_end_to_end_and_produces_sane_metrics():
    config = _small_config()
    source = SyntheticFuturesDataSource(config.data)
    store = PointInTimeStore(source)
    strategy = TrendStrategy(config.trend)

    engine = BacktestEngine(config, store, strategy)
    result = engine.run()

    assert len(result.equity_curve) > 1000
    assert (result.equity_curve > 0).all()  # no blow-up / negative NAV
    assert not result.trade_log.empty

    metrics = compute_metrics(result.equity_curve, result.turnover)
    assert metrics["annualized_vol"] > 0
    # Risk targeting should put realized vol in the right order of
    # magnitude given a 10% target, zero-correlation sizing assumption,
    # and instrument/asset-class caps -- this is a sanity band, not a
    # precise equality (caps and imperfect correlation assumptions mean it
    # won't be exact).
    assert 0.0 < metrics["annualized_vol"] < 0.40


def test_execution_delay_shifts_returns_without_changing_signal_generation():
    """Regression guard for look-ahead: changing execution_delay_sessions
    must change *when* a given target weight starts affecting NAV, but must
    not change the sequence of target weights computed at each decision
    date (which depends only on information as-of the prior session).
    """
    base_config = _small_config()
    delayed_config = dataclasses.replace(
        base_config,
        backtest=dataclasses.replace(base_config.backtest, execution_delay_sessions=2),
    )

    source = SyntheticFuturesDataSource(base_config.data)
    store = PointInTimeStore(source)

    base_result = BacktestEngine(
        base_config, store, TrendStrategy(base_config.trend)
    ).run()
    delayed_result = BacktestEngine(
        delayed_config, store, TrendStrategy(delayed_config.trend)
    ).run()

    # Signal generation is a pure function of (store, as_of), independent of
    # execution_delay_sessions, so every weight vector the delayed run
    # produces must also appear in the base run's set. The reverse need not
    # hold: near the end of the date range, a longer delay can legitimately
    # push execution past the last available session, dropping that
    # rebalance entirely -- that's an edge effect of a finite calendar, not
    # a signal-generation discrepancy.
    base_weight_sets = {
        tuple(sorted(row.dropna().round(6).items()))
        for _, row in base_result.weights_history.iterrows()
    }
    delayed_weight_sets = {
        tuple(sorted(row.dropna().round(6).items()))
        for _, row in delayed_result.weights_history.iterrows()
    }
    assert delayed_weight_sets.issubset(base_weight_sets)
    assert len(delayed_weight_sets) > 0

    # And the equity curves should differ (delay is not a no-op).
    assert not base_result.equity_curve.equals(delayed_result.equity_curve)


def test_signal_at_decision_date_is_unaffected_by_data_after_it():
    """Direct leakage probe: a store that only ever contains rows up to a
    cutoff must produce the exact same signal, at that same cutoff, as a
    store that also holds (but should never read) rows after it.

    Uses two stores built from the *same* underlying prices (one truncated
    by slicing, not by regenerating synthetic data with a different date
    range/seed-consuming path) so any difference can only come from the
    strategy/feature code reading beyond its as_of date -- not from the
    synthetic generator producing different random data for a shorter range.
    """
    config = _small_config()
    full_source = SyntheticFuturesDataSource(config.data)
    universe = full_source.get_universe()
    full_prices = {meta.symbol: full_source.get_prices(meta.symbol) for meta in universe}

    class _FullSource:
        def get_universe(self):
            return universe

        def get_prices(self, symbol):
            return full_prices[symbol].copy()

    full_store = PointInTimeStore(_FullSource())
    calendar = full_store.trading_calendar()
    cutoff = calendar[len(calendar) // 2]

    class _TruncatedSource:
        def get_universe(self):
            return universe

        def get_prices(self, symbol):
            df = full_prices[symbol]
            return df.loc[df.index <= cutoff].copy()

    truncated_store = PointInTimeStore(_TruncatedSource())
    strategy = TrendStrategy(config.trend)

    full_signals = {
        s.symbol: s.direction for s in strategy.generate_signals(full_store, cutoff)
    }
    truncated_signals = {
        s.symbol: s.direction
        for s in strategy.generate_signals(truncated_store, cutoff)
    }

    assert full_signals == truncated_signals
    assert len(full_signals) > 0
