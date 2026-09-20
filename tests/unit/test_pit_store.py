import pandas as pd
import pytest

from trading_system.data.interfaces import ContractMeta
from trading_system.data.pit_store import PointInTimeStore


class _FakeSource:
    def __init__(self, df: pd.DataFrame):
        self._df = df

    def get_universe(self):
        return [ContractMeta(symbol="X", asset_class="equity_index")]

    def get_prices(self, symbol: str) -> pd.DataFrame:
        return self._df.copy()


def _make_df():
    dates = pd.bdate_range("2020-01-01", periods=10)
    return pd.DataFrame(
        {
            "open": range(10),
            "high": range(10),
            "low": range(10),
            "close": [float(i) for i in range(10)],
            "volume": [1000.0] * 10,
        },
        index=dates,
    )


def test_history_as_of_excludes_future_rows():
    df = _make_df()
    store = PointInTimeStore(_FakeSource(df))
    cutoff = df.index[4]
    hist = store.history_as_of("X", cutoff)
    assert hist.index.max() == cutoff
    assert len(hist) == 5


def test_close_as_of_matches_last_visible_bar():
    df = _make_df()
    store = PointInTimeStore(_FakeSource(df))
    cutoff = df.index[4]
    assert store.close_as_of("X", cutoff) == 4.0


def test_mutating_a_returned_slice_does_not_leak_into_the_store():
    df = _make_df()
    store = PointInTimeStore(_FakeSource(df))
    cutoff = df.index[4]
    hist = store.history_as_of("X", cutoff)
    hist.loc[cutoff, "close"] = 9999.0
    assert store.close_as_of("X", cutoff) == 4.0


def test_rejects_unsorted_data():
    df = _make_df().iloc[::-1]

    class UnsortedSource:
        def get_universe(self):
            return [ContractMeta(symbol="X", asset_class="equity_index")]

        def get_prices(self, symbol):
            return df

    with pytest.raises(ValueError):
        PointInTimeStore(UnsortedSource())
