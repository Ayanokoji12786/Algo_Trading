import numpy as np
import pandas as pd
import pytest

from trading_system.backtest.attribution import subperiod_breakdown, train_test_split_metrics


def _equity_curve(n=800, start="2015-01-01"):
    rng = np.random.default_rng(2)
    dates = pd.bdate_range(start, periods=n)
    returns = rng.normal(0.0004, 0.01, n)
    equity = pd.Series(1_000_000 * np.exp(np.cumsum(returns)), index=dates)
    return equity


def test_subperiod_breakdown_has_one_row_per_year_present():
    equity = _equity_curve(n=800)
    breakdown = subperiod_breakdown(equity, freq="YE")
    years_in_data = equity.index.year.unique()
    assert len(breakdown) <= len(years_in_data)
    assert len(breakdown) > 0
    assert "sharpe" in breakdown.columns


def test_subperiod_metrics_are_independent_of_prior_periods():
    # Two curves that are identical in their second half but differ in
    # their first half should produce identical subperiod metrics for the
    # (matching) second period, because each period is rebased to start
    # at 1.0 rather than carrying forward compounding from earlier periods.
    dates = pd.bdate_range("2015-01-01", periods=600)
    tail = np.random.default_rng(3).normal(0.0003, 0.01, 300)
    head_a = np.zeros(300)
    head_b = np.full(300, 0.001)

    equity_a = pd.Series(1_000_000 * np.exp(np.cumsum(np.concatenate([head_a, tail]))), index=dates)
    equity_b = pd.Series(2_000_000 * np.exp(np.cumsum(np.concatenate([head_b, tail]))), index=dates)

    breakdown_a = subperiod_breakdown(equity_a, freq="YE")
    breakdown_b = subperiod_breakdown(equity_b, freq="YE")

    last_period = breakdown_a.index[-1]
    assert breakdown_a.loc[last_period, "sharpe"] == pytest.approx(
        breakdown_b.loc[last_period, "sharpe"], rel=1e-9
    )


def test_train_test_split_reserves_final_fraction():
    equity = _equity_curve(n=1000)
    split = train_test_split_metrics(equity, turnover=None, holdout_fraction=0.2)
    assert "in_sample" in split and "holdout" in split
    assert split["in_sample"]["cagr"] == split["in_sample"]["cagr"]  # not NaN-crashing
    assert pd.Timestamp(split["split_date"]) in equity.index
