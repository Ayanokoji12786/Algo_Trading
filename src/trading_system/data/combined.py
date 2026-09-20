"""Merges multiple DataSource instances into one universe.

This is the concrete "blending" primitive (Docs/India_Implementation_Spec.md
S3): combining, say, an NSE-equity source and an MCX-commodity source (or
later, a real Zerodha adapter and a real global-futures vendor) into one
PointInTimeStore/backtest is just wrapping them in a CombinedDataSource --
nothing about PointInTimeStore, features, or strategies needs to know that
more than one underlying source exists.
"""
from __future__ import annotations

from trading_system.data.interfaces import ContractMeta, DataSource


class CombinedDataSource:
    def __init__(self, sources: list[DataSource]):
        self._by_symbol: dict[str, DataSource] = {}
        self._universe: list[ContractMeta] = []
        for source in sources:
            for meta in source.get_universe():
                if meta.symbol in self._by_symbol:
                    raise ValueError(
                        f"Symbol collision while combining data sources: "
                        f"'{meta.symbol}' is provided by more than one source"
                    )
                self._by_symbol[meta.symbol] = source
                self._universe.append(meta)

    def get_universe(self) -> list[ContractMeta]:
        return list(self._universe)

    def get_prices(self, symbol: str):
        return self._by_symbol[symbol].get_prices(symbol)
