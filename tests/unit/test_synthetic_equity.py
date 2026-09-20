from datetime import date

from trading_system.data.synthetic_equity import NSEEquityConfig, SyntheticNSEEquityDataSource


def test_universe_size_and_sectors():
    config = NSEEquityConfig(
        sectors=("financials", "it"),
        stocks_per_sector=3,
        start_date=date(2015, 1, 1),
        end_date=date(2016, 12, 31),
    )
    source = SyntheticNSEEquityDataSource(config)
    universe = source.get_universe()
    assert len(universe) == 6
    assert {m.sector for m in universe} == {"financials", "it"}
    assert all(m.asset_class == "nse_equity" for m in universe)
    assert all(m.currency == "INR" for m in universe)


def test_prices_are_sorted_positive_and_reproducible():
    config = NSEEquityConfig(
        stocks_per_sector=2, start_date=date(2015, 1, 1), end_date=date(2017, 12, 31)
    )
    source_a = SyntheticNSEEquityDataSource(config)
    source_b = SyntheticNSEEquityDataSource(config)
    symbol = source_a.get_universe()[0].symbol
    df_a = source_a.get_prices(symbol)
    df_b = source_b.get_prices(symbol)
    assert (df_a["close"] > 0).all()
    assert df_a.index.is_monotonic_increasing
    assert df_a.equals(df_b)  # same seed -> same synthetic data
