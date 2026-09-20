from datetime import date

import pandas as pd

from trading_system.brokers.base import InstrumentMapping
from trading_system.brokers.indmoney import INDmoneyDataSource


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHttpClient:
    def __init__(self):
        self.calls: list[dict] = []

    def get(self, url, headers, params, timeout=30.0):
        self.calls.append({"url": url, "headers": headers, "params": params})
        start_ms = params["start_time"]
        end_ms = params["end_time"]
        start = pd.Timestamp(start_ms, unit="ms")
        end = pd.Timestamp(end_ms, unit="ms")
        dates = pd.bdate_range(start, end)
        candles = [
            [int(d.timestamp() * 1000), 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 500 + i]
            for i, d in enumerate(dates)
        ]
        return _FakeResponse({"status": "success", "data": {"candles": candles}})


def _mapping():
    return [InstrumentMapping(symbol="TCS", asset_class="equity_index", vendor_id="NSE_11536")]


def test_get_prices_parses_documented_response_shape():
    source = INDmoneyDataSource(
        _FakeHttpClient(), "fake-token", _mapping(), date(2020, 1, 1), date(2020, 1, 10)
    )
    df = source.get_prices("TCS")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.is_monotonic_increasing
    assert not df.empty


def test_sends_authorization_header_and_scrip_code():
    client = _FakeHttpClient()
    source = INDmoneyDataSource(client, "my-token", _mapping(), date(2020, 1, 1), date(2020, 1, 5))
    source.get_prices("TCS")
    assert client.calls[0]["headers"]["Authorization"] == "my-token"
    assert client.calls[0]["params"]["scrip-codes"] == "NSE_11536"


def test_raises_on_non_success_status():
    class _ErrorClient:
        def get(self, url, headers, params, timeout=30.0):
            return _FakeResponse({"status": "error", "message": "bad token"})

    source = INDmoneyDataSource(
        _ErrorClient(), "bad-token", _mapping(), date(2020, 1, 1), date(2020, 1, 5)
    )
    try:
        source.get_prices("TCS")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_chunks_long_ranges():
    client = _FakeHttpClient()
    source = INDmoneyDataSource(
        client, "tok", _mapping(), date(2020, 1, 1), date(2020, 6, 30), max_days_per_chunk=30
    )
    source.get_prices("TCS")
    assert len(client.calls) > 1
