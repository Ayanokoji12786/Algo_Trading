from __future__ import annotations

import numpy as np
import pandas as pd

_TRADING_DAYS_PER_YEAR = 252


def ewma_annualized_vol(close: pd.Series, window_days: int) -> float | None:
    """Annualized EWMA volatility of daily log returns.

    Implementation_Spec.md S5: the 60-day EWMA window is a testable default
    named by the research, not a fixed requirement -- window_days is a
    parameter so alternates can be swept (Prompt.md S21).

    ``close`` must already be PIT-sliced by the caller (see returns.py).
    """
    if len(close) < window_days + 1:
        return None
    log_returns = np.log(close / close.shift(1)).dropna()
    if len(log_returns) < 2:
        return None
    # span relates to the EWMA decay such that the window roughly matches
    # the requested lookback in "effective" observations.
    ewm_var = log_returns.ewm(span=window_days, min_periods=window_days).var()
    latest_var = ewm_var.iloc[-1]
    if pd.isna(latest_var):
        return None
    return float(np.sqrt(latest_var) * np.sqrt(_TRADING_DAYS_PER_YEAR))
