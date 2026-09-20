import pandas as pd

from trading_system.config.schema import SystemConfig
from trading_system.strategies.carry import CarryStrategy, SyntheticCarrySignalSource


def test_synthetic_carry_source_is_deterministic_per_symbol_and_date():
    source = SyntheticCarrySignalSource(["A", "B"], seed=1)
    v1 = source.carry_score_as_of("A", pd.Timestamp("2020-01-01"))
    v2 = source.carry_score_as_of("A", pd.Timestamp("2020-01-01"))
    assert v1 == v2  # cached / deterministic for the same (symbol, date)


def test_synthetic_carry_source_bounded():
    source = SyntheticCarrySignalSource(["A"], seed=2)
    for i in range(50):
        v = source.carry_score_as_of("A", pd.Timestamp("2020-01-01") + pd.Timedelta(days=i))
        assert -1.0 <= v <= 1.0


def test_carry_flags_data_as_synthetic_placeholder():
    from trading_system.data.interfaces import ContractMeta
    from trading_system.data.pit_store import PointInTimeStore

    class _FakeSource:
        def get_universe(self):
            return [ContractMeta(symbol="X", asset_class="fx")]

        def get_prices(self, symbol):
            dates = pd.bdate_range("2020-01-01", periods=80)
            return pd.DataFrame(
                {
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": [1.0 + 0.001 * i for i in range(80)],
                    "volume": 100.0,
                },
                index=dates,
            )

    store = PointInTimeStore(_FakeSource())
    carry_source = SyntheticCarrySignalSource(["X"], seed=5)
    config = SystemConfig()
    strategy = CarryStrategy(carry_source, config.trend)
    signals = strategy.generate_signals(store, store.trading_calendar()[-1])
    assert len(signals) == 1
    assert signals[0].metadata["data_status"] == "SYNTHETIC_PLACEHOLDER"
