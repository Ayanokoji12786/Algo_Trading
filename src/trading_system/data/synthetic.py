"""Synthetic multi-asset futures data for pipeline development and testing.

This exists solely to unblock architecture/pipeline work while
Implementation_Spec.md S6.1 (real data vendor) is unresolved. Every price
series here is fabricated. Any backtest metric produced against it is a
correctness check on the code, not evidence about the researched trend
hypothesis -- see Implementation_Spec.md S6.1's closing note.

Generation model: each instrument's daily log return is a slowly regime-
switching drift plus idiosyncratic Gaussian noise. The regime switching
exists so that a trend-following signal has genuine, known persistence to
detect in tests (see tests/integration/test_backtest_pipeline.py), not to
imply that real markets behave this way.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from trading_system.config.schema import DataConfig
from trading_system.data.interfaces import ContractMeta
from trading_system.util import stable_hash

_ANNUAL_VOL_BY_ASSET_CLASS = {
    "equity_index": 0.16,
    "rates": 0.06,
    "fx": 0.08,
    "commodities": 0.20,
}
_TRADING_DAYS_PER_YEAR = 252


class SyntheticFuturesDataSource:
    def __init__(self, config: DataConfig):
        self._config = config
        self._universe = self._build_universe()
        self._prices = {
            meta.symbol: self._generate_series(meta)
            for meta in self._universe
        }

    def get_universe(self) -> list[ContractMeta]:
        return list(self._universe)

    def get_prices(self, symbol: str) -> pd.DataFrame:
        return self._prices[symbol].copy()

    def _build_universe(self) -> list[ContractMeta]:
        universe: list[ContractMeta] = []
        for asset_class in self._config.asset_classes:
            for i in range(self._config.instruments_per_asset_class):
                universe.append(
                    ContractMeta(
                        symbol=f"{asset_class.upper()}_{i}",
                        asset_class=asset_class,
                    )
                )
        return universe

    def _generate_series(self, meta: ContractMeta) -> pd.DataFrame:
        rng = np.random.default_rng(
            self._config.random_seed + stable_hash(meta.symbol) % (2**16)
        )
        dates = pd.bdate_range(self._config.start_date, self._config.end_date)
        n = len(dates)
        daily_vol = _ANNUAL_VOL_BY_ASSET_CLASS[meta.asset_class] / np.sqrt(
            _TRADING_DAYS_PER_YEAR
        )

        # Regime-switching drift: a new regime (and a new random drift
        # magnitude/sign) begins roughly every 250-500 sessions.
        regime_length = rng.integers(250, 500)
        drift = np.zeros(n)
        pos = 0
        while pos < n:
            length = min(regime_length, n - pos)
            magnitude = rng.uniform(0.02, 0.08) / _TRADING_DAYS_PER_YEAR
            sign = rng.choice([-1.0, 1.0])
            drift[pos : pos + length] = sign * magnitude
            pos += length
            regime_length = rng.integers(250, 500)

        noise = rng.normal(0.0, daily_vol, size=n)
        log_returns = drift + noise
        log_price = np.cumsum(log_returns)
        close = 100.0 * np.exp(log_price)

        # Minimal OHLV: open/high/low derived from close with a small
        # synthetic intraday range. Not a claim about real market microstructure.
        intraday_range = np.abs(rng.normal(0.0, daily_vol * 0.3, size=n))
        high = close * (1 + intraday_range)
        low = close * (1 - intraday_range)
        open_ = np.roll(close, 1)
        open_[0] = close[0]
        volume = rng.uniform(1e4, 1e5, size=n)

        return pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=dates,
        )
