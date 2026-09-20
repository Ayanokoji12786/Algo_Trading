"""Monte Carlo uncertainty analysis (Docs/India_Implementation_Spec.md S1.6):
"do not merely shuffle individual daily returns and thereby erase serial
dependence. Run both a block/bootstrap return resampling preserving short-
horizon dependence and a trade-order permutation... The outputs are
uncertainty estimates, not evidence of guaranteed future profitability."

Two distinct resampling schemes, matching that instruction exactly:

- block_bootstrap_returns: resamples overlapping BLOCKS of consecutive
  daily returns (not individual days), preserving whatever short-horizon
  serial dependence (e.g. trend persistence, mean reversion after a shock)
  the real return series has.
- trade_order_permutation: shuffles the ORDER of discrete trade outcomes
  (not daily returns) -- the same set of trades happening in a different
  sequence, testing sensitivity to sequencing/luck rather than to the
  return-generating process itself.

Neither of these is a forecast. They characterize how much of the observed
result could plausibly have come out differently under the same underlying
process/trade set -- report the DISTRIBUTION, never a single number.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def block_bootstrap_returns(
    returns: pd.Series, n_simulations: int, block_size: int, seed: int = 0
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = returns.to_numpy()
    n = len(values)
    if block_size <= 0 or block_size > n:
        raise ValueError("block_size must be in (0, len(returns)]")

    sims = np.empty((n_simulations, n))
    max_start = n - block_size
    for s in range(n_simulations):
        pieces = []
        total = 0
        while total < n:
            start = rng.integers(0, max_start + 1)
            piece = values[start : start + block_size]
            pieces.append(piece)
            total += len(piece)
        sims[s] = np.concatenate(pieces)[:n]
    return sims


def trade_order_permutation(trade_returns: pd.Series, n_simulations: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = trade_returns.to_numpy()
    n = len(values)
    sims = np.empty((n_simulations, n))
    for s in range(n_simulations):
        sims[s] = rng.permutation(values)
    return sims


def summarize_simulations(sims: np.ndarray, rolling_window: int = 252) -> dict:
    """sims: (n_simulations, n_periods) array of simple per-period returns."""
    n_sims, n_periods = sims.shape
    cum = np.cumprod(1.0 + sims, axis=1)
    terminal_return = cum[:, -1] - 1.0

    running_max = np.maximum.accumulate(cum, axis=1)
    drawdown = cum / running_max - 1.0
    max_drawdown = drawdown.min(axis=1)

    window = min(rolling_window, n_periods)
    log_r = np.log1p(sims)
    cumsum = np.concatenate([np.zeros((n_sims, 1)), np.cumsum(log_r, axis=1)], axis=1)
    rolling_log_return = cumsum[:, window:] - cumsum[:, :-window]
    rolling_return = np.exp(rolling_log_return) - 1.0
    worst_rolling = rolling_return.min(axis=1) if rolling_return.size else np.full(n_sims, np.nan)

    def _pct(arr: np.ndarray) -> dict:
        return {
            "p5": float(np.percentile(arr, 5)),
            "p50": float(np.percentile(arr, 50)),
            "p95": float(np.percentile(arr, 95)),
        }

    return {
        "n_simulations": n_sims,
        "terminal_return": _pct(terminal_return),
        "max_drawdown": _pct(max_drawdown),
        "worst_rolling_window_return": _pct(worst_rolling),
    }
