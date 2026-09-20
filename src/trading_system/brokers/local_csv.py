"""Generic local-file adapter -- the path for "any other vendor."

Works with ANY data vendor that lets you export or download historical
OHLCV data (which is effectively all of them: Interactive Brokers, Norgate,
Databento, TrueData, Global Datafeeds, a broker's own export button, etc.).
No vendor-specific code is needed: export your data to one CSV or Parquet
file per instrument with the columns below, point this adapter at the
folder, and everything upstream (features, strategies, backtest engine,
paper trader) works unmodified -- this is the same DataSource contract
Zerodha/Angel One/INDmoney's adapters implement.

Expected file layout: ``{directory}/{symbol}.csv`` (or ``.parquet``), each
with a date/datetime column (any name -- configurable) plus ``open``,
``high``, ``low``, ``close``, ``volume`` columns (case-insensitive).

For a vendor with its own API instead of a file export, see this package's
other adapters as a template: the entire "small modification" needed is a
class with get_universe() and get_prices(symbol) matching
trading_system.data.interfaces.DataSource -- see Docs/Vendor_Integration.md.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from trading_system.brokers.base import normalize_ohlcv
from trading_system.data.interfaces import ContractMeta
from trading_system.util import validate_symbol_name


class LocalFileDataSource:
    def __init__(
        self,
        directory: Path | str,
        universe: list[ContractMeta],
        date_column_candidates: tuple[str, ...] = ("date", "datetime", "timestamp"),
    ):
        self._directory = Path(directory)
        self._universe = list(universe)
        self._date_columns = date_column_candidates

    def get_universe(self) -> list[ContractMeta]:
        return list(self._universe)

    def get_prices(self, symbol: str) -> pd.DataFrame:
        validate_symbol_name(symbol)
        csv_path = self._directory / f"{symbol}.csv"
        parquet_path = self._directory / f"{symbol}.parquet"
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
        elif csv_path.exists():
            df = pd.read_csv(csv_path)
        else:
            raise FileNotFoundError(
                f"No {symbol}.csv or {symbol}.parquet found in {self._directory}"
            )

        df.columns = [c.lower() for c in df.columns]

        if isinstance(df.index, pd.DatetimeIndex):
            # Already indexed by date -- e.g. a parquet file written by this
            # package's own cache (brokers/base.py:write_cache) or by pandas
            # with a meaningful index. Use it as-is rather than searching
            # for a date column that doesn't exist in this layout.
            df.index.name = "date"
            return normalize_ohlcv(df)

        date_col = next((c for c in self._date_columns if c in df.columns), None)
        if date_col is None:
            raise ValueError(
                f"{symbol}: no DatetimeIndex and no date column found among "
                f"{self._date_columns} in columns {list(df.columns)}"
            )
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.set_index(date_col)
        df.index.name = "date"
        return normalize_ohlcv(df)
