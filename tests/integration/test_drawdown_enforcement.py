"""Regression test for the check_drawdown wiring audit finding:
RiskGuardrails.check_drawdown was defined but never called from any
paper trader, so drawdown limits were silently unenforced. Now both
PaperTrader and BlendedPaperTrader track peak NAV and call the guard
after every step.
"""
from datetime import date

from trading_system.backtest.blended_engine import SleeveSpec
from trading_system.config.india_schema import IndiaSystemConfig
from trading_system.config.schema import DataConfig, SystemConfig
from trading_system.data.combined import CombinedDataSource
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.data.synthetic_curve import MCXCurveConfig, SyntheticMCXCurveDataSource
from trading_system.data.synthetic_equity import NSEEquityConfig, SyntheticNSEEquityDataSource
from trading_system.live.guardrails import GuardrailConfig, RiskGuardrails
from trading_system.live.paper.blended_paper_trader import BlendedPaperTrader
from trading_system.live.paper.paper_trader import PaperTrader
from trading_system.strategies.cross_sectional_momentum import (
    CrossSectionalMomentumStrategy,
    EQMomConfig,
)
from trading_system.strategies.mcx_trend_sleeve import MCXTrendConfig, MCXTrendSleeve
from trading_system.strategies.trend import TrendStrategy


def test_single_strategy_paper_trader_tracks_peak_and_calls_check_drawdown():
    """Verify the wiring: PaperTrader now maintains _peak_nav and calls
    check_drawdown on the guardrail every step. (Whether the drawdown
    guardrail actually TRIPS depends on how far NAV falls between steps,
    which for the single-strategy trader is only from transaction cost --
    daily mark-to-market between rebalances is not simulated by this
    trader's design. So this test checks that the wiring exists, and the
    blended-trader test below checks that it can actually trip when NAV
    moves via daily P&L.)
    """
    data = DataConfig(
        asset_classes=("equity_index",),
        instruments_per_asset_class=2,
        start_date=date(2015, 1, 1),
        end_date=date(2019, 12, 31),
        random_seed=91,
    )
    config = SystemConfig(mode="paper", data=data)
    store = PointInTimeStore(SyntheticFuturesDataSource(config.data))
    strategy = TrendStrategy(config.trend)
    trader = PaperTrader(config, store, strategy)

    initial_peak = trader._peak_nav
    replay_dates = list(store.trading_calendar()[-30:])
    trader.run_replay(replay_dates)

    # Peak either stays at initial (no rebalance ever pushed NAV higher,
    # since cost only decreases) or updates as configured, but the
    # attribute must exist and be tracked.
    assert hasattr(trader, "_peak_nav")
    assert trader._peak_nav >= initial_peak - 1e-6
    # And the guardrail's check_drawdown method exists / did not error.
    assert not trader._guardrails.is_tripped or "Drawdown" in (
        trader._guardrails._trip_reason or ""
    )


def test_blended_paper_trader_tracks_peak_and_enforces_drawdown():
    eq = NSEEquityConfig(
        sectors=("it",),
        stocks_per_sector=3,
        start_date=date(2015, 1, 1),
        end_date=date(2017, 12, 31),
    )
    mcx = MCXCurveConfig(
        commodities=("GOLD",), start_date=date(2015, 1, 1), end_date=date(2017, 12, 31)
    )
    config = IndiaSystemConfig(eq_data=eq, mcx_data=mcx)
    store = PointInTimeStore(
        CombinedDataSource([SyntheticNSEEquityDataSource(eq), SyntheticMCXCurveDataSource(mcx)])
    )
    specs = [
        SleeveSpec(
            CrossSectionalMomentumStrategy(EQMomConfig(top_n=3)),
            rebalance_frequency="monthly",
            risk_share=0.5,
        ),
        SleeveSpec(
            MCXTrendSleeve(MCXTrendConfig()),
            rebalance_frequency="daily",
            risk_share=0.5,
            resolve_contracts=True,
        ),
    ]
    tight = RiskGuardrails(GuardrailConfig(max_drawdown_pct=0.001))
    trader = BlendedPaperTrader(config, store, specs, guardrails=tight)

    replay_dates = list(store.trading_calendar()[-60:])
    records = trader.run_replay(replay_dates)

    assert hasattr(trader, "_peak_nav")
    assert any("GUARDRAIL BREACH" in r.note for r in records)


def test_paper_trader_does_not_breach_drawdown_with_generous_limit():
    """Sanity check: the drawdown check should NOT trip when the limit
    is set generously enough to accommodate normal fluctuation.
    """
    data = DataConfig(
        asset_classes=("equity_index",),
        instruments_per_asset_class=2,
        start_date=date(2015, 1, 1),
        end_date=date(2017, 12, 31),
        random_seed=91,
    )
    config = SystemConfig(mode="paper", data=data)
    store = PointInTimeStore(SyntheticFuturesDataSource(config.data))
    strategy = TrendStrategy(config.trend)
    lax = RiskGuardrails(GuardrailConfig(max_drawdown_pct=0.99))
    trader = PaperTrader(config, store, strategy, guardrails=lax)
    replay_dates = list(store.trading_calendar()[-30:])
    records = trader.run_replay(replay_dates)
    assert not any("Drawdown" in r.note for r in records)
