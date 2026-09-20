from trading_system.features.cross_sectional import zscore_cross_section


def test_zscore_basic_properties():
    values = {"A": 1.0, "B": 2.0, "C": 3.0}
    z = zscore_cross_section(values)
    assert abs(sum(z.values())) < 1e-9  # z-scores sum to ~0
    assert z["C"] > z["B"] > z["A"]


def test_zscore_constant_values_returns_zeros():
    values = {"A": 5.0, "B": 5.0, "C": 5.0}
    z = zscore_cross_section(values)
    assert all(v == 0.0 for v in z.values())


def test_zscore_empty_input():
    assert zscore_cross_section({}) == {}


def test_zscore_single_value():
    z = zscore_cross_section({"A": 1.0})
    assert z["A"] == 0.0
