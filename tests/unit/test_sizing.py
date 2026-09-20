import pandas as pd
import pytest

from trading_system.config.schema import RiskConfig
from trading_system.portfolio.sizing import compute_target_weights
from trading_system.strategies.base import Signal


def _signal(symbol, asset_class, direction, vol):
    return Signal(
        symbol=symbol,
        asset_class=asset_class,
        direction=direction,
        strategy_id="test",
        timestamp=pd.Timestamp("2020-01-01"),
        annualized_vol=vol,
    )


def test_equal_risk_across_asset_classes_with_one_instrument_each():
    risk = RiskConfig(
        portfolio_vol_target_annualized=0.10,
        max_instrument_weight=1.0,
        max_asset_class_weight=1.0,
        max_gross_leverage=10.0,
    )
    signals = [
        _signal("EQ", "equity_index", 1.0, 0.16),
        _signal("FX", "fx", 1.0, 0.08),
    ]
    weights = compute_target_weights(signals, risk, vol_floor_annualized=0.01)
    # Each asset class gets equal ex-ante risk budget: weight * vol should
    # be approximately equal across the two instruments.
    risk_contrib = {sym: abs(w) * v for (sym, w), v in zip(weights.items(), [0.16, 0.08])}
    values = list(risk_contrib.values())
    assert values[0] == pytest.approx(values[1], rel=1e-6)


def test_zero_signals_produce_no_weights():
    signals = [_signal("EQ", "equity_index", 0.0, 0.16)]
    weights = compute_target_weights(signals, RiskConfig(), vol_floor_annualized=0.01)
    assert weights == {}


def test_instrument_cap_is_respected():
    risk = RiskConfig(
        portfolio_vol_target_annualized=2.0,  # deliberately huge, forces cap to bind
        max_instrument_weight=0.05,
        max_asset_class_weight=1.0,
        max_gross_leverage=10.0,
    )
    signals = [_signal("EQ", "equity_index", 1.0, 0.01)]
    weights = compute_target_weights(signals, risk, vol_floor_annualized=0.01)
    assert abs(weights["EQ"]) <= 0.05 + 1e-9


def test_gross_leverage_cap_is_respected():
    risk = RiskConfig(
        portfolio_vol_target_annualized=5.0,
        max_instrument_weight=10.0,
        max_asset_class_weight=10.0,
        max_gross_leverage=1.0,
    )
    signals = [
        _signal("A", "equity_index", 1.0, 0.05),
        _signal("B", "fx", -1.0, 0.05),
    ]
    weights = compute_target_weights(signals, risk, vol_floor_annualized=0.01)
    assert sum(abs(w) for w in weights.values()) <= 1.0 + 1e-9


def test_direction_sign_is_preserved():
    signals = [
        _signal("LONG", "equity_index", 1.0, 0.1),
        _signal("SHORT", "fx", -1.0, 0.1),
    ]
    weights = compute_target_weights(signals, RiskConfig(), vol_floor_annualized=0.01)
    assert weights["LONG"] > 0
    assert weights["SHORT"] < 0
