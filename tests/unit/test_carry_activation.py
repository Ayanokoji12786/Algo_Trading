import numpy as np
import pandas as pd

from trading_system.strategies.carry_activation import evaluate_carry_activation


def _returns(seed, n=500, mean=0.0003, std=0.01):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-01", periods=n)
    return pd.Series(rng.normal(mean, std, n), index=dates)


def test_fails_when_carry_has_negative_expectancy():
    trend = _returns(1)
    carry = _returns(2, mean=-0.001)
    result = evaluate_carry_activation(
        trend,
        carry,
        carry_metrics_base={"cagr": -0.05, "sharpe": -0.3},
        carry_metrics_stress_2x={"sharpe": -0.5},
    )
    assert result["positive_net_value_after_base_costs"] is False
    assert result["passes_implemented_subset_of_gate"] is False


def test_fails_when_correlated_with_trend_even_if_profitable():
    trend = _returns(3)
    carry = trend * 1.0 + _returns(4, std=0.0001)  # near-identical to trend
    result = evaluate_carry_activation(
        trend,
        carry,
        carry_metrics_base={"cagr": 0.05, "sharpe": 0.8},
        carry_metrics_stress_2x={"sharpe": 0.3},
    )
    assert result["low_correlation_with_trend"] is False
    assert result["passes_implemented_subset_of_gate"] is False


def test_passes_when_all_implemented_criteria_hold():
    trend = _returns(5)
    carry = _returns(6)  # independent RNG stream -> ~uncorrelated
    result = evaluate_carry_activation(
        trend,
        carry,
        carry_metrics_base={"cagr": 0.04, "sharpe": 0.6},
        carry_metrics_stress_2x={"sharpe": 0.2},
    )
    assert abs(result["measured_correlation_with_trend"]) < 0.3
    assert result["passes_implemented_subset_of_gate"] is True


def test_result_always_documents_its_own_scope_limits():
    trend = _returns(7)
    carry = _returns(8)
    result = evaluate_carry_activation(
        trend, carry, carry_metrics_base={"cagr": 0.01, "sharpe": 0.1}, carry_metrics_stress_2x={"sharpe": 0.0}
    )
    assert "note" in result and "parameter stability" in result["note"]
