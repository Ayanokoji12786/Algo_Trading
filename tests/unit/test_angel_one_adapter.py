from datetime import date

import pandas as pd

from trading_system.brokers.angel_one import AngelOneDataSource
from trading_system.brokers.base import InstrumentMapping


class _FakeSmartConnect:
    def __init__(self):
        self.calls: list[dict] = []

    def getCandleData(self, historicParam: dict) -> dict:
        self.calls.append(historicParam)
        start = pd.Timestamp(historicParam["fromdate"].split(" ")[0])
        end = pd.Timestamp(historicParam["todate"].split(" ")[0])
        dates = pd.bdate_range(start, end)
        return {
            "status": True,
            "data": [
                [f"{d.date()}T09:15:00+05:30", 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 500 + i]
                for i, d in enumerate(dates)
            ],
        }


def _mapping():
    return [
        InstrumentMapping(
            symbol="RELIANCE", asset_class="equity_index", vendor_id="2885", exchange="NSE"
        )
    ]


def test_get_prices_parses_documented_response_shape():
    source = AngelOneDataSource(
        _FakeSmartConnect(), _mapping(), date(2020, 1, 1), date(2020, 1, 10)
    )
    df = source.get_prices("RELIANCE")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.is_monotonic_increasing
    assert not df.empty


def test_passes_exchange_and_symboltoken_from_mapping():
    client = _FakeSmartConnect()
    source = AngelOneDataSource(client, _mapping(), date(2020, 1, 1), date(2020, 1, 5))
    source.get_prices("RELIANCE")
    assert client.calls[0]["exchange"] == "NSE"
    assert client.calls[0]["symboltoken"] == "2885"


def test_raises_on_error_status():
    class _ErrorClient:
        def getCandleData(self, historicParam):
            return {"status": False, "message": "Invalid token"}

    source = AngelOneDataSource(_ErrorClient(), _mapping(), date(2020, 1, 1), date(2020, 1, 5))
    try:
        source.get_prices("RELIANCE")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "Invalid token" in str(e)


def test_chunks_long_ranges():
    client = _FakeSmartConnect()
    source = AngelOneDataSource(
        client, _mapping(), date(2020, 1, 1), date(2020, 6, 30), max_days_per_chunk=30
    )
    source.get_prices("RELIANCE")
    assert len(client.calls) > 1
