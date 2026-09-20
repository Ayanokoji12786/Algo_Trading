"""Angel One SmartAPI adapter (https://smartapi.angelone.in/,
package ``smartapi-python``, class ``SmartConnect``).

Built against SmartAPI's documented getCandleData() contract: a historicParam
dict {"exchange", "symboltoken", "interval", "fromdate", "todate"} (dates as
"YYYY-MM-DD HH:MM"), returning {"data": [[iso_timestamp, open, high, low,
close, volume], ...]}. This project's environment has no Angel One session
to test against live, so -- like the Zerodha adapter -- this is written to
the public SDK/API contract and unit-tested with a mocked client, not
execution-tested against a real account. Run a smoke test with your own
credentials before trusting it.

SmartAPI's per-request history window is limited and interval-dependent
(documented historically as roughly 30 days for minute-level intervals and
much longer for ONE_DAY; Angel One's own docs/forum are the source of truth
at the time you integrate, since these limits have changed before) --
max_days_per_chunk defaults conservatively and is a constructor parameter.

CREDENTIAL POLICY: takes an already-authenticated ``SmartConnect`` instance;
this module never handles your API key, client code, password, or TOTP.
"""
from __future__ import annotations

from datetime import date
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


class SmartConnectLike(Protocol):
    def getCandleData(self, historicParam: dict) -> dict:
        ...


class AngelOneDataSource:
    def __init__(
        self,
        smart_connect_client: SmartConnectLike,
        instrument_map: list[InstrumentMapping],
        start_date: date,
        end_date: date,
        interval: str = "ONE_DAY",
        cache_dir: Path | str | None = None,
        max_days_per_chunk: int = 365,
    ):
        self._client = smart_connect_client
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
            response = self._client.getCandleData(
                {
                    "exchange": mapping.exchange,
                    "symboltoken": mapping.vendor_id,
                    "interval": self._interval,
                    "fromdate": f"{chunk_start} 09:00",
                    "todate": f"{chunk_end} 15:30",
                }
            )
            if not response.get("status", True):
                raise ValueError(
                    f"Angel One SmartAPI error for {symbol}: {response.get('message')}"
                )
            rows.extend(response.get("data", []))

        if not rows:
            raise ValueError(
                f"Angel One SmartAPI returned no historical data for {symbol} "
                f"({self._start_date} to {self._end_date}, interval={self._interval})"
            )

        raw = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
        # Angel One returns ISO timestamps with a +05:30 (IST) offset. Parse
        # without utc=True and then drop the tz label (rather than
        # converting to UTC first) so the IST wall-clock date/time is
        # preserved -- converting to UTC first would shift early-session
        # candles onto the previous calendar day.
        raw["date"] = pd.to_datetime(raw["date"]).dt.tz_localize(None)
        raw = raw.set_index("date")
        result = normalize_ohlcv(raw)

        if self._cache_dir is not None:
            write_cache(self._cache_dir, symbol, result)

        return result
