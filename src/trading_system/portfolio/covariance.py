"""Rolling covariance-based portfolio volatility estimate
(Docs/India_Implementation_Spec.md RISK_01: sigma_p = sqrt(252 * w^T Sigma w),
"estimate portfolio covariance only from past observations").

This is a real methodological upgrade over the global-futures system's
documented zero-correlation simplification (portfolio/sizing.py) -- used
ONLY by the new blended engine (backtest/blended_engine.py) for the India
system, so the original global-futures sizing path and its already-reported
results (Docs/Final_Report.md SS I-M) remain byte-for-byte unaffected.

Point-in-time responsibility is pushed to the caller by contract: the
`returns` DataFrame passed in must already end at the last date the caller
is allowed to use for a decision made "today" (i.e. the caller slices it,
this module does not know or enforce a decision date itself).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_TRADING_DAYS_PER_YEAR = 252


def rolling_annualized_covariance(returns: pd.DataFrame, window_days: int) -> pd.DataFrame | None:
    if len(returns) < window_days:
        return None
    window = returns.iloc[-window_days:]
    cov = window.cov() * _TRADING_DAYS_PER_YEAR
    return cov.fillna(0.0)


def portfolio_vol_from_covariance(weights: dict[str, float], cov: pd.DataFrame) -> float:
    symbols = [s for s in weights if s in cov.index]
    if not symbols:
        return 0.0
    w = np.array([weights[s] for s in symbols])
    sub_cov = cov.loc[symbols, symbols].to_numpy()
    variance = float(w @ sub_cov @ w)
    return float(np.sqrt(max(variance, 0.0)))
