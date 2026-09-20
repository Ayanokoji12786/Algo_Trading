"""Vendor-agnostic broker/data-vendor adapter machinery.

Design goal (per user request): this system should work with ANY data
vendor, with Zerodha Kite Connect, Angel One SmartAPI, and INDmoney
(INDstocks API) as first-class, ready-to-use adapters, and a generic
local-file adapter covering everyone else. Every adapter in this package
implements ONLY the two methods trading_system.data.interfaces.DataSource
already requires (get_universe, get_prices) -- nothing downstream (features,
strategies, sizing, backtest engine, paper trader) needs to know or care
which vendor supplied the data. That is the actual "works with any vendor"
mechanism: the contract is small and already vendor-neutral by construction.

CREDENTIAL POLICY: no adapter in this package accepts or stores API keys,
passwords, or TOTP secrets. Each constructor takes an ALREADY-AUTHENTICATED
client object (a KiteConnect, SmartConnect, or requests.Session instance)
that the caller creates themselves using the vendor's own official login
flow, in their own script. This module never performs authentication.

INDIA-SPECIFIC SCOPE NOTE: Zerodha, Angel One, and INDmoney are Indian
brokers covering NSE/BSE (equity, index F&O), MCX (commodities), and CDS
(currency derivatives). Building against them means running Research.md's
"India-specific branch" (its own STT/tax model and instrument universe),
which Research.md treats as a SEPARATE experiment from the global-futures
universe Docs/Implementation_Spec.md S6.1 picked as the primary research
target. Using one of these adapters does not silently satisfy that earlier
decision -- see Docs/Vendor_Integration.md for how the two relate.

TESTING STATUS: each adapter's own parsing/chunking/caching logic is unit-
tested against mocked clients (see tests/unit/test_*_adapter.py). None have
been execution-tested against a live authenticated vendor session in this
environment -- do a small smoke test with your own credentials
(scripts/vendor_smoke_test.py) before trusting one for real use.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from trading_system.util import validate_symbol_name


@dataclass(frozen=True)
class InstrumentMapping:
    """Maps this system's canonical symbol to one vendor's own identifier
    for that instrument. There is no universal instrument-id standard across
    Indian brokers (Kite uses a numeric instrument_token, Angel One a
    numeric symboltoken plus exchange, INDstocks an "EXCHANGE_code" scrip
    code) -- the user builds this list once per vendor, typically from that
    vendor's instrument/scrip master, and everything else in this system is
    then vendor-independent.
    """

    symbol: str
    asset_class: str
    vendor_id: str
    exchange: str = ""
    extra: dict = field(default_factory=dict)


REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Validates and returns a DataFrame ready for PointInTimeStore:
    DatetimeIndex, sorted ascending, no duplicate timestamps, and exactly
    the columns PointInTimeStore/features expect.
    """
    missing = [c for c in REQUIRED_OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Vendor data missing required column(s): {missing}")
    df = df[list(REQUIRED_OHLCV_COLUMNS)].copy()
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    return df


def chunk_date_range(
    start: date, end: date, max_days_per_chunk: int
) -> list[tuple[date, date]]:
    """Splits [start, end] into consecutive chunks no longer than
    max_days_per_chunk days -- every vendor's historical-data endpoint
    limits how much history can be requested in a single call, and the
    limit differs by vendor and interval. Each adapter picks its own
    conservative default (see that adapter's module docstring for the
    documented source of its limit) and callers can override it.
    """
    if start > end:
        return []
    chunks = []
    chunk_start = start
    while chunk_start <= end:
        chunk_end = min(chunk_start + timedelta(days=max_days_per_chunk - 1), end)
        chunks.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return chunks


def read_or_none(cache_dir: Path, symbol: str, start: date, end: date) -> pd.DataFrame | None:
    """Returns a cached OHLCV frame for ``symbol`` only if it fully covers
    [start, end]; otherwise None, signaling the caller must fetch fresh.

    Simplification (documented, not silent): a cache miss re-fetches the
    ENTIRE requested range rather than only the missing gap. This trades
    some redundant API calls for much simpler, harder-to-get-wrong cache
    logic -- acceptable for a research system where get_prices() is called
    once per symbol per PointInTimeStore construction, not per tick.
    """
    validate_symbol_name(symbol)
    path = cache_dir / f"{symbol}.parquet"
    if not path.exists():
        return None
    cached = pd.read_parquet(path)
    if cached.empty:
        return None
    # Cached frames must still pass the vendor-agnostic shape check on
    # every read -- if the cache format ever changes or a stale/partial
    # file exists, silently returning a wrong-shape frame would break
    # downstream code far from the actual defect. normalize_ohlcv raises
    # if required columns are missing.
    cached = normalize_ohlcv(cached)
    if cached.index.min().date() <= start and cached.index.max().date() >= end:
        mask = (cached.index.date >= start) & (cached.index.date <= end)
        return cached.loc[mask]
    return None


def write_cache(cache_dir: Path, symbol: str, df: pd.DataFrame) -> None:
    validate_symbol_name(symbol)
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Atomic write: staging file + rename so an interrupted process can't
    # leave a truncated/corrupted parquet at the destination (which the
    # next read would explode on). Rename on POSIX is atomic within a
    # single filesystem; the temp file lives in the same dir so this holds.
    final_path = cache_dir / f"{symbol}.parquet"
    tmp_path = cache_dir / f"{symbol}.parquet.tmp"
    df.to_parquet(tmp_path)
    tmp_path.replace(final_path)
