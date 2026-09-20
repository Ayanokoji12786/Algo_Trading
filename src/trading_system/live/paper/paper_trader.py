"""Paper-trading mode (Prompt.md S33).

"Paper trading must use the same strategy logic as the backtest. Do not
create a separate simplified strategy for paper trading." -- PaperTrader
calls the exact same Strategy.generate_signals() and
portfolio.sizing.compute_target_weights() functions BacktestEngine uses.
There is no parallel decision-making code path here; only the surrounding
loop (day-by-day stepping with logging and guardrail checks) differs from
the backtest engine's vectorized run.

HONEST LIMITATION (Docs/Implementation_Spec.md S3): this system has no live
market data feed or broker connection. "Paper trading" here means replaying
historical sessions one at a time through the live-style stepping loop, using
that session's historical close as a stand-in for both the "simulated
execution price" and the "actual market price" Prompt.md S33 asks to be
recorded and compared. Since both are the same historical value, the
expected-vs-simulated-execution difference is always logged as 0.0 and
flagged as not meaningful -- it will only become a real measurement once an
actual live/delayed quote feed is connected. Do not report this replay's
"zero slippage surprise" as a finding about real execution quality.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from trading_system.config.schema import SystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.execution.costs import trade_cost
from trading_system.live.guardrails import GuardrailBreach, RiskGuardrails
from trading_system.portfolio.sizing import compute_target_weights
from trading_system.strategies.base import Strategy


@dataclass(frozen=True)
class PaperTradeRecord:
    signal_timestamp: pd.Timestamp
    decision_date: pd.Timestamp
    intended_trade: dict[str, float]  # symbol -> weight delta
    simulated_execution_price: dict[str, float]
    actual_market_price: dict[str, float]
    slippage_estimate: float
    position: dict[str, float]
    portfolio_value: float
    expected_vs_simulated_execution_diff: float
    note: str = (
        "actual_market_price == simulated_execution_price: this replay has "
        "no live feed, so both are the same historical close. See module "
        "docstring -- this is a mechanism demo, not an execution-quality result."
    )


class PaperTrader:
    def __init__(
        self,
        config: SystemConfig,
        store: PointInTimeStore,
        strategy: Strategy,
        guardrails: RiskGuardrails | None = None,
    ):
        if config.mode not in ("research", "backtest", "paper"):
            raise ValueError(
                f"PaperTrader cannot run in mode={config.mode!r} -- live trading "
                "is not implemented and must never be reached via this class."
            )
        self._config = config
        self._store = store
        self._strategy = strategy
        self._guardrails = guardrails or RiskGuardrails()
        self._current_weights: dict[str, float] = {}
        self._nav = config.backtest.initial_capital
        self._nav_start_of_day = self._nav
        self._asset_class_by_symbol = {m.symbol: m.asset_class for m in store.universe}
        self._order_counter = 0
        self.records: list[PaperTradeRecord] = []

    def step(self, decision_date: pd.Timestamp) -> PaperTradeRecord:
        calendar = self._store.trading_calendar()
        pos = calendar.get_loc(decision_date)
        if pos == 0:
            raise ValueError("decision_date has no prior session to form a signal from")
        signal_as_of = calendar[pos - 1]

        self._guardrails.check_data_staleness(signal_as_of, decision_date, calendar)

        signals = self._strategy.generate_signals(self._store, signal_as_of)
        target_weights = compute_target_weights(
            signals, self._config.risk, self._config.trend.vol_floor_annualized
        )
        self._guardrails.check_position_count(target_weights)

        all_symbols = set(target_weights) | set(self._current_weights)
        intended_trade = {
            sym: target_weights.get(sym, 0.0) - self._current_weights.get(sym, 0.0)
            for sym in all_symbols
        }
        intended_trade = {sym: delta for sym, delta in intended_trade.items() if delta != 0.0}

        self._order_counter += 1
        order_id = f"{decision_date.date()}-{self._order_counter}"
        self._guardrails.check_duplicate_order(order_id)

        execution_price = {
            sym: self._store.close_as_of(sym, decision_date) for sym in intended_trade
        }

        total_cost = 0.0
        for sym, delta in intended_trade.items():
            notional = delta * self._nav
            total_cost += trade_cost(notional, self._asset_class_by_symbol[sym], self._config.cost)
        self._nav -= total_cost

        self._current_weights = {sym: w for sym, w in target_weights.items() if w != 0.0}

        self._guardrails.check_daily_loss(self._nav_start_of_day, self._nav)
        self._nav_start_of_day = self._nav

        record = PaperTradeRecord(
            signal_timestamp=signal_as_of,
            decision_date=decision_date,
            intended_trade=intended_trade,
            simulated_execution_price=execution_price,
            actual_market_price=dict(execution_price),
            slippage_estimate=total_cost,
            position=dict(self._current_weights),
            portfolio_value=self._nav,
            expected_vs_simulated_execution_diff=0.0,
        )
        self.records.append(record)
        return record

    def run_replay(self, decision_dates: list[pd.Timestamp]) -> list[PaperTradeRecord]:
        for d in decision_dates:
            try:
                self.step(d)
            except GuardrailBreach as breach:
                self.records.append(
                    PaperTradeRecord(
                        signal_timestamp=d,
                        decision_date=d,
                        intended_trade={},
                        simulated_execution_price={},
                        actual_market_price={},
                        slippage_estimate=0.0,
                        position=dict(self._current_weights),
                        portfolio_value=self._nav,
                        expected_vs_simulated_execution_diff=0.0,
                        note=f"GUARDRAIL BREACH, replay halted: {breach.reason}",
                    )
                )
                break
        return self.records
