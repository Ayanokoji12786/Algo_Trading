import numpy as np
import pandas as pd
import pytest

from trading_system.features.volatility import ewma_annualized_vol, realized_annualized_vol


def test_realized_vol_none_when_insufficient_history():
    close = pd.Series(np.linspace(100, 110, 10))
    assert realized_annualized_vol(close, window_days=60) is None


def test_realized_vol_positive_for_noisy_series():
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.01, 300)
    close = pd.Series(100 * np.exp(np.cumsum(returns)))
    vol = realized_annualized_vol(close, window_days=60)
    assert vol is not None and vol > 0


def test_realized_vol_matches_manual_calc():
    rng = np.random.default_rng(1)
    returns = rng.normal(0, 0.01, 100)
    close = pd.Series(100 * np.exp(np.cumsum(returns)))
    vol = realized_annualized_vol(close, window_days=60)
    manual_returns = np.diff(np.log(close.to_numpy()))[-60:]
    expected = manual_returns.std(ddof=1) * np.sqrt(252)
    assert vol == pytest.approx(expected, rel=1e-9)


def test_realized_and_ewma_differ_for_a_trending_series():
    # Not a claim that one is "more correct" -- just confirms they are
    # genuinely different estimators, per Docs/India_Implementation_Spec.md's
    # explicit instruction not to silently treat them as interchangeable.
    rng = np.random.default_rng(2)
    returns = rng.normal(0.001, 0.015, 200)
    close = pd.Series(100 * np.exp(np.cumsum(returns)))
    realized = realized_annualized_vol(close, window_days=60)
    ewma = ewma_annualized_vol(close, window_days=60)
    assert realized is not None and ewma is not None
    assert realized != ewma
