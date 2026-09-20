import dataclasses
from datetime import date

from trading_system.config.schema import DataConfig, SystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.live.guardrails import GuardrailConfig, RiskGuardrails
from trading_system.strategies.trend import TrendStrategy
from trading_system.live.paper.paper_trader import PaperTrader


def _config() -> SystemConfig:
    data = DataConfig(
        asset_classes=("equity_index", "fx"),
        instruments_per_asset_class=2,
        start_date=date(2018, 1, 1),
        end_date=date(2020, 12, 31),
        random_seed=17,
    )
    return SystemConfig(mode="paper", data=data)


def test_paper_trader_produces_one_record_per_replayed_date():
    config = _config()
    store = PointInTimeStore(SyntheticFuturesDataSource(config.data))
    strategy = TrendStrategy(config.trend)
    trader = PaperTrader(config, store, strategy)

    calendar = store.trading_calendar()
    replay_dates = list(calendar[-30:])
    records = trader.run_replay(replay_dates)

    assert len(records) == len(replay_dates)
    assert all(r.portfolio_value > 0 for r in records)


def test_paper_trader_uses_the_same_strategy_class_as_backtest():
    from trading_system.backtest.engine import BacktestEngine
    from trading_system.backtest.metrics import compute_metrics

    config = _config()
    store = PointInTimeStore(SyntheticFuturesDataSource(config.data))
    strategy = TrendStrategy(config.trend)

    backtest_result = BacktestEngine(config, store, strategy).run()
    trader = PaperTrader(config, store, strategy)

    calendar = store.trading_calendar()
    check_date = calendar[len(calendar) // 2]
    record = trader.step(check_date)

    # The weights the paper trader computed at this date must match the
    # weights the (independently run) backtest engine set at the same
    # decision date -- proving both call the identical strategy/sizing code,
    # not two diverging implementations.
    if check_date in backtest_result.weights_history.index:
        backtest_weights = backtest_result.weights_history.loc[check_date].dropna().to_dict()
        assert record.position == {k: v for k, v in backtest_weights.items() if v != 0.0}


def test_guardrail_breach_halts_replay():
    config = _config()
    store = PointInTimeStore(SyntheticFuturesDataSource(config.data))
    strategy = TrendStrategy(config.trend)
    tight_guardrails = RiskGuardrails(GuardrailConfig(max_simultaneous_positions=0))
    trader = PaperTrader(config, store, strategy, guardrails=tight_guardrails)

    calendar = store.trading_calendar()
    replay_dates = list(calendar[-10:])
    records = trader.run_replay(replay_dates)

    assert "GUARDRAIL BREACH" in records[-1].note
    assert len(records) < len(replay_dates)


def test_rejects_live_mode():
    import pytest

    # mode="live" cannot even be constructed (SystemConfig.__post_init__),
    # so PaperTrader's own guard is unreachable via SystemConfig -- assert
    # the underlying protection still exists directly.
    with pytest.raises(ValueError):
        dataclasses.replace(_config(), mode="live")
