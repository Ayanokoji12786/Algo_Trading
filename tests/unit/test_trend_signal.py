import numpy as np
import pandas as pd

from trading_system.features.trend_signal import composite_trend_score


def test_composite_score_none_until_full_history():
    close = pd.Series(np.linspace(100, 110, 100))
    assert composite_trend_score(close, (63, 126, 252)) is None


def test_composite_score_all_positive():
    close = pd.Series(np.linspace(100, 400, 260))  # strictly increasing
    score = composite_trend_score(close, (63, 126, 252))
    assert score == 1.0


def test_composite_score_all_negative():
    close = pd.Series(np.linspace(400, 100, 260))  # strictly decreasing
    score = composite_trend_score(close, (63, 126, 252))
    assert score == -1.0


def test_composite_score_mixed():
    n = 260
    close = pd.Series(np.linspace(100, 400, n))
    close.iloc[-1] = close.iloc[-64] * 0.99  # 63d return negative, longer ones positive
    score = composite_trend_score(close, (63, 126, 252))
    assert score is not None
    assert -1.0 < score < 1.0
