from datetime import date

import pandas as pd
import pytest

from trading_system.brokers.base import (
    chunk_date_range,
    normalize_ohlcv,
    read_or_none,
    write_cache,
)


def test_chunk_date_range_splits_correctly():
    chunks = chunk_date_range(date(2020, 1, 1), date(2020, 1, 10), max_days_per_chunk=4)
    assert chunks == [
        (date(2020, 1, 1), date(2020, 1, 4)),
        (date(2020, 1, 5), date(2020, 1, 8)),
        (date(2020, 1, 9), date(2020, 1, 10)),
    ]


def test_chunk_date_range_single_chunk_when_within_limit():
    chunks = chunk_date_range(date(2020, 1, 1), date(2020, 1, 3), max_days_per_chunk=30)
    assert chunks == [(date(2020, 1, 1), date(2020, 1, 3))]


def test_chunk_date_range_empty_when_start_after_end():
    assert chunk_date_range(date(2020, 1, 10), date(2020, 1, 1), max_days_per_chunk=30) == []


def test_normalize_ohlcv_sorts_dedupes_and_selects_columns():
    df = pd.DataFrame(
        {
            "close": [3.0, 1.0, 2.0, 2.0],
            "open": [3.0, 1.0, 2.0, 2.5],
            "high": [3.0, 1.0, 2.0, 2.5],
            "low": [3.0, 1.0, 2.0, 2.5],
            "volume": [100, 100, 100, 200],
            "extra_field": ["x", "y", "z", "w"],
        },
        index=pd.to_datetime(["2020-01-03", "2020-01-01", "2020-01-02", "2020-01-02"]),
    )
    result = normalize_ohlcv(df)
    assert list(result.columns) == ["open", "high", "low", "close", "volume"]
    assert result.index.is_monotonic_increasing
    assert not result.index.has_duplicates
    assert len(result) == 3
    # keep="last" duplicate handling -> the second 2020-01-02 row wins
    assert result.loc["2020-01-02", "volume"] == 200


def test_normalize_ohlcv_raises_on_missing_column():
    df = pd.DataFrame({"open": [1.0], "close": [1.0]}, index=pd.to_datetime(["2020-01-01"]))
    with pytest.raises(ValueError):
        normalize_ohlcv(df)


def test_cache_round_trip(tmp_path):
    df = pd.DataFrame(
        {"open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0], "close": [1.0, 2.0], "volume": [10, 20]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )
    write_cache(tmp_path, "TEST", df)
    result = read_or_none(tmp_path, "TEST", date(2020, 1, 1), date(2020, 1, 2))
    assert result is not None
    assert len(result) == 2


def test_cache_miss_when_range_not_fully_covered(tmp_path):
    df = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [10]},
        index=pd.to_datetime(["2020-01-02"]),
    )
    write_cache(tmp_path, "TEST", df)
    assert read_or_none(tmp_path, "TEST", date(2020, 1, 1), date(2020, 1, 5)) is None


def test_cache_miss_when_no_file(tmp_path):
    assert read_or_none(tmp_path, "MISSING", date(2020, 1, 1), date(2020, 1, 2)) is None
