import numpy as np
import pandas as pd

from trading_system.portfolio.blend import blend_sleeves, scale_to_vol_target
from trading_system.portfolio.covariance import (
    portfolio_vol_from_covariance,
    rolling_annualized_covariance,
)


def test_rolling_covariance_none_when_insufficient_history():
    returns = pd.DataFrame({"A": [0.01] * 10, "B": [0.02] * 10})
    assert rolling_annualized_covariance(returns, window_days=60) is None


def test_rolling_covariance_shape_and_symmetry():
    rng = np.random.default_rng(0)
    returns = pd.DataFrame(
        {"A": rng.normal(0, 0.01, 200), "B": rng.normal(0, 0.01, 200)}
    )
    cov = rolling_annualized_covariance(returns, window_days=60)
    assert cov is not None
    assert cov.shape == (2, 2)
    assert cov.loc["A", "B"] == cov.loc["B", "A"]


def test_portfolio_vol_from_covariance_diagonal_only():
    cov = pd.DataFrame({"A": [0.04, 0.0], "B": [0.0, 0.09]}, index=["A", "B"])
    vol = portfolio_vol_from_covariance({"A": 1.0, "B": 0.0}, cov)
    assert vol == 0.2  # sqrt(0.04)


def test_blend_sleeves_respects_risk_shares():
    sleeve_weights = {"S1": {"X": 1.0}, "S2": {"Y": 1.0}}
    risk_shares = {"S1": 0.5, "S2": 0.5}
    combined = blend_sleeves(sleeve_weights, risk_shares)
    assert combined == {"X": 0.5, "Y": 0.5}


def test_blend_sleeves_sums_overlapping_symbols():
    sleeve_weights = {"S1": {"X": 1.0}, "S2": {"X": -0.5}}
    risk_shares = {"S1": 0.5, "S2": 0.5}
    combined = blend_sleeves(sleeve_weights, risk_shares)
    assert combined["X"] == 0.25


def test_scale_to_vol_target_never_scales_up():
    weights = {"A": 0.1}
    cov = pd.DataFrame({"A": [0.0001]}, index=["A"])  # tiny estimated vol
    scaled = scale_to_vol_target(weights, cov, vol_target_annualized=0.10)
    # k = min(1, 0.10/0.01) = 1 -- capped at 1, not scaled up to 10x
    assert scaled["A"] == weights["A"]


def test_scale_to_vol_target_scales_down_when_too_risky():
    weights = {"A": 1.0}
    cov = pd.DataFrame({"A": [1.0]}, index=["A"])  # estimated vol = 1.0 (100%)
    scaled = scale_to_vol_target(weights, cov, vol_target_annualized=0.10)
    assert scaled["A"] == 0.10
