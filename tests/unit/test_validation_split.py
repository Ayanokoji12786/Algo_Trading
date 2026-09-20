from datetime import date

import numpy as np
import pandas as pd

from trading_system.backtest.validation_split import ValidationSplit, split_and_report


def _equity_curve(start: str, end: str, seed: int = 0) -> pd.Series:
    dates = pd.bdate_range(start, end)
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0003, 0.01, len(dates))
    return pd.Series(1_000_000 * np.exp(np.cumsum(returns)), index=dates)


def test_full_coverage_all_segments_ok():
    equity = _equity_curve("2016-01-01", "2024-12-31")
    report = split_and_report(equity)
    assert report["discovery"]["status"] == "OK"
    assert report["validation"]["status"] == "OK"
    assert report["holdout"]["status"] == "OK"


def test_insufficient_history_flagged_not_reshaped():
    # Data starts in 2020 -- discovery (ends 2018-12-31) has nothing.
    equity = _equity_curve("2020-01-01", "2024-12-31")
    report = split_and_report(equity)
    assert report["discovery"]["status"] == "INSUFFICIENT_HISTORY"
    assert report["validation"]["status"] == "OK"


def test_custom_split_dates_respected():
    equity = _equity_curve("2016-01-01", "2020-12-31")
    custom = ValidationSplit(
        discovery_end=date(2017, 12, 31),
        validation_start=date(2018, 1, 1),
        validation_end=date(2019, 12, 31),
        holdout_start=date(2020, 1, 1),
        holdout_end=date(2020, 12, 31),
    )
    report = split_and_report(equity, custom)
    assert all(report[k]["status"] == "OK" for k in ("discovery", "validation", "holdout"))
