from __future__ import annotations

import pandas as pd

from trading_system.features.returns import log_return, sign


def composite_trend_score(close: pd.Series, lookback_days: tuple[int, ...]) -> float | None:
    """Research.md "Core trend signal":

        s = [sign(R_63) + sign(R_126) + sign(R_252)] / 3

    generalized to an arbitrary set of lookbacks so neighboring horizons can
    be swept as a robustness test without touching this function.

    Returns None (no position) until every lookback has enough history --
    this is a conservative choice (documented here, not silent) that delays
    trading a new instrument rather than computing a partial-information
    score from only some of the three horizons.
    """
    signs = []
    for lb in lookback_days:
        s = sign(log_return(close, lb))
        if s is None:
            return None
        signs.append(s)
    return sum(signs) / len(signs)
