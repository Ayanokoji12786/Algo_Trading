import numpy as np
import pandas as pd

from trading_system.features.regime import (
    average_pairwise_correlation,
    cross_asset_trend_dispersion,
    trailing_vol_percentile,
)


def test_trailing_vol_percentile_low_and_high():
    history = pd.Series(np.linspace(0.05, 0.30, 100))
    assert trailing_vol_percentile(history, current_vol=0.01) == 0.0
    assert trailing_vol_percentile(history, current_vol=1.0) == 1.0


def test_trailing_vol_percentile_none_with_short_history():
    history = pd.Series([0.1, 0.2])
    assert trailing_vol_percentile(history, current_vol=0.15) is None


def test_cross_asset_trend_dispersion_zero_when_all_agree():
    scores = {"A": 1.0, "B": 1.0, "C": 1.0}
    assert cross_asset_trend_dispersion(scores) == 0.0


def test_cross_asset_trend_dispersion_positive_when_mixed():
    scores = {"A": 1.0, "B": -1.0, "C": 0.0}
    dispersion = cross_asset_trend_dispersion(scores)
    assert dispersion is not None and dispersion > 0


def test_cross_asset_trend_dispersion_none_with_one_instrument():
    assert cross_asset_trend_dispersion({"A": 1.0}) is None


def test_average_pairwise_correlation_high_for_identical_series():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.01, 200)
    returns = pd.DataFrame({"A": base, "B": base, "C": base})
    corr = average_pairwise_correlation(returns, window_days=100)
    assert corr is not None and corr > 0.99


def test_average_pairwise_correlation_low_for_independent_series():
    rng = np.random.default_rng(1)
    returns = pd.DataFrame(
        {
            "A": rng.normal(0, 0.01, 300),
            "B": rng.normal(0, 0.01, 300),
            "C": rng.normal(0, 0.01, 300),
        }
    )
    corr = average_pairwise_correlation(returns, window_days=250)
    assert corr is not None and abs(corr) < 0.3


def test_average_pairwise_correlation_none_with_single_instrument():
    returns = pd.DataFrame({"A": np.random.default_rng(0).normal(0, 0.01, 200)})
    assert average_pairwise_correlation(returns, window_days=100) is None
