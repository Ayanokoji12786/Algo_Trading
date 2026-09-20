from datetime import date

import pandas as pd

from trading_system.data.combined import CombinedDataSource
from trading_system.data.interfaces import ContractMeta
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic_curve import MCXCurveConfig, SyntheticMCXCurveDataSource
from trading_system.data.synthetic_equity import NSEEquityConfig, SyntheticNSEEquityDataSource
from trading_system.strategies.cross_sectional_momentum import (
    CrossSectionalMomentumStrategy,
    EQMomConfig,
)


def _equity_store(**kwargs):
    config = NSEEquityConfig(
        sectors=("financials", "it", "energy"),
        stocks_per_sector=4,
        start_date=date(2015, 1, 1),
        end_date=date(2018, 12, 31),
        **kwargs,
    )
    return PointInTimeStore(SyntheticNSEEquityDataSource(config))


def test_selects_at_most_top_n():
    store = _equity_store()
    strategy = CrossSectionalMomentumStrategy(EQMomConfig(top_n=5))
    as_of = store.trading_calendar()[-1]
    weights = strategy.compute_weights(store, as_of)
    assert 0 < len(weights) <= 5


def test_all_weights_positive_long_only():
    store = _equity_store()
    strategy = CrossSectionalMomentumStrategy(EQMomConfig(top_n=10))
    as_of = store.trading_calendar()[-1]
    weights = strategy.compute_weights(store, as_of)
    assert all(w > 0 for w in weights.values())


def test_single_name_cap_respected():
    store = _equity_store()
    strategy = CrossSectionalMomentumStrategy(EQMomConfig(top_n=3, single_name_cap=0.05))
    as_of = store.trading_calendar()[-1]
    weights = strategy.compute_weights(store, as_of)
    assert all(w <= 0.05 + 1e-9 for w in weights.values())


def test_sector_cap_respected():
    store = _equity_store()
    strategy = CrossSectionalMomentumStrategy(
        EQMomConfig(top_n=12, single_name_cap=1.0, sector_cap=0.25)
    )
    as_of = store.trading_calendar()[-1]
    weights = strategy.compute_weights(store, as_of)
    sector_by_symbol = {m.symbol: m.sector for m in store.universe}
    sector_totals: dict[str, float] = {}
    for sym, w in weights.items():
        sector_totals[sector_by_symbol[sym]] = sector_totals.get(sector_by_symbol[sym], 0.0) + w
    assert all(total <= 0.25 + 1e-9 for total in sector_totals.values())


def test_returns_empty_before_minimum_history():
    store = _equity_store()
    strategy = CrossSectionalMomentumStrategy(EQMomConfig(min_history_days=252))
    early_date = store.trading_calendar()[100]  # well under 252 trading days
    weights = strategy.compute_weights(store, early_date)
    assert weights == {}


def test_ignores_non_equity_instruments_in_a_shared_universe():
    """Regression test for a real bug found during integration: the
    strategy must restrict itself to its own eligible_asset_class, not
    score every instrument in a combined multi-asset-class store.
    """
    eq_config = NSEEquityConfig(
        sectors=("it",),
        stocks_per_sector=4,
        start_date=date(2015, 1, 1),
        end_date=date(2018, 12, 31),
    )
    mcx_config = MCXCurveConfig(
        commodities=("GOLD",), start_date=date(2015, 1, 1), end_date=date(2018, 12, 31)
    )
    combined = CombinedDataSource(
        [SyntheticNSEEquityDataSource(eq_config), SyntheticMCXCurveDataSource(mcx_config)]
    )
    store = PointInTimeStore(combined)
    strategy = CrossSectionalMomentumStrategy(EQMomConfig(top_n=10))
    as_of = store.trading_calendar()[-1]
    weights = strategy.compute_weights(store, as_of)
    equity_symbols = {m.symbol for m in store.universe if m.asset_class == "nse_equity"}
    assert set(weights).issubset(equity_symbols)
    assert not any("GOLD" in sym for sym in weights)


def test_signal_at_decision_date_unaffected_by_future_prices():
    """Direct leakage probe for the cross-sectional path: a store truncated
    right after the decision date must produce the same selection/weights
    as a store that also holds later data it should never read.
    """
    eq_config = NSEEquityConfig(
        sectors=("financials", "it"),
        stocks_per_sector=5,
        start_date=date(2015, 1, 1),
        end_date=date(2018, 12, 31),
    )
    full_source = SyntheticNSEEquityDataSource(eq_config)
    universe = full_source.get_universe()
    full_prices = {m.symbol: full_source.get_prices(m.symbol) for m in universe}

    class _FullSource:
        def get_universe(self):
            return universe

        def get_prices(self, symbol):
            return full_prices[symbol].copy()

    full_store = PointInTimeStore(_FullSource())
    calendar = full_store.trading_calendar()
    cutoff = calendar[len(calendar) // 2]

    class _TruncatedSource:
        def get_universe(self):
            return universe

        def get_prices(self, symbol):
            df = full_prices[symbol]
            return df.loc[df.index <= cutoff].copy()

    truncated_store = PointInTimeStore(_TruncatedSource())
    strategy = CrossSectionalMomentumStrategy(EQMomConfig(top_n=8))

    full_weights = strategy.compute_weights(full_store, cutoff)
    truncated_weights = strategy.compute_weights(truncated_store, cutoff)

    assert full_weights == truncated_weights
    assert len(full_weights) > 0
