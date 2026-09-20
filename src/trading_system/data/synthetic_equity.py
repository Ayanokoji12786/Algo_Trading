"""Synthetic NSE-style equity universe for pipeline development
(India_Implementation_Spec.md EQ_MOM_01).

Same status as data/synthetic.py: fabricated data used to prove the
cross-sectional momentum pipeline is leakage-safe and mechanically correct,
not evidence about real NSE stocks. Every price series here is fictional.

Generation model: each stock's daily return = a common market factor + its
sector's factor + an idiosyncratic, regime-switching "alpha" component
(same regime-switching style as data/synthetic.py's trend generator, reused
so a cross-sectional momentum strategy has genuine, known relative
persistence to detect -- a stock's own alpha regime should keep it in the
top or bottom of the cross-section for a while, which is the entire premise
being tested, not assumed true of real markets).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from datetime import date
from dataclasses import dataclass, field

from trading_system.data.interfaces import ContractMeta
from trading_system.util import stable_hash

_TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class NSEEquityConfig:
    sectors: tuple[str, ...] = (
        "financials",
        "it",
        "energy",
        "fmcg",
        "auto",
        "pharma",
        "metals",
        "infra",
    )
    stocks_per_sector: int = 8  # 8 x 8 = 64 names, a Nifty-200-like scale down
    start_date: date = date(2010, 1, 1)
    end_date: date = date(2023, 12, 31)
    random_seed: int = 202
    market_annual_vol: float = 0.15
    sector_annual_vol: float = 0.10
    idio_annual_vol: float = 0.20


class SyntheticNSEEquityDataSource:
    def __init__(self, config: NSEEquityConfig):
        self._config = config
        self._universe = self._build_universe()
        rng = np.random.default_rng(config.random_seed)
        dates = pd.bdate_range(config.start_date, config.end_date)
        n = len(dates)

        market_returns = rng.normal(
            0.0003, config.market_annual_vol / np.sqrt(_TRADING_DAYS_PER_YEAR), n
        )
        sector_returns = {
            sector: rng.normal(
                0.0, config.sector_annual_vol / np.sqrt(_TRADING_DAYS_PER_YEAR), n
            )
            for sector in config.sectors
        }

        self._prices: dict[str, pd.DataFrame] = {}
        for meta in self._universe:
            self._prices[meta.symbol] = self._generate_series(
                meta, dates, market_returns, sector_returns[meta.sector], rng
            )

    def get_universe(self) -> list[ContractMeta]:
        return list(self._universe)

    def get_prices(self, symbol: str) -> pd.DataFrame:
        return self._prices[symbol].copy()

    def _build_universe(self) -> list[ContractMeta]:
        universe = []
        for sector in self._config.sectors:
            for i in range(self._config.stocks_per_sector):
                universe.append(
                    ContractMeta(
                        symbol=f"{sector.upper()}_{i}",
                        asset_class="nse_equity",
                        currency="INR",
                        sector=sector,
                    )
                )
        return universe

    def _generate_series(
        self,
        meta: ContractMeta,
        dates: pd.DatetimeIndex,
        market_returns: np.ndarray,
        sector_returns: np.ndarray,
        shared_rng: np.random.Generator,
    ) -> pd.DataFrame:
        n = len(dates)
        rng = np.random.default_rng(
            self._config.random_seed + stable_hash(meta.symbol) % (2**16) + 1
        )
        idio_daily_vol = self._config.idio_annual_vol / np.sqrt(_TRADING_DAYS_PER_YEAR)

        # Regime-switching idiosyncratic alpha, same construction as
        # data/synthetic.py's trend generator, so relative winners/losers
        # persist for a while -- the premise a momentum strategy tests.
        regime_length = rng.integers(150, 400)
        alpha = np.zeros(n)
        pos = 0
        while pos < n:
            length = min(regime_length, n - pos)
            magnitude = rng.uniform(0.0, 0.06) / _TRADING_DAYS_PER_YEAR
            sign = rng.choice([-1.0, 1.0])
            alpha[pos : pos + length] = sign * magnitude
            pos += length
            regime_length = rng.integers(150, 400)

        idio_noise = rng.normal(0.0, idio_daily_vol, n)
        total_returns = market_returns + sector_returns + alpha + idio_noise
        close = 100.0 * np.exp(np.cumsum(total_returns))

        intraday_range = np.abs(rng.normal(0.0, idio_daily_vol * 0.3, n))
        high = close * (1 + intraday_range)
        low = close * (1 - intraday_range)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        volume = rng.uniform(1e5, 1e6, n)

        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        )
