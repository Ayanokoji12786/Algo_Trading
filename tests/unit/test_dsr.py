import numpy as np
import pandas as pd

from trading_system.backtest.dsr import deflated_sharpe_ratio, expected_max_sharpe_under_null


def test_expected_max_sharpe_zero_for_single_trial():
    assert expected_max_sharpe_under_null(sharpe_std_across_trials=0.5, n_trials=1) == 0.0


def test_expected_max_sharpe_increases_with_more_trials():
    small = expected_max_sharpe_under_null(0.5, n_trials=5)
    large = expected_max_sharpe_under_null(0.5, n_trials=500)
    assert large > small > 0


def test_dsr_lower_when_more_trials_searched_for_same_observed_sharpe():
    rng = np.random.default_rng(0)
    daily_returns = pd.Series(rng.normal(0.0005, 0.01, 1000))
    selected_sharpe = 1.0

    few_trials = pd.Series([0.2, 0.5, 1.0])
    many_trials = pd.Series(list(rng.normal(0.3, 0.4, 200)) + [1.0])

    dsr_few = deflated_sharpe_ratio(few_trials, selected_sharpe, daily_returns)
    dsr_many = deflated_sharpe_ratio(many_trials, selected_sharpe, daily_returns)

    assert dsr_many["deflated_sharpe_probability"] < dsr_few["deflated_sharpe_probability"]
    assert dsr_many["n_trials"] == 201
    assert dsr_few["n_trials"] == 3


def test_dsr_is_a_probability():
    rng = np.random.default_rng(1)
    daily_returns = pd.Series(rng.normal(0.0003, 0.01, 500))
    trials = pd.Series([0.1, 0.4, 0.8])
    result = deflated_sharpe_ratio(trials, 0.8, daily_returns)
    assert 0.0 <= result["deflated_sharpe_probability"] <= 1.0
