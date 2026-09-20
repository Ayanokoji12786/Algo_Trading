from datetime import date

import pytest

from trading_system.data.combined import CombinedDataSource
from trading_system.data.interfaces import ContractMeta
from trading_system.data.synthetic_equity import NSEEquityConfig, SyntheticNSEEquityDataSource


class _FakeSource:
    def __init__(self, symbols):
        self._symbols = symbols

    def get_universe(self):
        return [ContractMeta(symbol=s, asset_class="test") for s in self._symbols]

    def get_prices(self, symbol):
        raise NotImplementedError


def test_combines_universes_without_collision():
    a = _FakeSource(["A1", "A2"])
    b = _FakeSource(["B1", "B2"])
    combined = CombinedDataSource([a, b])
    symbols = {m.symbol for m in combined.get_universe()}
    assert symbols == {"A1", "A2", "B1", "B2"}


def test_raises_on_symbol_collision():
    a = _FakeSource(["X"])
    b = _FakeSource(["X"])
    with pytest.raises(ValueError):
        CombinedDataSource([a, b])


def test_get_prices_routes_to_correct_underlying_source():
    eq = SyntheticNSEEquityDataSource(
        NSEEquityConfig(
            sectors=("it",),
            stocks_per_sector=2,
            start_date=date(2015, 1, 1),
            end_date=date(2016, 12, 31),
        )
    )
    combined = CombinedDataSource([eq])
    symbol = eq.get_universe()[0].symbol
    pd_a = eq.get_prices(symbol)
    pd_b = combined.get_prices(symbol)
    assert pd_a.equals(pd_b)
