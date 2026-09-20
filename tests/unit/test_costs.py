from trading_system.config.schema import CostConfig
from trading_system.execution.costs import trade_cost


def test_base_scenario_cost():
    cfg = CostConfig(bps_by_asset_class={"equity_index": 2.0}, scenario="base")
    assert trade_cost(1_000_000, "equity_index", cfg) == 200.0


def test_stress_scenarios_scale_linearly():
    base = CostConfig(bps_by_asset_class={"fx": 1.0}, scenario="base")
    stress2x = CostConfig(bps_by_asset_class={"fx": 1.0}, scenario="stress_2x")
    stress3x = CostConfig(bps_by_asset_class={"fx": 1.0}, scenario="stress_3x")
    base_cost = trade_cost(500_000, "fx", base)
    assert trade_cost(500_000, "fx", stress2x) == base_cost * 2
    assert trade_cost(500_000, "fx", stress3x) == base_cost * 3


def test_cost_uses_absolute_notional():
    cfg = CostConfig(bps_by_asset_class={"rates": 1.0}, scenario="base")
    assert trade_cost(-100_000, "rates", cfg) == trade_cost(100_000, "rates", cfg)
