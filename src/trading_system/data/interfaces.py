"""Data-source interface.

Any real vendor (futures OHLC/settlement feed, broker historical API, local
CSV dump) implements this same protocol so that everything downstream --
features, strategies, backtest engine -- is unaffected by the choice of
Implementation_Spec.md S6.1. The synthetic source in synthetic.py is one
implementation, used only to develop and pipeline-test the system before a
real vendor is wired in.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class ContractMeta:
    symbol: str
    asset_class: str
    currency: str = "USD"
    multiplier: float = 1.0
    # Additive, optional fields (default to "neutral" values) so every
    # existing DataSource/ContractMeta construction site remains valid
    # unchanged -- added for the India NSE+MCX system (Docs/India_Implementation_Spec.md):
    # `sector` supports EQ_MOM_01's sector concentration cap; `underlying` +
    # `expiry_date` let multiple dated contracts (e.g. MCX_TREND_01/MCX_CARRY_01's
    # front/next contracts) be grouped and rolled without guessing from the symbol string.
    sector: str = ""
    underlying: str = ""
    expiry_date: date | None = None


class DataSource(Protocol):
    def get_universe(self) -> list[ContractMeta]:
        """Return the pre-declared instrument universe.

        Must be decided before any performance is observed (Research.md
        "Market and instruments") -- a real implementation should apply a
        fixed liquidity/history rule, not hand-pick winners after the fact.
        """
        ...

    def get_prices(self, symbol: str) -> pd.DataFrame:
        """Return a DataFrame indexed by date with at least an
        ``open``, ``high``, ``low``, ``close``, ``volume`` column, sorted
        chronologically, for the full history of ``symbol``.

        Note: this returns the *full* series. Callers must never hand this
        directly to strategy/feature code -- route it through
        PointInTimeStore so no code path can see beyond its decision time.
        """
        ...
