"""INDmoney / INDstocks Trading API adapter
(https://api-docs.indstocks.com/, REST, no official Python SDK found).

Built against INDstocks' documented historical-data contract:
``GET https://api.indstocks.com/market/historical/{interval}?scrip-codes=...&start_time=<epoch_ms>&end_time=<epoch_ms>``
with header ``Authorization: <token>``, returning
``{"status": "success", "data": {"candles": [[epoch_ms, open, high, low, close, volume], ...]}}``.

UNCERTAINTY FLAGGED HONESTLY: the documented example uses interval
"1minute"; the exact daily-interval string (e.g. "1day", "day", "D") was
not confirmed from available documentation at the time this was written --
``interval`` defaults to "1day" as a best guess and is a constructor
parameter so it can be corrected without touching this file. Likewise, the
instruments-master endpoint (``/market/instruments?source=...``) returns a
CSV whose exact column layout was not confirmed here, so this adapter does
NOT attempt to parse it -- you supply InstrumentMapping entries yourself
(the same pattern every adapter in this package uses). No live INDstocks
session was available to execution-test this adapter; verify both of the
above with a real account before trusting it, and fix the interval string
here if it differs (a single line, see get_prices()).

CREDENTIAL POLICY: this adapter takes an already-authenticated HTTP client
(anything with a requests.Session-like ``.get(url, headers=, params=)``
method) with your access token already available to pass in the
Authorization header -- you obtain that token yourself via INDstocks'
dashboard or their ``/generate/token`` endpoint, in your own script. This
module never sees your API key, MPIN, or TOTP.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Protocol

import pandas as pd

from trading_system.brokers.base import (
    InstrumentMapping,
    chunk_date_range,
    normalize_ohlcv,
    read_or_none,
    write_cache,
)
from trading_system.data.interfaces import ContractMeta

BASE_URL = "https://api.indstocks.com"


class HttpClientLike(Protocol):
    def get(self, url: str, headers: dict, params: dict, timeout: float = 30.0):
        ...


def _to_epoch_ms(d: date, end_of_day: bool = False) -> int:
    dt = datetime(d.year, d.month, d.day, 23, 59, 59) if end_of_day else datetime(d.year, d.month, d.day)
    return int(dt.timestamp() * 1000)


class INDmoneyDataSource:
    def __init__(
        self,
        http_client: HttpClientLike,
        access_token: str,
        instrument_map: list[InstrumentMapping],
        start_date: date,
        end_date: date,
        interval: str = "1day",  # UNCONFIRMED -- see module docstring
        cache_dir: Path | str | None = None,
        max_days_per_chunk: int = 365,
    ):
        self._client = http_client
        self._access_token = access_token
        self._by_symbol = {m.symbol: m for m in instrument_map}
        self._start_date = start_date
        self._end_date = end_date
        self._interval = interval
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._max_days_per_chunk = max_days_per_chunk

    def get_universe(self) -> list[ContractMeta]:
        return [
            ContractMeta(symbol=m.symbol, asset_class=m.asset_class)
            for m in self._by_symbol.values()
        ]

    def get_prices(self, symbol: str) -> pd.DataFrame:
        mapping = self._by_symbol[symbol]

        if self._cache_dir is not None:
            cached = read_or_none(self._cache_dir, symbol, self._start_date, self._end_date)
            if cached is not None:
                return cached

        rows: list[list] = []
        for chunk_start, chunk_end in chunk_date_range(
            self._start_date, self._end_date, self._max_days_per_chunk
        ):
            response = self._client.get(
                f"{BASE_URL}/market/historical/{self._interval}",
                headers={"Authorization": self._access_token},
                params={
                    "scrip-codes": mapping.vendor_id,
                    "start_time": _to_epoch_ms(chunk_start),
                    "end_time": _to_epoch_ms(chunk_end, end_of_day=True),
                },
                timeout=30.0,
            )
            payload = response.json()
            if payload.get("status") != "success":
                raise ValueError(f"INDstocks API error for {symbol}: {payload}")
            rows.extend(payload["data"]["candles"])

        if not rows:
            raise ValueError(
                f"INDstocks API returned no historical data for {symbol} "
                f"({self._start_date} to {self._end_date}, interval={self._interval})"
            )

        raw = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        # Epoch ms -> UTC instant -> IST wall-clock date, then drop tz.
        raw["date"] = (
            pd.to_datetime(raw["date"], unit="ms", utc=True)
            .dt.tz_convert("Asia/Kolkata")
            .dt.tz_localize(None)
        )
        raw = raw.set_index("date")
        result = normalize_ohlcv(raw)

        if self._cache_dir is not None:
            write_cache(self._cache_dir, symbol, result)

        return result
