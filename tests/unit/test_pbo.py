import numpy as np
import pandas as pd

from trading_system.backtest.pbo import probability_of_backtest_overfitting


def test_pbo_high_for_pure_noise_trials():
    """With many purely-random, meaningless trials, whichever looks best
    in-sample has no real edge -- PBO should be close to 0.5 (a coin flip
    for whether the in-sample pick beats the out-of-sample median).
    """
    rng = np.random.default_rng(0)
    returns_matrix = pd.DataFrame(rng.normal(0, 0.01, size=(800, 20)))
    result = probability_of_backtest_overfitting(returns_matrix, n_splits=16)
    assert 0.3 < result["pbo"] < 0.8  # loose band -- exact value is noisy


def test_pbo_low_when_one_configuration_has_consistent_real_skill():
    """One configuration has a real, consistent positive drift throughout
    (both in-sample and out-of-sample); the rest are pure noise. The skilled
    configuration should usually be both the in-sample winner and rank well
    out-of-sample, so PBO should be low.
    """
    rng = np.random.default_rng(1)
    t = 800
    n_noise = 14
    noise = rng.normal(0.0, 0.01, size=(t, n_noise))
    skilled = rng.normal(0.003, 0.01, size=(t, 1))  # consistent positive drift throughout
    returns_matrix = pd.DataFrame(np.concatenate([noise, skilled], axis=1))
    result = probability_of_backtest_overfitting(returns_matrix, n_splits=16)
    assert result["pbo"] < 0.3


def test_raises_on_odd_n_splits():
    returns_matrix = pd.DataFrame(np.random.default_rng(0).normal(0, 0.01, (100, 5)))
    try:
        probability_of_backtest_overfitting(returns_matrix, n_splits=15)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_raises_when_too_few_observations_for_splits():
    returns_matrix = pd.DataFrame(np.random.default_rng(0).normal(0, 0.01, (5, 5)))
    try:
        probability_of_backtest_overfitting(returns_matrix, n_splits=16)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_result_reports_combination_count():
    rng = np.random.default_rng(2)
    returns_matrix = pd.DataFrame(rng.normal(0, 0.01, size=(320, 6)))
    result = probability_of_backtest_overfitting(returns_matrix, n_splits=8)
    from math import comb

    assert result["n_combinations"] == comb(8, 4)
