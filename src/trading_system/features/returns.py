from __future__ import annotations

import numpy as np
import pandas as pd


def log_return(close: pd.Series, lookback_days: int) -> float | None:
    """Log return over the trailing ``lookback_days`` bars of ``close``.

    ``close`` must already end at the last bar the caller is allowed to see
    (enforced upstream by PointInTimeStore.history_as_of) -- this function
    has no notion of "now" and cannot itself introduce look-ahead.
    Returns None if there isn't enough history yet.
    """
    if len(close) <= lookback_days:
        return None
    recent = close.iloc[-1]
    past = close.iloc[-(lookback_days + 1)]
    if past <= 0 or recent <= 0:
        return None
    return float(np.log(recent / past))


def sign(x: float | None) -> float | None:
    if x is None:
        return None
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return 0.0
