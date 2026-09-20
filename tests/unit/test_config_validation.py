"""Regression tests for the config-validation audit findings: previously
CostConfig, IndiaCostConfig, and SystemConfig accepted invalid scenario/
mode values silently at construction, only surfacing as a KeyError deep
inside a backtest. Now validated at __post_init__.
"""
import pytest

from trading_system.config.schema import CostConfig, SystemConfig
from trading_system.execution.india_costs import IndiaCostConfig


def test_cost_config_rejects_bad_scenario():
    with pytest.raises(ValueError):
        CostConfig(scenario="stress_5x")  # typo / not in the known set


def test_india_cost_config_rejects_bad_scenario():
    with pytest.raises(ValueError):
        IndiaCostConfig(scenario="stress_5x")


def test_system_config_rejects_typo_mode():
    with pytest.raises(ValueError):
        SystemConfig(mode="papper")  # type: ignore[arg-type]


def test_system_config_still_blocks_live_mode():
    with pytest.raises(ValueError):
        SystemConfig(mode="live")


def test_valid_scenarios_still_accepted():
    for s in ("base", "stress_2x", "stress_3x"):
        CostConfig(scenario=s)
        IndiaCostConfig(scenario=s)
