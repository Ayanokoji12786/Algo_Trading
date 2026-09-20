"""Synthetic MCX-style multi-expiry commodity data for pipeline development
(India_Implementation_Spec.md MCX_TREND_01, MCX_CARRY_01).

Produces TWO kinds of instrument per commodity, matching the research's
explicit "keep two separate objects" requirement:

- ``{COMMODITY}_INDEX``: a clean, deterministic return-linked continuous
  series (``asset_class="mcx_commodity_index"``) used ONLY for signal
  generation (MCX_TREND_01's trend score). This is not itself tradable.
- ``{COMMODITY}_{YYYYMM}``: individual dated futures contracts
  (``asset_class="mcx_commodity"``, ``underlying=COMMODITY``,
  ``expiry_date`` set) whose own price is used for P&L/execution and for
  MCX_CARRY_01's curve slope. A contract's price = the index level plus a
  basis that depends on time-to-expiry and a regime-switching curve-slope
  factor -- giving carry a genuine, persistent (if fabricated) signal to
  detect, the same way data/synthetic.py's regime-switching drift gives
  trend a genuine signal. None of this is evidence about real MCX curves.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from trading_system.data.interfaces import ContractMeta
from trading_system.util import stable_hash

_TRADING_DAYS_PER_YEAR = 252
_DEFAULT_COMMODITIES = (
    "GOLD",
    "SILVER",
    "CRUDEOIL",
    "NATURALGAS",
    "COPPER",
    "ALUMINIUM",
    "ZINC",
)


@dataclass(frozen=True)
class MCXCurveConfig:
    commodities: tuple[str, ...] = _DEFAULT_COMMODITIES
    start_date: date = date(2010, 1, 1)
    end_date: date = date(2023, 12, 31)
    random_seed: int = 303
    annual_vol: float = 0.20
    listed_months_before_expiry: int = 6  # how far ahead a contract is listed
    contract_cycle_months: int = 1  # a new expiry every N months


def _month_end_expiries(start: date, end: date, cycle_months: int) -> list[date]:
    expiries = []
    cursor = pd.Timestamp(start).to_period("M").to_timestamp("M")
    end_ts = pd.Timestamp(end)
    while cursor <= end_ts:
        expiries.append(cursor.date())
        cursor = (cursor + pd.DateOffset(months=cycle_months)).to_period("M").to_timestamp("M")
    return expiries


class SyntheticMCXCurveDataSource:
    def __init__(self, config: MCXCurveConfig):
        self._config = config
        self._prices: dict[str, pd.DataFrame] = {}
        self._universe: list[ContractMeta] = []

        full_calendar = pd.bdate_range(config.start_date, config.end_date)

        for commodity in config.commodities:
            rng = np.random.default_rng(config.random_seed + stable_hash(commodity) % (2**16))
            index_price = self._generate_index(commodity, full_calendar, rng)
            basis_slope = self._generate_basis_slope(full_calendar, rng)

            index_symbol = f"{commodity}_INDEX"
            self._universe.append(
                ContractMeta(
                    symbol=index_symbol,
                    asset_class="mcx_commodity_index",
                    currency="INR",
                    underlying=commodity,
                )
            )
            self._prices[index_symbol] = self._to_ohlcv(index_price, full_calendar, rng)

            # Contracts listed from `listed_months_before_expiry` months
            # before `start_date` so the very first backtest day already has
            # an active front/next pair, through expiries covering `end_date`.
            list_from = pd.Timestamp(config.start_date) - pd.DateOffset(
                months=config.listed_months_before_expiry
            )
            expiries = _month_end_expiries(
                list_from.date(), config.end_date, config.contract_cycle_months
            )
            for expiry in expiries:
                listing_start = pd.Timestamp(expiry) - pd.DateOffset(
                    months=config.listed_months_before_expiry
                )
                contract_dates = full_calendar[
                    (full_calendar >= max(listing_start, full_calendar[0]))
                    & (full_calendar <= pd.Timestamp(expiry))
                ]
                if len(contract_dates) == 0:
                    continue
                symbol = f"{commodity}_{expiry.strftime('%Y%m')}"
                contract_price = self._contract_price(
                    index_price, basis_slope, full_calendar, contract_dates, expiry
                )
                self._universe.append(
                    ContractMeta(
                        symbol=symbol,
                        asset_class="mcx_commodity",
                        currency="INR",
                        underlying=commodity,
                        expiry_date=expiry,
                    )
                )
                self._prices[symbol] = self._to_ohlcv(contract_price, contract_dates, rng)

    def get_universe(self) -> list[ContractMeta]:
        return list(self._universe)

    def get_prices(self, symbol: str) -> pd.DataFrame:
        return self._prices[symbol].copy()

    def _generate_index(
        self, commodity: str, calendar: pd.DatetimeIndex, rng: np.random.Generator
    ) -> pd.Series:
        n = len(calendar)
        daily_vol = self._config.annual_vol / np.sqrt(_TRADING_DAYS_PER_YEAR)
        regime_length = rng.integers(200, 450)
        drift = np.zeros(n)
        pos = 0
        while pos < n:
            length = min(regime_length, n - pos)
            magnitude = rng.uniform(0.02, 0.10) / _TRADING_DAYS_PER_YEAR
            sign = rng.choice([-1.0, 1.0])
            drift[pos : pos + length] = sign * magnitude
            pos += length
            regime_length = rng.integers(200, 450)
        noise = rng.normal(0.0, daily_vol, n)
        log_price = np.cumsum(drift + noise)
        return pd.Series(100.0 * np.exp(log_price), index=calendar)

    def _generate_basis_slope(
        self, calendar: pd.DatetimeIndex, rng: np.random.Generator
    ) -> pd.Series:
        """Regime-switching annualized curve-slope factor: positive = contango
        (upward-sloping curve), negative = backwardation. Persistent by
        construction so MCX_CARRY_01 has a genuine (fabricated) signal.
        """
        n = len(calendar)
        regime_length = rng.integers(120, 300)
        slope = np.zeros(n)
        pos = 0
        while pos < n:
            length = min(regime_length, n - pos)
            magnitude = rng.uniform(0.0, 0.15)
            sign = rng.choice([-1.0, 1.0])
            slope[pos : pos + length] = sign * magnitude
            pos += length
            regime_length = rng.integers(120, 300)
        return pd.Series(slope, index=calendar)

    def _contract_price(
        self,
        index_price: pd.Series,
        basis_slope: pd.Series,
        full_calendar: pd.DatetimeIndex,
        contract_dates: pd.DatetimeIndex,
        expiry: date,
    ) -> pd.Series:
        idx = index_price.loc[contract_dates]
        slope = basis_slope.loc[contract_dates]
        days_to_expiry = (pd.Timestamp(expiry) - contract_dates).days.to_numpy()
        basis = slope.to_numpy() * (days_to_expiry / 365.0)
        return pd.Series(idx.to_numpy() * np.exp(basis), index=contract_dates)

    def _to_ohlcv(
        self, close: pd.Series, dates: pd.DatetimeIndex, rng: np.random.Generator
    ) -> pd.DataFrame:
        n = len(close)
        daily_vol = self._config.annual_vol / np.sqrt(_TRADING_DAYS_PER_YEAR)
        intraday_range = np.abs(rng.normal(0.0, daily_vol * 0.3, n))
        close_vals = close.to_numpy()
        high = close_vals * (1 + intraday_range)
        low = close_vals * (1 - intraday_range)
        open_ = np.roll(close_vals, 1)
        open_[0] = close_vals[0]
        volume = rng.uniform(1e3, 1e4, n)
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close_vals, "volume": volume},
            index=dates,
        )
