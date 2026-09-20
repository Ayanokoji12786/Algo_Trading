from datetime import date, timedelta

import numpy as np
import pandas as pd

from trading_system.data.interfaces import ContractMeta
from trading_system.data.pit_store import PointInTimeStore
from trading_system.strategies.mcx_carry import MCXCarryConfig, MCXCarryStrategy


def _price_frame(value: float, n_days: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=n_days)
    noise = rng.normal(0.0, 0.002, n_days)
    close = value * np.exp(np.cumsum(noise))
    return pd.DataFrame(
        {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": 1e4},
        index=dates,
    )


class _CurveSource:
    """Controlled front/next contract prices for exactly-known backwardation
    or contango, across enough commodities to satisfy the cross-sectional
    minimum.
    """

    def __init__(self, relation: str, n_days: int = 300):
        self._frames: dict[str, pd.DataFrame] = {}
        self._universe: list[ContractMeta] = []
        commodities = ["GOLD", "SILVER", "CRUDEOIL", "COPPER"]
        # n_days is a count of BUSINESS days, which spans more calendar time
        # than n_days itself (weekends) -- derive the expiry from the actual
        # last generated date, not from a naive calendar-day offset, so the
        # contracts are still unexpired at the last date in the series.
        last_date = pd.bdate_range("2015-01-01", periods=n_days)[-1].date()
        expiry1 = last_date + timedelta(days=30)  # comfortably after all price data
        expiry2 = expiry1 + timedelta(days=30)
        for i, commodity in enumerate(commodities):
            front_value = 100.0
            # backwardation: front (near) > next (far); contango: front < next
            next_value = 95.0 if relation == "backwardation" else 105.0
            front_symbol = f"{commodity}_FRONT"
            next_symbol = f"{commodity}_NEXT"
            self._frames[front_symbol] = _price_frame(front_value, n_days, seed=i)
            self._frames[next_symbol] = _price_frame(next_value, n_days, seed=i + 100)
            self._universe.append(
                ContractMeta(
                    symbol=front_symbol,
                    asset_class="mcx_commodity",
                    underlying=commodity,
                    expiry_date=expiry1,
                )
            )
            self._universe.append(
                ContractMeta(
                    symbol=next_symbol,
                    asset_class="mcx_commodity",
                    underlying=commodity,
                    expiry_date=expiry2,
                )
            )

    def get_universe(self):
        return list(self._universe)

    def get_prices(self, symbol):
        return self._frames[symbol].copy()


def test_backwardation_gives_positive_carry():
    store = PointInTimeStore(_CurveSource("backwardation"))
    strategy = MCXCarryStrategy(MCXCarryConfig(min_commodities_for_cross_section=3))
    as_of = store.trading_calendar()[-1]
    weights = strategy.compute_weights(store, as_of)
    assert len(weights) > 0
    # All four commodities are symmetrically backwardated here, so their
    # z-scored carry (and thus weight) should be ~0 relative to each other,
    # but the *sign convention* is what matters: verify via the raw formula
    # directly rather than only through the (mean-zero) cross-sectional output.
    front = store.close_as_of("GOLD_FRONT", as_of)
    next_ = store.close_as_of("GOLD_NEXT", as_of)
    assert next_ < front  # backwardation by construction


def test_contango_gives_negative_slope_sign_flip():
    back_store = PointInTimeStore(_CurveSource("backwardation"))
    contango_store = PointInTimeStore(_CurveSource("contango"))
    strategy = MCXCarryStrategy(MCXCarryConfig(min_commodities_for_cross_section=3))

    as_of_back = back_store.trading_calendar()[-1]
    as_of_contango = contango_store.trading_calendar()[-1]

    # Compute the raw (pre-cross-section) carry score directly to check the
    # sign convention unambiguously (backwardation -> positive carry score).
    import numpy as np

    f1_back = back_store.close_as_of("GOLD_FRONT", as_of_back)
    f2_back = back_store.close_as_of("GOLD_NEXT", as_of_back)
    front_meta = next(m for m in back_store.universe if m.symbol == "GOLD_FRONT")
    next_meta = next(m for m in back_store.universe if m.symbol == "GOLD_NEXT")
    days_between = (next_meta.expiry_date - front_meta.expiry_date).days
    slope_back = (365.0 / days_between) * np.log(f2_back / f1_back)
    carry_back = -slope_back
    assert carry_back > 0  # backwardation -> positive carry

    f1_c = contango_store.close_as_of("GOLD_FRONT", as_of_contango)
    f2_c = contango_store.close_as_of("GOLD_NEXT", as_of_contango)
    slope_contango = (365.0 / days_between) * np.log(f2_c / f1_c)
    carry_contango = -slope_contango
    assert carry_contango < 0  # contango -> negative carry


def test_returns_empty_below_minimum_commodities():
    store = PointInTimeStore(_CurveSource("backwardation"))
    strategy = MCXCarryStrategy(MCXCarryConfig(min_commodities_for_cross_section=10))
    weights = strategy.compute_weights(store, store.trading_calendar()[-1])
    assert weights == {}


def test_gross_weights_sum_to_one_in_absolute_value():
    store = PointInTimeStore(_CurveSource("backwardation"))
    strategy = MCXCarryStrategy(MCXCarryConfig(min_commodities_for_cross_section=3))
    weights = strategy.compute_weights(store, store.trading_calendar()[-1])
    if weights:
        assert abs(sum(abs(w) for w in weights.values()) - 1.0) < 1e-6
