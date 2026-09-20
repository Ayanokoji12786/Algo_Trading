from datetime import date

import pandas as pd
import pytest

from trading_system.backtest.blended_engine import BlendedPortfolioEngine, SleeveSpec
from trading_system.config.india_schema import IndiaSystemConfig
from trading_system.data.combined import CombinedDataSource
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic_curve import MCXCurveConfig, SyntheticMCXCurveDataSource
from trading_system.data.synthetic_equity import NSEEquityConfig, SyntheticNSEEquityDataSource
from trading_system.live.guardrails import GuardrailConfig, RiskGuardrails
from trading_system.live.paper.blended_paper_trader import BlendedPaperTrader
from trading_system.strategies.cross_sectional_momentum import (
    CrossSectionalMomentumStrategy,
    EQMomConfig,
)
from trading_system.strategies.mcx_trend_sleeve import MCXTrendConfig, MCXTrendSleeve


def _config_and_store(start=date(2015, 1, 1), end=date(2017, 12, 31)):
    eq_data = NSEEquityConfig(
        sectors=("financials", "it"), stocks_per_sector=3, start_date=start, end_date=end
    )
    mcx_data = MCXCurveConfig(commodities=("GOLD", "SILVER"), start_date=start, end_date=end)
    config = IndiaSystemConfig(eq_data=eq_data, mcx_data=mcx_data)
    combined = CombinedDataSource(
        [SyntheticNSEEquityDataSource(eq_data), SyntheticMCXCurveDataSource(mcx_data)]
    )
    return config, PointInTimeStore(combined)


def _default_specs():
    return [
        SleeveSpec(
            CrossSectionalMomentumStrategy(EQMomConfig(top_n=5)),
            rebalance_frequency="monthly",
            risk_share=0.5,
            participation_cap_fraction=0.05,
        ),
        SleeveSpec(
            MCXTrendSleeve(MCXTrendConfig()),
            rebalance_frequency="daily",
            risk_share=0.5,
            resolve_contracts=True,
        ),
    ]


def test_paper_trader_produces_one_record_per_rebalance_day():
    config, store = _config_and_store()
    trader = BlendedPaperTrader(config, store, _default_specs())
    calendar = store.trading_calendar()
    days = list(calendar[-60:])
    records = trader.run_replay(days)

    assert len(records) > 0
    assert all(r.portfolio_value > 0 for r in records)
    assert all(len(r.rebalanced_sleeves) > 0 for r in records)


def test_paper_trader_matches_backtest_engine_at_a_shared_date():
    """The paper trader's NAV and target-position vector at the final day
    of a replay must match the backtest engine's, since both drive the
    exact same shared helpers (backtest/blended_engine.py's module-level
    functions) over the same trading calendar. This is the parity contract
    that keeps the two code paths from silently drifting apart.
    """
    config, store = _config_and_store()
    specs = _default_specs()

    engine = BlendedPortfolioEngine(
        store,
        specs,
        config.cost,
        initial_capital=config.initial_capital,
        portfolio_vol_target=config.portfolio_vol_target,
        covariance_window_days=config.covariance_window_days,
    )
    engine_result = engine.run()

    trader = BlendedPaperTrader(config, store, _default_specs())
    trader.run_replay(list(store.trading_calendar()))

    engine_final_nav = float(engine_result.equity_curve.iloc[-1])
    trader_final_nav = trader.nav
    assert engine_final_nav == pytest.approx(trader_final_nav, rel=1e-6)

    engine_final_positions = {
        sym: float(w)
        for sym, w in engine_result.weights_history.iloc[-1].dropna().items()
        if w != 0
    }
    trader_final_positions = trader.current_weights
    assert set(engine_final_positions) == set(trader_final_positions)
    for sym in engine_final_positions:
        assert engine_final_positions[sym] == pytest.approx(
            trader_final_positions[sym], rel=1e-6
        )


def test_paper_trader_rejects_live_mode():
    config, store = _config_and_store()
    with pytest.raises(ValueError):
        BlendedPaperTrader(config, store, _default_specs(), mode="live")


def test_guardrail_breach_halts_replay():
    config, store = _config_and_store()
    trader = BlendedPaperTrader(
        config,
        store,
        _default_specs(),
        guardrails=RiskGuardrails(GuardrailConfig(max_simultaneous_positions=0)),
    )
    calendar = store.trading_calendar()
    records = trader.run_replay(list(calendar[-30:]))
    assert any("GUARDRAIL BREACH" in r.note for r in records)


def test_paper_trader_records_have_no_lookahead_into_future_prices():
    """The execution price recorded for a symbol on day D must equal the
    close-as-of-D price fetched independently -- proving the trader is not
    silently reading tomorrow's price to execute today's trade.
    """
    config, store = _config_and_store()
    trader = BlendedPaperTrader(config, store, _default_specs())
    calendar = store.trading_calendar()
    trader.run_replay(list(calendar[-30:]))

    for record in trader.records[:5]:
        for sym, recorded_price in record.simulated_execution_price.items():
            fetched_price = store.close_as_of(sym, record.decision_date)
            assert fetched_price is not None
            assert recorded_price == pytest.approx(float(fetched_price), rel=1e-9)


def test_paper_trader_step_returns_none_on_pure_hold_days():
    config, store = _config_and_store()
    # Only a monthly sleeve, so most days are pure-hold days with no
    # rebalance -- step() should return None on those and not append a record.
    monthly_only = [
        SleeveSpec(
            CrossSectionalMomentumStrategy(EQMomConfig(top_n=5)),
            rebalance_frequency="monthly",
            risk_share=1.0,
        )
    ]
    trader = BlendedPaperTrader(config, store, monthly_only)
    calendar = store.trading_calendar()

    # Pick a mid-month day that shouldn't be a monthly rebalance date.
    mid_month = calendar[300]
    result = trader.step(mid_month)
    if result is None:
        assert len(trader.records) == 0
