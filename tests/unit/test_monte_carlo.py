import numpy as np
import pandas as pd

from trading_system.backtest.monte_carlo import (
    block_bootstrap_returns,
    summarize_simulations,
    trade_order_permutation,
)


def test_block_bootstrap_shape_and_reproducibility():
    returns = pd.Series(np.random.default_rng(0).normal(0.0005, 0.01, 500))
    sims_a = block_bootstrap_returns(returns, n_simulations=50, block_size=20, seed=1)
    sims_b = block_bootstrap_returns(returns, n_simulations=50, block_size=20, seed=1)
    assert sims_a.shape == (50, 500)
    np.testing.assert_array_equal(sims_a, sims_b)  # same seed -> reproducible


def test_block_bootstrap_preserves_the_actual_value_set_within_blocks():
    # Every simulated value must come from the original series -- block
    # bootstrap resamples existing observations, it doesn't invent new ones.
    returns = pd.Series(np.arange(100) / 1000.0)
    sims = block_bootstrap_returns(returns, n_simulations=5, block_size=10, seed=0)
    original_values = set(returns.to_numpy().round(6))
    assert set(sims.flatten().round(6)).issubset(original_values)


def test_trade_order_permutation_preserves_the_multiset_of_trades():
    trades = pd.Series([0.05, -0.02, 0.01, -0.10, 0.03])
    sims = trade_order_permutation(trades, n_simulations=20, seed=0)
    for row in sims:
        assert sorted(row) == sorted(trades.to_numpy())


def test_trade_order_permutation_changes_the_order():
    trades = pd.Series(np.arange(50) / 100.0)
    sims = trade_order_permutation(trades, n_simulations=1, seed=0)
    assert not np.array_equal(sims[0], trades.to_numpy())


def test_summarize_simulations_reports_percentile_bands():
    rng = np.random.default_rng(0)
    sims = rng.normal(0.0003, 0.01, size=(200, 300))
    summary = summarize_simulations(sims, rolling_window=60)
    assert summary["n_simulations"] == 200
    for key in ("terminal_return", "max_drawdown", "worst_rolling_window_return"):
        band = summary[key]
        assert band["p5"] <= band["p50"] <= band["p95"]


def test_summarize_simulations_max_drawdown_is_never_positive():
    rng = np.random.default_rng(1)
    sims = rng.normal(-0.001, 0.02, size=(100, 250))
    summary = summarize_simulations(sims)
    assert summary["max_drawdown"]["p95"] <= 0.0
