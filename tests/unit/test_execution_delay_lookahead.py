"""Regression tests for the negative-execution-delay look-ahead bug.

Before the fix, next_execution_date(cal, decision, -1) returned a FUTURE
calendar date (Python negative-index wraparound through calendar[exec_pos]
when exec_pos went negative), silently executing trades on data that
didn't exist at decision time -- the exact failure this whole system is
built to prevent. Now a negative delay raises, and config/SleeveSpec
validation rejects it at construction too.
"""
import pandas as pd
import pytest

from trading_system.backtest.blended_engine import SleeveSpec
from trading_system.config.schema import BacktestConfig
from trading_system.execution.simulator import next_execution_date


def _calendar():
    return pd.bdate_range("2020-01-01", periods=100)


def test_negative_delay_raises_not_wraparound():
    cal = _calendar()
    with pytest.raises(ValueError):
        next_execution_date(cal, cal[0], -1)


def test_zero_delay_executes_same_day():
    cal = _calendar()
    assert next_execution_date(cal, cal[5], 0) == cal[5]


def test_positive_delay_executes_later_never_earlier():
    cal = _calendar()
    decision = cal[10]
    exec_date = next_execution_date(cal, decision, 2)
    assert exec_date == cal[12]
    assert exec_date > decision


def test_delay_past_end_of_calendar_returns_none():
    cal = _calendar()
    assert next_execution_date(cal, cal[-1], 1) is None


def test_backtest_config_rejects_negative_delay():
    with pytest.raises(ValueError):
        BacktestConfig(execution_delay_sessions=-1)


def test_backtest_config_rejects_bad_frequency():
    with pytest.raises(ValueError):
        BacktestConfig(rebalance_frequency="monthly")  # plain engine only does daily/weekly
    with pytest.raises(ValueError):
        BacktestConfig(rebalance_frequency="weeky")  # typo


def test_backtest_config_rejects_nonpositive_capital():
    with pytest.raises(ValueError):
        BacktestConfig(initial_capital=0)
    with pytest.raises(ValueError):
        BacktestConfig(initial_capital=-1000)


def test_backtest_config_accepts_valid_values():
    BacktestConfig(rebalance_frequency="daily", execution_delay_sessions=0)
    BacktestConfig(rebalance_frequency="weekly", execution_delay_sessions=2)


class _DummySleeve:
    sleeve_id = "dummy"

    def compute_weights(self, store, as_of):
        return {}


def test_sleeve_spec_rejects_negative_delay():
    with pytest.raises(ValueError):
        SleeveSpec(_DummySleeve(), rebalance_frequency="daily", risk_share=0.5, execution_delay_sessions=-1)


def test_sleeve_spec_rejects_bad_frequency():
    with pytest.raises(ValueError):
        SleeveSpec(_DummySleeve(), rebalance_frequency="fortnightly", risk_share=0.5)


def test_sleeve_spec_rejects_negative_risk_share():
    with pytest.raises(ValueError):
        SleeveSpec(_DummySleeve(), rebalance_frequency="daily", risk_share=-0.1)


def test_sleeve_spec_rejects_nonpositive_participation_cap():
    with pytest.raises(ValueError):
        SleeveSpec(
            _DummySleeve(),
            rebalance_frequency="daily",
            risk_share=0.5,
            participation_cap_fraction=0.0,
        )


def test_sleeve_spec_accepts_valid_values():
    SleeveSpec(_DummySleeve(), rebalance_frequency="monthly", risk_share=0.5)
    SleeveSpec(
        _DummySleeve(),
        rebalance_frequency="daily",
        risk_share=1.0,
        execution_delay_sessions=1,
        participation_cap_fraction=0.05,
    )
