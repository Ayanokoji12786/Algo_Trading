import numpy as np
import pandas as pd

from trading_system.data.interfaces import ContractMeta
from trading_system.data.pit_store import PointInTimeStore
from trading_system.strategies.mcx_trend_sleeve import MCXTrendConfig, MCXTrendSleeve


class _MonotonicIndexSource:
    def __init__(self, underlying: str, direction: float, n_days: int = 400, seed: int = 0):
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range("2015-01-01", periods=n_days)
        drift = direction * 0.0006
        noise = rng.normal(0.0, 0.004, n_days)
        close = 100.0 * np.exp(np.cumsum(drift + noise))
        self._df = pd.DataFrame(
            {"open": close, "high": close * 1.001, "low": close * 0.999, "close": close, "volume": 1e4},
            index=dates,
        )
        self._meta = ContractMeta(
            symbol=f"{underlying}_INDEX",
            asset_class="mcx_commodity_index",
            underlying=underlying,
        )

    def get_universe(self):
        return [self._meta]

    def get_prices(self, symbol):
        return self._df.copy()


def test_sleeve_goes_long_on_uptrend_and_short_on_downtrend():
    up_store = PointInTimeStore(_MonotonicIndexSource("GOLD", direction=1.0))
    down_store = PointInTimeStore(_MonotonicIndexSource("GOLD", direction=-1.0, seed=1))
    sleeve = MCXTrendSleeve(MCXTrendConfig())

    up_weights = sleeve.compute_weights(up_store, up_store.trading_calendar()[-1])
    down_weights = sleeve.compute_weights(down_store, down_store.trading_calendar()[-1])

    assert up_weights["GOLD"] > 0
    assert down_weights["GOLD"] < 0


def test_weights_keyed_by_underlying_not_index_symbol():
    store = PointInTimeStore(_MonotonicIndexSource("GOLD", direction=1.0))
    sleeve = MCXTrendSleeve(MCXTrendConfig())
    weights = sleeve.compute_weights(store, store.trading_calendar()[-1])
    assert "GOLD" in weights
    assert "GOLD_INDEX" not in weights


def test_gross_normalization_sums_to_one_in_absolute_value():
    class _MultiCommodity:
        def __init__(self):
            self._sources = [
                _MonotonicIndexSource("GOLD", direction=1.0, seed=0),
                _MonotonicIndexSource("SILVER", direction=-1.0, seed=1),
            ]

        def get_universe(self):
            metas = []
            for s in self._sources:
                metas.extend(s.get_universe())
            return metas

        def get_prices(self, symbol):
            for s in self._sources:
                if symbol in [m.symbol for m in s.get_universe()]:
                    return s.get_prices(symbol)
            raise KeyError(symbol)

    store = PointInTimeStore(_MultiCommodity())
    sleeve = MCXTrendSleeve(MCXTrendConfig())
    weights = sleeve.compute_weights(store, store.trading_calendar()[-1])
    assert abs(sum(abs(w) for w in weights.values()) - 1.0) < 1e-9


def test_returns_empty_before_minimum_history():
    store = PointInTimeStore(_MonotonicIndexSource("GOLD", direction=1.0, n_days=400))
    sleeve = MCXTrendSleeve(MCXTrendConfig())
    early_date = store.trading_calendar()[50]
    assert sleeve.compute_weights(store, early_date) == {}
