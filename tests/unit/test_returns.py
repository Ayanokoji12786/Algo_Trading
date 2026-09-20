import numpy as np
import pandas as pd

from trading_system.features.returns import log_return, sign


def test_log_return_basic():
    close = pd.Series([100.0, 101.0, 102.0, 110.0])
    r = log_return(close, 2)
    # 2-day lookback from the last bar (110.0) is the price 2 bars earlier
    # (101.0), not the series' first value.
    assert r == np.log(110.0 / 101.0)


def test_log_return_insufficient_history_returns_none():
    close = pd.Series([100.0, 101.0])
    assert log_return(close, 5) is None


def test_log_return_ignores_data_beyond_series_end():
    # Simulates point-in-time slicing: the function only ever sees what it's
    # given, so truncating the series must not change earlier results.
    full = pd.Series([100.0, 105.0, 102.0, 130.0, 90.0])
    truncated = full.iloc[:3]
    assert log_return(truncated, 2) == np.log(102.0 / 100.0)


def test_sign():
    assert sign(0.5) == 1.0
    assert sign(-0.5) == -1.0
    assert sign(0.0) == 0.0
    assert sign(None) is None
