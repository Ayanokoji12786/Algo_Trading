from datetime import date

import pandas as pd

from trading_system.brokers.base import InstrumentMapping
from trading_system.brokers.zerodha_kite import ZerodhaKiteDataSource
from trading_system.data.pit_store import PointInTimeStore


class _FakeKite:
    """Mimics kiteconnect.KiteConnect.historical_data's documented response
    shape: a list of dicts with date/open/high/low/close/volume.
    """

    def __init__(self):
        self.calls: list[dict] = []

    def historical_data(self, instrument_token, from_date, to_date, interval, **kwargs):
        self.calls.append(
            {"instrument_token": instrument_token, "from_date": from_date, "to_date": to_date}
        )
        dates = pd.bdate_range(from_date.split(" ")[0], to_date.split(" ")[0])
        return [
            {
                "date": f"{d.date()}T00:00:00+0530",
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": 1000 + i,
            }
            for i, d in enumerate(dates)
        ]


def _mapping():
    return [InstrumentMapping(symbol="NIFTY_FUT", asset_class="equity_index", vendor_id="256265")]


def test_get_universe_maps_instrument_mapping_to_contract_meta():
    source = ZerodhaKiteDataSource(_FakeKite(), _mapping(), date(2020, 1, 1), date(2020, 1, 10))
    universe = source.get_universe()
    assert len(universe) == 1
    assert universe[0].symbol == "NIFTY_FUT"
    assert universe[0].asset_class == "equity_index"


def test_get_prices_returns_sorted_ohlcv():
    source = ZerodhaKiteDataSource(_FakeKite(), _mapping(), date(2020, 1, 1), date(2020, 1, 10))
    df = source.get_prices("NIFTY_FUT")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.is_monotonic_increasing


def test_get_prices_chunks_long_ranges():
    kite = _FakeKite()
    source = ZerodhaKiteDataSource(
        kite, _mapping(), date(2020, 1, 1), date(2020, 6, 30), max_days_per_chunk=30
    )
    source.get_prices("NIFTY_FUT")
    assert len(kite.calls) > 1
    assert kite.calls[0]["instrument_token"] == 256265


def test_get_prices_uses_and_populates_cache(tmp_path):
    kite = _FakeKite()
    source = ZerodhaKiteDataSource(
        kite, _mapping(), date(2020, 1, 1), date(2020, 1, 10), cache_dir=tmp_path
    )
    first = source.get_prices("NIFTY_FUT")
    n_calls_after_first = len(kite.calls)

    second_source = ZerodhaKiteDataSource(
        kite, _mapping(), date(2020, 1, 1), date(2020, 1, 10), cache_dir=tmp_path
    )
    second = second_source.get_prices("NIFTY_FUT")

    assert len(kite.calls) == n_calls_after_first  # no new API calls -- served from cache
    pd.testing.assert_frame_equal(first, second)


def test_zerodha_source_plugs_directly_into_point_in_time_store():
    source = ZerodhaKiteDataSource(_FakeKite(), _mapping(), date(2020, 1, 1), date(2020, 3, 1))
    store = PointInTimeStore(source)
    assert len(store.universe) == 1
    assert store.close_as_of("NIFTY_FUT", store.trading_calendar()[-1]) is not None
