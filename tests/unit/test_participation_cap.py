from trading_system.portfolio.participation import apply_participation_cap


def test_uncapped_trade_passes_through():
    target = {"A": 0.10}
    current = {"A": 0.05}
    result = apply_participation_cap(
        target, current, sleeve_nav=1_000_000, median_traded_value={"A": 1_000_000_000}, cap_fraction=0.05
    )
    assert result["A"] == 0.10


def test_oversized_trade_is_capped():
    target = {"A": 0.50}
    current = {"A": 0.0}
    # median traded value = 1,000,000; cap 5% -> max notional = 50,000
    # sleeve_nav = 1,000,000 -> max delta weight = 50,000/1,000,000 = 0.05
    result = apply_participation_cap(
        target, current, sleeve_nav=1_000_000, median_traded_value={"A": 1_000_000}, cap_fraction=0.05
    )
    assert result["A"] == 0.05


def test_zero_liquidity_blocks_the_trade_entirely():
    target = {"A": 0.10}
    current = {"A": 0.02}
    result = apply_participation_cap(
        target, current, sleeve_nav=1_000_000, median_traded_value={"A": 0.0}, cap_fraction=0.05
    )
    assert result["A"] == current["A"]


def test_negative_delta_capped_symmetrically():
    target = {"A": -0.50}
    current = {"A": 0.0}
    result = apply_participation_cap(
        target, current, sleeve_nav=1_000_000, median_traded_value={"A": 1_000_000}, cap_fraction=0.05
    )
    assert result["A"] == -0.05


def test_missing_symbol_in_median_traded_value_blocks_trade():
    target = {"NEW": 0.10}
    current = {}
    result = apply_participation_cap(
        target, current, sleeve_nav=1_000_000, median_traded_value={}, cap_fraction=0.05
    )
    assert result["NEW"] == 0.0
