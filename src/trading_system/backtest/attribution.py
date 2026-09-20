"""Subperiod / holdout attribution (Prompt.md S17: "yearly returns... regime
specific performance", S22: in-sample vs validation vs out-of-sample, S23:
walk-forward "record every period independently").

Honesty note (Implementation_Spec.md audit item on walk-forward, S6): the
baseline trend strategy has no fitted parameters -- 63/126/252, the vol
window, and the risk targets are frozen research inputs, not estimated from
data. There is therefore nothing to "retrain" between folds in the classic
walk-forward sense. What this module provides instead is honest, per-period
performance reporting: does the frozen rule perform consistently across
subperiods, or is its aggregate result carried by one lucky stretch? That is
a real and required check (Prompt.md S23's stated purpose: "show whether
performance is dependent on a particular historical period"), but it is not
a substitute for walk-forward *re-estimation*, which only becomes meaningful
once this system has an actual fitted component (e.g. a challenger_models/
entry). Do not describe subperiod breakdowns from this module as
"walk-forward validation" of a fitted model -- they are not that.
"""
from __future__ import annotations

import pandas as pd

from trading_system.backtest.metrics import compute_metrics


def _rebase(segment: pd.Series) -> pd.Series:
    return segment / segment.iloc[0]


def subperiod_breakdown(equity_curve: pd.Series, freq: str = "YE") -> pd.DataFrame:
    """Metrics computed independently within each calendar period, each
    rebased to start at 1.0 so per-period Sharpe/drawdown/etc. reflect only
    that period's behavior, not compounding from before it.
    """
    rows = []
    for period, segment in equity_curve.groupby(pd.Grouper(freq=freq)):
        if len(segment) < 5:
            continue
        metrics = compute_metrics(_rebase(segment))
        rows.append({"period": period, "n_days": len(segment), **metrics})
    return pd.DataFrame(rows).set_index("period") if rows else pd.DataFrame()


def train_test_split_metrics(
    equity_curve: pd.Series,
    turnover: pd.Series | None,
    holdout_fraction: float = 0.2,
) -> dict[str, dict[str, float]]:
    """Splits the (already-computed, causal) equity curve chronologically
    into an in-sample segment and an untouched final holdout segment
    (Prompt.md S22). Each segment's metrics are computed on its own rebased
    equity path, independent of the other.

    This does not re-run the backtest or refit anything -- for this frozen,
    non-fitted baseline, "reserving a holdout" means never letting the
    holdout segment's results influence the (already-frozen) configuration,
    which the process in Docs/Implementation_Spec.md S6 already guarantees
    by construction (parameters were fixed before any backtest ran).
    """
    n = len(equity_curve)
    split_idx = int(n * (1 - holdout_fraction))
    in_sample = equity_curve.iloc[:split_idx]
    holdout = equity_curve.iloc[split_idx:]

    def _slice_turnover(index: pd.DatetimeIndex) -> pd.Series | None:
        if turnover is None:
            return None
        return turnover.loc[turnover.index.intersection(index)]

    return {
        "in_sample": compute_metrics(_rebase(in_sample), _slice_turnover(in_sample.index)),
        "holdout": compute_metrics(_rebase(holdout), _slice_turnover(holdout.index)),
        "split_date": str(equity_curve.index[split_idx]),
    }
