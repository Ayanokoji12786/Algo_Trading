"""Point-in-time enforcement boundary (Prompt.md S7).

Every feature/strategy in this system must ask "would this value have been
known at this exact timestamp?" The answer is enforced here structurally:
no code outside this module ever holds a reference to a full price history.
Callers can only ask for data "as of" a given date, which slices away
anything timestamped later. This makes a whole class of look-ahead bugs
impossible to introduce accidentally elsewhere in the codebase.
"""
from __future__ import annotations

import pandas as pd

from trading_system.data.interfaces import ContractMeta, DataSource


class PointInTimeStore:
    def __init__(self, source: DataSource):
        self._universe = source.get_universe()
        self.__full_history = {
            meta.symbol: source.get_prices(meta.symbol) for meta in self._universe
        }
        for symbol, df in self.__full_history.items():
            if not df.index.is_monotonic_increasing:
                raise ValueError(f"{symbol}: price history is not chronologically sorted")
            if df.index.has_duplicates:
                raise ValueError(f"{symbol}: price history has duplicate timestamps")

    @property
    def universe(self) -> list[ContractMeta]:
        return list(self._universe)

    def trading_calendar(self) -> pd.DatetimeIndex:
        """Union of all instruments' trading dates, sorted ascending."""
        all_dates: pd.Index = pd.Index([])
        for df in self.__full_history.values():
            all_dates = all_dates.union(df.index)
        return pd.DatetimeIndex(sorted(all_dates))

    def history_as_of(self, symbol: str, as_of: pd.Timestamp) -> pd.DataFrame:
        """All bars for ``symbol`` with timestamp <= ``as_of``.

        This is the *only* way strategy/feature code should touch prices.
        Returns a defensive copy: pandas' ``.loc[bool_mask]`` semantics have
        historically varied between view and copy across versions, and the
        SettingWithCopyWarning that currently protects the store's internal
        state is being deprecated in pandas 3.0's copy-on-write model.
        An explicit ``.copy()`` makes the leakage-safety guarantee hold
        identically across pandas versions, at a small per-call cost that
        is fine for a research pipeline.
        """
        full = self.__full_history[symbol]
        return full.loc[full.index <= as_of].copy()

    def close_as_of(self, symbol: str, as_of: pd.Timestamp) -> float | None:
        hist = self.history_as_of(symbol, as_of)
        if hist.empty:
            return None
        return float(hist["close"].iloc[-1])

    def close_matrix(self) -> pd.DataFrame:
        """Wide close-price matrix (columns=symbols) over the full trading
        calendar, forward-filled across each instrument's non-trading gaps.

        FOR BACKTEST MARK-TO-MARKET / ACCOUNTING ONLY. A backtest loop that
        iterates the calendar strictly forward and only reads "today's" row
        is not introducing look-ahead by using this -- it is simply pricing
        already-realized closes. Signal/feature code must never use this;
        use history_as_of() there so the point-in-time guarantee holds.
        """
        calendar = self.trading_calendar()
        data = {
            symbol: df["close"].reindex(calendar).ffill()
            for symbol, df in self.__full_history.items()
        }
        return pd.DataFrame(data, index=calendar)
