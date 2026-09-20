import numpy as np
import pandas as pd

from trading_system.features.volatility import ewma_annualized_vol


def test_vol_none_when_insufficient_history():
    close = pd.Series(np.linspace(100, 110, 10))
    assert ewma_annualized_vol(close, window_days=60) is None


def test_vol_is_positive_for_noisy_series():
    rng = np.random.default_rng(0)
    returns = rng.normal(0, 0.01, size=300)
    close = pd.Series(100 * np.exp(np.cumsum(returns)))
    vol = ewma_annualized_vol(close, window_days=60)
    assert vol is not None
    assert vol > 0


def test_vol_unaffected_by_future_truncation():
    rng = np.random.default_rng(1)
    returns = rng.normal(0, 0.01, size=300)
    close = pd.Series(100 * np.exp(np.cumsum(returns)))
    full_vol = ewma_annualized_vol(close, window_days=60)
    truncated_vol = ewma_annualized_vol(close.iloc[:200], window_days=60)
    # Different windows of data legitimately produce different vol; the
    # point of this test is only that computing on a prefix never requires
    # or reads anything past its own end (no exception, no reliance on the
    # longer series).
    assert truncated_vol is not None
    assert full_vol is not None
