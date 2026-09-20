import pandas as pd
import pytest

from trading_system.live.guardrails import GuardrailBreach, GuardrailConfig, RiskGuardrails


def _calendar():
    return pd.bdate_range("2020-01-01", periods=30)


def test_data_staleness_within_limit_passes():
    g = RiskGuardrails(GuardrailConfig(max_data_staleness_sessions=2))
    cal = _calendar()
    g.check_data_staleness(cal[5], cal[6], cal)  # not stale


def test_data_staleness_beyond_limit_trips():
    g = RiskGuardrails(GuardrailConfig(max_data_staleness_sessions=1))
    cal = _calendar()
    with pytest.raises(GuardrailBreach):
        g.check_data_staleness(cal[0], cal[10], cal)
    assert g.is_tripped


def test_daily_loss_within_limit_passes():
    g = RiskGuardrails(GuardrailConfig(max_daily_loss_pct=0.05))
    g.check_daily_loss(1_000_000, 970_000)  # 3% loss


def test_daily_loss_beyond_limit_trips():
    g = RiskGuardrails(GuardrailConfig(max_daily_loss_pct=0.05))
    with pytest.raises(GuardrailBreach):
        g.check_daily_loss(1_000_000, 900_000)  # 10% loss
    assert g.is_tripped


def test_drawdown_beyond_limit_trips():
    g = RiskGuardrails(GuardrailConfig(max_drawdown_pct=0.2))
    with pytest.raises(GuardrailBreach):
        g.check_drawdown(-0.35)


def test_position_count_limit():
    g = RiskGuardrails(GuardrailConfig(max_simultaneous_positions=2))
    with pytest.raises(GuardrailBreach):
        g.check_position_count({"A": 0.1, "B": 0.1, "C": 0.1})


def test_duplicate_order_rejected():
    g = RiskGuardrails()
    g.check_duplicate_order("order-1")
    with pytest.raises(GuardrailBreach):
        g.check_duplicate_order("order-1")


def test_tripped_guardrail_blocks_all_further_checks():
    g = RiskGuardrails(GuardrailConfig(max_daily_loss_pct=0.01))
    with pytest.raises(GuardrailBreach):
        g.check_daily_loss(1_000_000, 900_000)
    with pytest.raises(GuardrailBreach):
        g.check_position_count({"A": 0.1})
