from datetime import date

from trading_system.data.synthetic_curve import MCXCurveConfig, SyntheticMCXCurveDataSource
from trading_system.data.roll import active_contract_for, front_and_next_contracts


def _source():
    config = MCXCurveConfig(
        commodities=("GOLD", "SILVER"),
        start_date=date(2015, 1, 1),
        end_date=date(2016, 12, 31),
    )
    return SyntheticMCXCurveDataSource(config)


def test_universe_has_index_and_dated_contracts_per_commodity():
    source = _source()
    universe = source.get_universe()
    gold_index = [m for m in universe if m.symbol == "GOLD_INDEX"]
    gold_contracts = [
        m for m in universe if m.underlying == "GOLD" and m.asset_class == "mcx_commodity"
    ]
    assert len(gold_index) == 1
    assert gold_index[0].expiry_date is None
    assert len(gold_contracts) > 12  # multi-year monthly contracts
    assert all(m.expiry_date is not None for m in gold_contracts)


def test_contracts_have_no_price_data_after_expiry():
    source = _source()
    universe = source.get_universe()
    a_contract = next(
        m for m in universe if m.underlying == "GOLD" and m.asset_class == "mcx_commodity"
    )
    prices = source.get_prices(a_contract.symbol)
    assert prices.index.max().date() <= a_contract.expiry_date


def test_front_and_next_contracts_ordering():
    source = _source()
    universe = source.get_universe()
    front, next_ = front_and_next_contracts("GOLD", date(2015, 3, 1), universe)
    assert front is not None and next_ is not None
    assert front.expiry_date < next_.expiry_date


def test_active_contract_rolls_before_expiry():
    source = _source()
    universe = source.get_universe()
    front, next_ = front_and_next_contracts("GOLD", date(2015, 1, 5), universe)
    # A few days before the front contract's expiry, the roll rule should
    # already have moved to the next contract (default 5-day buffer).
    near_expiry = front.expiry_date
    from datetime import timedelta

    active = active_contract_for("GOLD", near_expiry - timedelta(days=1), universe)
    assert active == next_.symbol


def test_active_contract_none_past_all_expiries():
    source = _source()
    universe = source.get_universe()
    far_future = date(2100, 1, 1)
    assert active_contract_for("GOLD", far_future, universe) is None
