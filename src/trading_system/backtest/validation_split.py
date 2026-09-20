"""Exact-date validation split (Docs/India_Implementation_Spec.md S1.5):

    discovery/training:            earliest reliable history -> 2018-12-31
    validation/walk-forward:       2019-01-01 -> 2022-12-31
    untouched final holdout:       2023-01-01 -> 2026-08-31 (opened once)

Distinct from backtest/attribution.py's generic 80/20 holdout_fraction split
used for the global-futures system -- this uses the specific calendar dates
the India research names, not a fraction of whatever range happens to be
backtested. If the data doesn't reach back far enough for a segment, that
segment's status is explicitly INSUFFICIENT_HISTORY rather than the split
being silently reshaped around what data exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from trading_system.backtest.metrics import compute_metrics


@dataclass(frozen=True)
class ValidationSplit:
    discovery_end: date = date(2018, 12, 31)
    validation_start: date = date(2019, 1, 1)
    validation_end: date = date(2022, 12, 31)
    holdout_start: date = date(2023, 1, 1)
    holdout_end: date = date(2026, 8, 31)


def _segment(equity_curve: pd.Series, start: pd.Timestamp | None, end: pd.Timestamp) -> pd.Series:
    mask = equity_curve.index <= end
    if start is not None:
        mask &= equity_curve.index >= start
    return equity_curve.loc[mask]


def split_and_report(
    equity_curve: pd.Series, split: ValidationSplit = ValidationSplit()
) -> dict[str, dict]:
    segments = {
        "discovery": (None, pd.Timestamp(split.discovery_end)),
        "validation": (pd.Timestamp(split.validation_start), pd.Timestamp(split.validation_end)),
        "holdout": (pd.Timestamp(split.holdout_start), pd.Timestamp(split.holdout_end)),
    }
    report: dict[str, dict] = {}
    for name, (start, end) in segments.items():
        seg = _segment(equity_curve, start, end)
        if len(seg) < 5:
            report[name] = {"status": "INSUFFICIENT_HISTORY"}
            continue
        rebased = seg / seg.iloc[0]
        report[name] = {"status": "OK", "n_days": len(seg), **compute_metrics(rebased)}
    return report
