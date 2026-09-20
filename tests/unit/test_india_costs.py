from trading_system.execution.india_costs import CURRENT_INDIA_COST_RATES, IndiaCostConfig, india_trade_cost


def test_nse_equity_buy_includes_stt_stamp_and_sebi_fee():
    config = IndiaCostConfig()
    cost = india_trade_cost(1_000_000, "nse_equity", is_buy=True, config=config)
    r = CURRENT_INDIA_COST_RATES
    expected_bps = (
        r.delivery_equity_stt_buy_bps
        + r.sebi_turnover_fee_bps
        + r.equity_futures_stamp_duty_buy_bps
        + r.brokerage_bps_estimate
        + r.exchange_spread_impact_bps_estimate
        + r.brokerage_bps_estimate * r.gst_rate_on_brokerage
    )
    assert cost == 1_000_000 * expected_bps / 10_000.0


def test_nse_equity_sell_has_no_stamp_duty():
    config = IndiaCostConfig()
    buy_cost = india_trade_cost(1_000_000, "nse_equity", is_buy=True, config=config)
    sell_cost = india_trade_cost(1_000_000, "nse_equity", is_buy=False, config=config)
    assert sell_cost < buy_cost  # stamp duty only applies on the buy side


def test_mcx_commodity_cost_uses_commodity_stamp_duty():
    config = IndiaCostConfig()
    cost_buy = india_trade_cost(1_000_000, "mcx_commodity", is_buy=True, config=config)
    cost_sell = india_trade_cost(1_000_000, "mcx_commodity", is_buy=False, config=config)
    assert cost_buy > cost_sell


def test_cost_scenario_stress_scales_only_estimated_components():
    base = IndiaCostConfig(scenario="base")
    stress = IndiaCostConfig(scenario="stress_3x")
    base_cost = india_trade_cost(1_000_000, "nse_equity", is_buy=True, config=base)
    stress_cost = india_trade_cost(1_000_000, "nse_equity", is_buy=True, config=stress)
    # Stress must increase cost, but not by exactly 3x overall since
    # statutory tax components (STT, SEBI fee, stamp duty) don't scale.
    assert stress_cost > base_cost
    assert stress_cost < base_cost * 3


def test_unsupported_asset_class_raises():
    config = IndiaCostConfig()
    try:
        india_trade_cost(1_000, "crypto", is_buy=True, config=config)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_zero_notional_is_zero_cost():
    config = IndiaCostConfig()
    assert india_trade_cost(0.0, "nse_equity", is_buy=True, config=config) == 0.0
