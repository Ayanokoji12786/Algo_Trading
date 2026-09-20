"""Regression test for the participation-cap sell/exit bug found in the
audit: previously apply_participation_cap iterated only target_weights,
so a symbol present in current but absent from target (a full exit)
bypassed the cap entirely and disappeared from the returned dict --
letting the caller sell the whole position in one bar regardless of
liquidity. Fix iterates the union of target and current keys.
"""
from trading_system.portfolio.participation import apply_participation_cap


def test_full_exit_is_capped_by_median_traded_value():
    """current 20%, target 0% (full exit), sleeve NAV 1M, median traded
    value 100k, cap 5% => max notional 5k => max delta weight 0.5%.
    """
    result = apply_participation_cap(
        target_weights={},
        current_weights={"A": 0.20},
        sleeve_nav=1_000_000,
        median_traded_value={"A": 100_000},
        cap_fraction=0.05,
    )
    # Should NOT be a full exit -- capped at delta = -0.005 -> new_w = 0.195
    assert "A" in result
    assert abs(result["A"] - 0.195) < 1e-9


def test_partial_reduction_is_capped():
    """current 20%, target 10%, cap allows only 0.5% delta -> new_w = 19.5%."""
    result = apply_participation_cap(
        target_weights={"A": 0.10},
        current_weights={"A": 0.20},
        sleeve_nav=1_000_000,
        median_traded_value={"A": 100_000},
        cap_fraction=0.05,
    )
    assert abs(result["A"] - 0.195) < 1e-9


def test_within_cap_trade_passes_through_uncapped():
    """delta 5% x 1M = 50k, cap 5% x 1M = 50k -> allowed exactly."""
    result = apply_participation_cap(
        target_weights={"A": 0.10},
        current_weights={"A": 0.05},
        sleeve_nav=1_000_000,
        median_traded_value={"A": 1_000_000},
        cap_fraction=0.05,
    )
    assert result["A"] == 0.10
