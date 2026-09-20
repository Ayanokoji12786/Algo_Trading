"""Regime diagnostics -- Research.md "Regime detection": "Calculate but do
not trade on... trailing realised-volatility percentile; trend strength and
cross-asset trend dispersion; average cross-asset correlation... bond term
spread; liquidity proxies; inflation/rate regime variables." Flagged as the
single largest gap in Docs/Final_Report.md S F/N: this module closes the
part of that gap computable from price data alone.

STRICT SCOPE: these functions produce DIAGNOSTICS ONLY. None of them are
wired into any strategy's sizing or signal generation -- Research.md is
explicit that generation one uses continuous volatility-based risk scaling
(already implemented in portfolio/sizing.py), not a fitted regime switch,
and that a hard regime filter "is approved only after proving OOS marginal
benefit versus the identical strategy without it," which has not been
attempted. Wiring these into a strategy without that validation would
silently violate that instruction -- so intentionally, nothing in this
codebase currently imports this module except its own tests and a
reporting CLI.

NOT COMPUTABLE from what this system has (flagged, not fabricated): equity
CAPE/dividend-yield states, bond term spread, inflation/rate regime
variables, and liquidity proxies all require real external data (macro
series, cross-market reference rates) this system does not have. Only the
price-derived diagnostics below are implemented.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def trailing_vol_percentile(vol_history: pd.Series, current_vol: float) -> float | None:
    """Percentile rank (0-1) of current_vol within vol_history's own trailing
    distribution -- "is volatility currently high or low relative to its own
    recent past," not relative to an arbitrary universal threshold.
    """
    history = vol_history.dropna()
    if len(history) < 20:
        return None
    return float((history < current_vol).mean())


def cross_asset_trend_dispersion(trend_scores: dict[str, float]) -> float | None:
    """Dispersion (population std) of trend scores across instruments at a
    single point in time -- low dispersion means most instruments agree on
    direction (broad regime), high dispersion means the signal is mixed.
    """
    values = [v for v in trend_scores.values() if v is not None]
    if len(values) < 2:
        return None
    return float(np.std(values))


def average_pairwise_correlation(returns: pd.DataFrame, window_days: int) -> float | None:
    """Average of the off-diagonal entries of the trailing correlation
    matrix across all instrument-return columns -- a simple market-
    breadth/co-movement diagnostic. `returns` must already be PIT-sliced by
    the caller (same contract as portfolio/covariance.py).
    """
    if len(returns) < window_days or returns.shape[1] < 2:
        return None
    window = returns.iloc[-window_days:]
    corr = window.corr()
    n = corr.shape[0]
    off_diagonal_sum = corr.to_numpy().sum() - np.trace(corr.to_numpy())
    n_pairs = n * (n - 1)
    if n_pairs == 0:
        return None
    return float(off_diagonal_sum / n_pairs)


def compute_regime_snapshot(
    trend_scores: dict[str, float],
    vol_by_symbol: dict[str, float],
    vol_history_by_symbol: dict[str, pd.Series],
    returns: pd.DataFrame,
    correlation_window_days: int = 60,
) -> dict[str, float | None]:
    """Bundles the diagnostics above into one snapshot for a single as_of
    date -- the shape a reporting CLI or experiment log would want, one row
    per date. Still diagnostics only; see module docstring.
    """
    vol_percentiles = [
        p
        for symbol, current_vol in vol_by_symbol.items()
        if (p := trailing_vol_percentile(vol_history_by_symbol.get(symbol, pd.Series(dtype=float)), current_vol))
        is not None
    ]
    avg_vol_percentile = float(np.mean(vol_percentiles)) if vol_percentiles else None

    return {
        "trend_dispersion": cross_asset_trend_dispersion(trend_scores),
        "avg_vol_percentile": avg_vol_percentile,
        "avg_pairwise_correlation": average_pairwise_correlation(returns, correlation_window_days),
    }
