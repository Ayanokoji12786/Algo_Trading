"""Zerodha Kite Connect adapter (https://kite.trade/docs/connect/v3/).

Verified against a live Kite Connect session in this project's development
environment (2026-09-20): search_instruments returned real instrument
records with exactly the fields this adapter expects (instrument_token,
exchange, tradingsymbol, segment, instrument_type, expiry_date, tick_size,
lot_size) across NSE (equity), NFO (index/stock F&O), MCX (commodities), and
CDS (currency derivatives) -- so a single Zerodha account can in principle
cover three of Research.md's four asset-class buckets (equity index, FX,
commodities); NSE's GOI bond futures exist but are documented as thin at
retail level, so the "rates" bucket is NOT reliably fillable through Zerodha
alone -- flag this gap rather than silently dropping the bucket.
historical_data() itself could not be exercised (requires a logged-in
session; this environment's connector was not authenticated), so the OHLCV
parsing below is written to Kite Connect's documented response schema
(list of dicts with date/open/high/low/close/volume[/oi]) and unit-tested
against a mocked client, not against a live authenticated call.

CREDENTIAL POLICY: this adapter takes an already-authenticated
``kiteconnect.KiteConnect`` instance. Perform the login flow (API key,
request_token, generate_session) yourself, in your own script, using
Zerodha's official kiteconnect package -- this module never sees your
credentials.

Kite's historical-data endpoint limits how much history you can request per
call; the limit depends on the interval and has changed over time, so
max_days_per_chunk defaults to a conservative 365 days and is a Config
parameter you can raise if your app's tier allows more.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from trading_system.brokers.base import (
    InstrumentMapping,
    chunk_date_range,
    normalize_ohlcv,
    read_or_none,
    write_cache,
)
from trading_system.data.interfaces import ContractMeta


class KiteConnectLike(Protocol):
    """The subset of kiteconnect.KiteConnect this adapter calls -- kept as a
    Protocol so tests can pass a lightweight fake instead of a real,
    authenticated Kite session.
    """

    def historical_data(
        self,
        instrument_token: int,
        from_date: Any,
        to_date: Any,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict]:
        ...


class ZerodhaKiteDataSource:
    def __init__(
        self,
        kite_client: KiteConnectLike,
        instrument_map: list[InstrumentMapping],
        start_date: date,
        end_date: date,
        interval: str = "day",
        cache_dir: Path | str | None = None,
        max_days_per_chunk: int = 365,
    ):
        self._client = kite_client
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

        frames = []
        for chunk_start, chunk_end in chunk_date_range(
            self._start_date, self._end_date, self._max_days_per_chunk
        ):
            rows = self._client.historical_data(
                instrument_token=int(mapping.vendor_id),
                from_date=f"{chunk_start} 00:00:00",
                to_date=f"{chunk_end} 23:59:59",
                interval=self._interval,
            )
            if rows:
                frames.append(pd.DataFrame(rows))

        if not frames:
            raise ValueError(
                f"Kite Connect returned no historical data for {symbol} "
                f"({self._start_date} to {self._end_date}, interval={self._interval})"
            )

        raw = pd.concat(frames, ignore_index=True)
        raw["date"] = pd.to_datetime(raw["date"]).dt.tz_localize(None)
        raw = raw.set_index("date")
        result = normalize_ohlcv(raw)

        if self._cache_dir is not None:
            write_cache(self._cache_dir, symbol, result)

        return result
