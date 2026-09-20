"""Prompt.md S17 metrics. Deliberately not a single "score" -- every value
here is reported together, per S17's "do not rely on one metric."
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_TRADING_DAYS_PER_YEAR = 252


def _max_drawdown_duration_days(drawdown: pd.Series) -> int:
    in_drawdown = drawdown < 0
    if not in_drawdown.any():
        return 0
    longest = current = 0
    for flag in in_drawdown:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return int(longest)


def compute_metrics(
    equity: pd.Series, turnover: pd.Series | None = None
) -> dict[str, float]:
    equity = equity.dropna()
    daily_returns = equity.pct_change().dropna()

    n_years = (equity.index[-1] - equity.index[0]).days / 365.25
    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (
        (equity.iloc[-1] / equity.iloc[0]) ** (1 / n_years) - 1
        if n_years > 0
        else float("nan")
    )

    ann_vol = daily_returns.std() * np.sqrt(_TRADING_DAYS_PER_YEAR)
    ann_mean = daily_returns.mean() * _TRADING_DAYS_PER_YEAR
    sharpe = ann_mean / ann_vol if ann_vol > 0 else float("nan")

    downside = daily_returns[daily_returns < 0]
    downside_vol = (
        downside.std() * np.sqrt(_TRADING_DAYS_PER_YEAR) if len(downside) > 1 else float("nan")
    )
    sortino = (
        ann_mean / downside_vol
        if downside_vol and downside_vol > 0
        else float("nan")
    )

    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    max_drawdown = float(drawdown.min())
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else float("nan")
    max_dd_duration = _max_drawdown_duration_days(drawdown)

    result = {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annualized_vol": float(ann_vol),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": max_drawdown,
        "max_drawdown_duration_days": max_dd_duration,
        "calmar": float(calmar),
    }
    if turnover is not None and len(turnover) > 0:
        result["avg_turnover_per_rebalance"] = float(turnover.mean())
        result["total_turnover"] = float(turnover.sum())
    return result
