"""Event-driven backtest engine (Prompt.md S15).

Mechanics, deliberately explicit rather than assumed:

1. Decision dates are chosen per the configured rebalance frequency.
2. Each decision date's signal is generated from data as-of the *previous*
   trading day (Research.md: "no later than t-1"). The decision date itself
   is therefore already "the next tradable session" relative to that
   information -- the baseline execution (execution_delay_sessions=0)
   trades at the decision date's close; positive delay values push
   execution further out, per Research.md's required fragility checks.
3. Between one execution date and the next, the portfolio holds whatever
   weights were set at the most recent execution, mark-to-market daily.
4. Transaction costs are charged at the execution date based on the change
   in weights, using NAV at that point.

This is a returns-based (weight * instrument-return) simulator, not a
contract/margin-accurate one -- real contract multipliers, actual futures
rolls, and margin financing are deferred to the real-data phase
(Docs/Implementation_Spec.md S3). Every metric produced here is a
pipeline-correctness check, not a performance claim.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_system.config.schema import SystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.execution.costs import trade_cost
from trading_system.execution.simulator import next_execution_date
from trading_system.portfolio.aggregation import compute_multi_strategy_target_weights
from trading_system.portfolio.sizing import compute_target_weights
from trading_system.strategies.base import Strategy


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    weights_history: pd.DataFrame  # index=execution_date, columns=symbol
    turnover: pd.Series  # index=execution_date, sum of |weight changes|
    trade_log: pd.DataFrame


class BacktestEngine:
    def __init__(
        self,
        config: SystemConfig,
        store: PointInTimeStore,
        strategy: Strategy | list[Strategy],
    ):
        """``strategy`` is normally a single Strategy (the production
        baseline runs one active sleeve -- Research.md "Portfolio logic").
        A list is accepted only to support the trend+carry complementarity
        comparison (Research.md S20), in which case each strategy receives
        an equal ex-ante risk budget (portfolio/aggregation.py) rather than
        the single-strategy asset-class-only equalization.
        """
        self._config = config
        self._store = store
        self._strategies = strategy if isinstance(strategy, list) else [strategy]
        self._asset_class_by_symbol = {
            meta.symbol: meta.asset_class for meta in store.universe
        }

    def _select_decision_dates(self, calendar: pd.DatetimeIndex) -> list[pd.Timestamp]:
        if self._config.backtest.rebalance_frequency == "daily":
            return list(calendar[1:])  # need >=1 prior day for the signal cutoff
        # weekly: last trading day observed in each ISO calendar week
        iso = pd.Series(calendar, index=calendar).index.isocalendar()
        grouped = pd.DataFrame({"date": calendar, "year": iso["year"], "week": iso["week"]})
        weekly_dates = grouped.groupby(["year", "week"])["date"].max().sort_values()
        return [d for d in weekly_dates.tolist() if d != calendar[0]]

    def run(self) -> BacktestResult:
        calendar = self._store.trading_calendar()
        close_matrix = self._store.close_matrix()
        instrument_returns = close_matrix.pct_change()

        decision_dates = self._select_decision_dates(calendar)

        pending_weights: dict[pd.Timestamp, dict[str, float]] = {}
        for decision_date in decision_dates:
            pos = calendar.get_loc(decision_date)
            if pos == 0:
                continue
            signal_as_of = calendar[pos - 1]
            if len(self._strategies) == 1:
                signals = self._strategies[0].generate_signals(self._store, signal_as_of)
                target_weights = compute_target_weights(
                    signals,
                    self._config.risk,
                    self._config.trend.vol_floor_annualized,
                )
            else:
                signals_by_strategy = {
                    strat.strategy_id: strat.generate_signals(self._store, signal_as_of)
                    for strat in self._strategies
                }
                target_weights = compute_multi_strategy_target_weights(
                    signals_by_strategy,
                    self._config.risk,
                    self._config.trend.vol_floor_annualized,
                )
            execution_date = next_execution_date(
                calendar, decision_date, self._config.backtest.execution_delay_sessions
            )
            if execution_date is None:
                continue
            pending_weights[execution_date] = target_weights

        nav = self._config.backtest.initial_capital
        current_weights: dict[str, float] = {}
        equity_records: list[tuple[pd.Timestamp, float]] = []
        weights_records: dict[pd.Timestamp, dict[str, float]] = {}
        turnover_records: dict[pd.Timestamp, float] = {}
        trade_rows: list[dict] = []

        for i, day in enumerate(calendar):
            if i > 0 and current_weights:
                day_return = sum(
                    w * instrument_returns[sym].iloc[i]
                    for sym, w in current_weights.items()
                    if pd.notna(instrument_returns[sym].iloc[i])
                )
                nav *= 1 + day_return

            if day in pending_weights:
                new_weights = pending_weights[day]
                all_symbols = set(current_weights) | set(new_weights)
                gross_change = 0.0
                for sym in all_symbols:
                    old_w = current_weights.get(sym, 0.0)
                    new_w = new_weights.get(sym, 0.0)
                    delta_w = new_w - old_w
                    if delta_w == 0:
                        continue
                    notional_traded = delta_w * nav
                    asset_class = self._asset_class_by_symbol[sym]
                    cost = trade_cost(notional_traded, asset_class, self._config.cost)
                    nav -= cost
                    gross_change += abs(delta_w)
                    trade_rows.append(
                        {
                            "date": day,
                            "symbol": sym,
                            "old_weight": old_w,
                            "new_weight": new_w,
                            "notional_traded": notional_traded,
                            "cost": cost,
                        }
                    )
                current_weights = {
                    sym: w for sym, w in new_weights.items() if w != 0.0
                }
                turnover_records[day] = gross_change
                weights_records[day] = dict(current_weights)

            equity_records.append((day, nav))

        equity_curve = pd.Series(
            [v for _, v in equity_records],
            index=[d for d, _ in equity_records],
            name="equity",
        )
        weights_history = pd.DataFrame(weights_records).T.sort_index()
        turnover = pd.Series(turnover_records, name="turnover").sort_index()
        trade_log = pd.DataFrame(trade_rows)

        return BacktestResult(
            equity_curve=equity_curve,
            weights_history=weights_history,
            turnover=turnover,
            trade_log=trade_log,
        )
