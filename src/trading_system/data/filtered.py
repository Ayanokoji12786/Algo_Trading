"""Universe-filtering wrapper for leave-one-out robustness tests
(Prompt.md S21, S24: "leave-one-market-out tests", "leave-one-asset-class-out
tests"). Wraps an existing DataSource and restricts get_universe() without
touching get_prices() -- so the underlying price series are never
regenerated. This matters: regenerating a synthetic source with a different
universe would consume a different sequence of RNG draws and produce
genuinely different prices for the "same" instrument, contaminating any
comparison. Wrapping the already-built source keeps prices identical across
every leave-one-out variant, isolating the universe change as the only
difference.
"""
from __future__ import annotations

from trading_system.data.interfaces import ContractMeta, DataSource


class FilteredDataSource:
    def __init__(
        self,
        source: DataSource,
        excluded_symbols: frozenset[str] = frozenset(),
        excluded_asset_classes: frozenset[str] = frozenset(),
    ):
        self._source = source
        self._universe = [
            m
            for m in source.get_universe()
            if m.symbol not in excluded_symbols
            and m.asset_class not in excluded_asset_classes
        ]

    def get_universe(self) -> list[ContractMeta]:
        return list(self._universe)

    def get_prices(self, symbol: str):
        return self._source.get_prices(symbol)
