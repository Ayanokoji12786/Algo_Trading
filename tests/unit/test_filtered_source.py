from datetime import date

from trading_system.config.schema import DataConfig
from trading_system.data.filtered import FilteredDataSource
from trading_system.data.synthetic import SyntheticFuturesDataSource


def _source():
    config = DataConfig(
        asset_classes=("equity_index", "fx"),
        instruments_per_asset_class=2,
        start_date=date(2018, 1, 1),
        end_date=date(2019, 12, 31),
        random_seed=3,
    )
    return SyntheticFuturesDataSource(config)


def test_excludes_asset_class():
    source = _source()
    filtered = FilteredDataSource(source, excluded_asset_classes=frozenset({"fx"}))
    remaining = {m.asset_class for m in filtered.get_universe()}
    assert remaining == {"equity_index"}


def test_excludes_symbol():
    source = _source()
    all_symbols = [m.symbol for m in source.get_universe()]
    excluded = all_symbols[0]
    filtered = FilteredDataSource(source, excluded_symbols=frozenset({excluded}))
    remaining = [m.symbol for m in filtered.get_universe()]
    assert excluded not in remaining
    assert len(remaining) == len(all_symbols) - 1


def test_prices_are_identical_not_regenerated():
    source = _source()
    symbol = source.get_universe()[0].symbol
    original = source.get_prices(symbol)
    filtered = FilteredDataSource(source, excluded_asset_classes=frozenset({"fx"}))
    via_filtered = filtered.get_prices(symbol)
    assert original.equals(via_filtered)
