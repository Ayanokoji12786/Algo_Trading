"""Direction sanity checks -- not part of the regular pipeline suite, but a
deliberate due-diligence step before trusting any aggregate backtest number
(Prompt.md S37: distrust results, don't rationalize them). If the frozen
trend baseline can't make money on an unambiguous, low-noise, single-
direction monotonic trend after realistic (indeed, near-zero) costs, that
indicates a sign/wiring bug somewhere in signal generation, sizing, or the
engine's return application -- not a fact about the strategy's real-world
merit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_system.backtest.engine import BacktestEngine
from trading_system.backtest.metrics import compute_metrics
from trading_system.config.schema import CostConfig, DataConfig, SystemConfig
from trading_system.data.interfaces import ContractMeta
from trading_system.data.pit_store import PointInTimeStore
from trading_system.strategies.trend import TrendStrategy


class _MonotonicSource:
    """A single instrument that rises steadily with tiny noise for its
    entire history -- the least ambiguous possible "should be long and
    should make money" case for a trend follower.
    """

    def __init__(self, direction: float = 1.0, n_days: int = 1500, seed: int = 0):
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range("2010-01-01", periods=n_days)
        drift = direction * 0.0006  # ~15%/yr, comfortably above noise
        noise = rng.normal(0.0, 0.004, n_days)
        close = 100.0 * np.exp(np.cumsum(drift + noise))
        self._df = pd.DataFrame(
            {
                "open": close,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": 1e5,
            },
            index=dates,
        )

    def get_universe(self):
        return [ContractMeta(symbol="MONO", asset_class="equity_index")]

    def get_prices(self, symbol):
        return self._df.copy()


@pytest.mark.parametrize("direction,expect_positive", [(1.0, True), (-1.0, True)])
def test_trend_strategy_profits_from_an_unambiguous_trend_after_near_zero_costs(
    direction, expect_positive
):
    """A steady uptrend should make the strategy go long and profit; a
    steady downtrend should make it go short and ALSO profit (a correct
    trend follower doesn't care about the sign of the move, only whether it
    correctly detects and follows it). Costs are set near zero here so
    transaction-cost drag can't mask a directional bug.
    """
    config = SystemConfig(
        data=DataConfig(asset_classes=("equity_index",), instruments_per_asset_class=1),
        cost=CostConfig(bps_by_asset_class={"equity_index": 0.01}, scenario="base"),
    )
    source = _MonotonicSource(direction=direction)
    store = PointInTimeStore(source)
    strategy = TrendStrategy(config.trend)

    result = BacktestEngine(config, store, strategy).run()
    metrics = compute_metrics(result.equity_curve, result.turnover)

    assert metrics["sharpe"] > 0.5, (
        f"Expected a clearly positive Sharpe on an unambiguous "
        f"{'up' if direction > 0 else 'down'}trend with near-zero costs, "
        f"got {metrics['sharpe']!r} -- check for a sign/wiring bug before "
        f"trusting any synthetic-data backtest result."
    )
    assert metrics["total_return"] > 0


def test_trend_strategy_goes_long_on_uptrend_and_short_on_downtrend():
    """Directly inspects the generated signal/position sign, independent of
    P&L, to localize a bug to signal generation vs. execution if one exists.
    """
    config = SystemConfig(
        data=DataConfig(asset_classes=("equity_index",), instruments_per_asset_class=1)
    )
    up_store = PointInTimeStore(_MonotonicSource(direction=1.0))
    down_store = PointInTimeStore(_MonotonicSource(direction=-1.0))
    strategy = TrendStrategy(config.trend)

    as_of = up_store.trading_calendar()[-1]
    up_signal = strategy.generate_signals(up_store, as_of)[0]
    down_signal = strategy.generate_signals(down_store, as_of)[0]

    assert up_signal.direction > 0
    assert down_signal.direction < 0
