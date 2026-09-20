from datetime import date

import pandas as pd

from trading_system.backtest.blended_engine import BlendedPortfolioEngine, SleeveSpec
from trading_system.backtest.metrics import compute_metrics
from trading_system.data.combined import CombinedDataSource
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic_curve import MCXCurveConfig, SyntheticMCXCurveDataSource
from trading_system.data.synthetic_equity import NSEEquityConfig, SyntheticNSEEquityDataSource
from trading_system.execution.india_costs import IndiaCostConfig
from trading_system.strategies.cross_sectional_momentum import (
    CrossSectionalMomentumStrategy,
    EQMomConfig,
)
from trading_system.strategies.mcx_trend_sleeve import MCXTrendConfig, MCXTrendSleeve


def _build_store(start=date(2015, 1, 1), end=date(2018, 12, 31)):
    eq_source = SyntheticNSEEquityDataSource(
        NSEEquityConfig(
            sectors=("financials", "it"), stocks_per_sector=4, start_date=start, end_date=end
        )
    )
    mcx_source = SyntheticMCXCurveDataSource(
        MCXCurveConfig(commodities=("GOLD", "SILVER", "CRUDEOIL"), start_date=start, end_date=end)
    )
    combined = CombinedDataSource([eq_source, mcx_source])
    return PointInTimeStore(combined), eq_source, mcx_source


def _default_specs():
    eq_mom = CrossSectionalMomentumStrategy(EQMomConfig(top_n=5))
    mcx_trend = MCXTrendSleeve(MCXTrendConfig())
    return [
        SleeveSpec(eq_mom, rebalance_frequency="monthly", risk_share=0.5, participation_cap_fraction=0.05),
        SleeveSpec(mcx_trend, rebalance_frequency="daily", risk_share=0.5, resolve_contracts=True),
    ]


def test_runs_end_to_end_with_sane_equity_curve():
    store, _, _ = _build_store()
    engine = BlendedPortfolioEngine(store, _default_specs(), IndiaCostConfig())
    result = engine.run()

    assert len(result.equity_curve) > 500
    assert (result.equity_curve > 0).all()
    assert not result.trade_log.empty
    metrics = compute_metrics(result.equity_curve, result.turnover)
    assert 0.0 < metrics["annualized_vol"] < 0.5


def test_sleeves_rebalance_on_their_own_declared_frequency():
    store, _, _ = _build_store()
    engine = BlendedPortfolioEngine(store, _default_specs(), IndiaCostConfig())
    result = engine.run()

    n_days = len(store.trading_calendar())
    eq_mom_updates = len(result.sleeve_weights_history["eq_mom_01"])
    mcx_updates = len(result.sleeve_weights_history["mcx_trend_01"])

    # Monthly sleeve rebalances roughly once every ~21 trading days; daily
    # sleeve rebalances (almost) every trading day. The ratio should reflect
    # that, not be roughly equal.
    assert mcx_updates > eq_mom_updates * 5
    assert eq_mom_updates < n_days / 15  # well under one rebalance per 15 days
    assert mcx_updates > n_days * 0.8  # close to one rebalance per trading day


def test_trade_log_only_contains_known_tradable_asset_classes():
    """Regression test for the real bug found in development: EQ_MOM_01
    scoring MCX index/contract symbols because it didn't filter by asset
    class. At the engine level, this shows up as a KeyError/ValueError from
    the cost function for an unresolved or index symbol -- so simply
    running to completion without error, on top of the direct unit-level
    regression test in test_cross_sectional_momentum.py, is itself part of
    the regression coverage.
    """
    store, _, mcx_source = _build_store()
    index_symbols = {m.symbol for m in mcx_source.get_universe() if m.expiry_date is None}
    engine = BlendedPortfolioEngine(store, _default_specs(), IndiaCostConfig())
    result = engine.run()
    traded_symbols = set(result.trade_log["symbol"])
    assert traded_symbols.isdisjoint(index_symbols)


def test_mcx_roll_produces_a_trade_pair_around_expiry():
    store, _, mcx_source = _build_store()
    specs = [
        SleeveSpec(
            MCXTrendSleeve(MCXTrendConfig()),
            rebalance_frequency="daily",
            risk_share=1.0,
            resolve_contracts=True,
        )
    ]
    engine = BlendedPortfolioEngine(store, specs, IndiaCostConfig())
    result = engine.run()

    gold_contracts = sorted(
        (m for m in mcx_source.get_universe() if m.underlying == "GOLD" and m.expiry_date),
        key=lambda m: m.expiry_date,
    )
    gold_symbols = {m.symbol for m in gold_contracts}
    gold_trades = result.trade_log[result.trade_log["symbol"].isin(gold_symbols)]
    # Over a 4-year backtest with monthly GOLD contracts, multiple distinct
    # GOLD contract symbols must appear in the trade log -- i.e. the sleeve
    # actually rolled, rather than getting stuck holding one contract past
    # a point it should have moved on from (which would itself indicate
    # int he roll rule is broken, e.g. producing stale forward-filled prices).
    assert gold_trades["symbol"].nunique() > 3


def test_equity_curve_unaffected_by_data_after_the_current_simulation_day():
    """Engine-level leakage probe: a store truncated by slicing the SAME
    already-generated prices (not regenerated with a different end_date,
    which would consume a different RNG draw sequence and produce
    genuinely different noise -- see data/synthetic.py's docstring on this
    exact pitfall) must reproduce an identical equity curve up to the
    truncation point when run through the full engine.
    """
    long_store, eq_source, mcx_source = _build_store(end=date(2018, 12, 31))
    full_universe = eq_source.get_universe() + mcx_source.get_universe()
    full_prices = {
        m.symbol: (eq_source if m in eq_source.get_universe() else mcx_source).get_prices(m.symbol)
        for m in full_universe
    }
    cutoff = pd.Timestamp("2017-06-30")

    class _TruncatedSource:
        def get_universe(self):
            return full_universe

        def get_prices(self, symbol):
            df = full_prices[symbol]
            return df.loc[df.index <= cutoff].copy()

    short_store = PointInTimeStore(_TruncatedSource())

    long_result = BlendedPortfolioEngine(long_store, _default_specs(), IndiaCostConfig()).run()
    short_result = BlendedPortfolioEngine(short_store, _default_specs(), IndiaCostConfig()).run()

    common_dates = short_result.equity_curve.index
    pd.testing.assert_series_equal(
        long_result.equity_curve.loc[common_dates],
        short_result.equity_curve.loc[common_dates],
        check_names=False,
    )
