"""Regression tests for the path-traversal audit fix
(src/trading_system/util.py:validate_symbol_name is now called from
LocalFileDataSource.get_prices, brokers/base.py:read_or_none, and
brokers/base.py:write_cache).
"""
from datetime import date

import pandas as pd
import pytest

from trading_system.brokers.base import read_or_none, write_cache
from trading_system.brokers.local_csv import LocalFileDataSource
from trading_system.data.interfaces import ContractMeta


def test_local_csv_rejects_dot_dot_symbol(tmp_path):
    source = LocalFileDataSource(
        tmp_path,
        universe=[ContractMeta(symbol="..%2Fetc%2Fpasswd", asset_class="fx")],
    )
    with pytest.raises(ValueError):
        source.get_prices("../../etc/passwd")


def test_local_csv_rejects_empty_symbol(tmp_path):
    source = LocalFileDataSource(tmp_path, universe=[])
    with pytest.raises(ValueError):
        source.get_prices("")


def test_write_cache_rejects_dot_dot_symbol(tmp_path):
    df = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [10]},
        index=pd.to_datetime(["2020-01-01"]),
    )
    with pytest.raises(ValueError):
        write_cache(tmp_path, "../malicious", df)


def test_read_or_none_rejects_dot_dot_symbol(tmp_path):
    with pytest.raises(ValueError):
        read_or_none(tmp_path, "../etc/passwd", date(2020, 1, 1), date(2020, 12, 31))


def test_write_cache_is_atomic_under_interruption(tmp_path):
    """The staging-file+rename write pattern means a partially written
    parquet cannot end up at the final destination even if the process is
    interrupted between the write and the rename.
    """
    df = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [10]},
        index=pd.to_datetime(["2020-01-01"]),
    )
    write_cache(tmp_path, "OK", df)
    final = tmp_path / "OK.parquet"
    staging = tmp_path / "OK.parquet.tmp"
    assert final.exists()
    assert not staging.exists()  # rename cleaned up the staging file
