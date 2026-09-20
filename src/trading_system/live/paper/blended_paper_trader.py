"""Paper-trading wrapper for BlendedPortfolioEngine (Prompt.md S33,
Docs/Final_Report.md India-addendum status block: "no wrapper yet" gap).

Same principle as the single-strategy PaperTrader (live/paper/paper_trader.py):
"Paper trading must use the same strategy logic as the backtest. Do not
create a separate simplified strategy for paper trading." This class calls
the exact same shared helpers (backtest/blended_engine.py:
select_decision_dates, resolve_contracts, median_traded_value,
apply_participation_cap, blend_sleeves, scale_to_vol_target,
india_trade_cost) that BlendedPortfolioEngine.run() calls. There is no
parallel decision-making code path -- only the driving loop differs (day-by-
day with logging and guardrail checks vs. the engine's vectorized run) --
and tests/integration/test_blended_paper_trader.py verifies parity between
this trader's per-step state and the engine's end-state at each rebalance.

HONEST LIMITATION (Docs/Implementation_Spec.md S3, same as single-strategy
PaperTrader): this system has no live market data feed. "Paper trading"
here means replaying historical sessions one at a time through the live-
style stepping loop, using that session's historical close as a stand-in
for both the simulated execution price and the actual market price
Prompt.md S33 asks to be recorded and compared. Since both are the same
historical value, the expected-vs-simulated-execution difference is always
0.0 and flagged as not meaningful. This will only become a real measurement
once an actual live/delayed quote feed is connected.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_system.backtest.blended_engine import (
    SleeveSpec,
    median_traded_value,
    resolve_contracts,
    select_decision_dates,
)
from trading_system.config.india_schema import IndiaSystemConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.execution.india_costs import india_trade_cost
from trading_system.execution.simulator import next_execution_date
from trading_system.live.guardrails import GuardrailBreach, RiskGuardrails
from trading_system.portfolio.blend import blend_sleeves, scale_to_vol_target
from trading_system.portfolio.covariance import rolling_annualized_covariance
from trading_system.portfolio.participation import apply_participation_cap

# Modes this trader is allowed to run under. "live" is deliberately absent:
# there is no live-execution path in this system, and the SystemConfig-based
# safeguard prevents mode="live" being constructed at all -- this local list
# is a second, redundant layer of defense in depth, in case a future
# IndiaSystemConfig gains a mode field that bypasses SystemConfig's
# post_init check.
_ALLOWED_MODES = frozenset({"research", "backtest", "paper"})


@dataclass(frozen=True)
class BlendedPaperTradeRecord:
    signal_timestamp: pd.Timestamp
    decision_date: pd.Timestamp
    intended_trade: dict[str, float]
    simulated_execution_price: dict[str, float]
    actual_market_price: dict[str, float]
    slippage_estimate: float
    position: dict[str, float]
    sleeve_positions: dict[str, dict[str, float]]
    portfolio_value: float
    expected_vs_simulated_execution_diff: float
    rebalanced_sleeves: tuple[str, ...]
    note: str = (
        "actual_market_price == simulated_execution_price: this replay has "
        "no live feed, so both are the same historical close. See module "
        "docstring -- this is a mechanism demo, not an execution-quality result."
    )


class BlendedPaperTrader:
    def __init__(
        self,
        config: IndiaSystemConfig,
        store: PointInTimeStore,
        sleeve_specs: list[SleeveSpec],
        guardrails: RiskGuardrails | None = None,
        mode: str = "paper",
    ):
        if mode not in _ALLOWED_MODES:
            raise ValueError(
                f"BlendedPaperTrader cannot run in mode={mode!r} -- live "
                "trading is not implemented and must never be reached via "
                "this class. Allowed modes: {sorted(_ALLOWED_MODES)!r}."
            )
        self._config = config
        self._store = store
        self._specs = sleeve_specs
        self._spec_by_id = {s.sleeve.sleeve_id: s for s in sleeve_specs}
        self._risk_shares = {s.sleeve.sleeve_id: s.risk_share for s in sleeve_specs}
        self._guardrails = guardrails or RiskGuardrails()
        self._asset_class_by_symbol = {m.symbol: m.asset_class for m in store.universe}

        self._nav = config.initial_capital
        self._nav_start_of_day = self._nav
        # Peak NAV so far -- needed for the drawdown guardrail (see the
        # single-strategy PaperTrader's __init__ comment for context: the
        # drawdown limit was documented in RiskGuardrails but not
        # previously enforced by any caller).
        self._peak_nav = self._nav
        self._current_weights: dict[str, float] = {}
        self._current_sleeve_weights: dict[str, dict[str, float]] = {
            sid: {} for sid in self._spec_by_id
        }
        self._order_counter = 0
        self._schedule: dict[str, list[pd.Timestamp]] | None = None
        # Cache the store's forward-filled close matrix and its pct_change so
        # covariance/mark-to-market computations use the SAME aligned data the
        # engine's run() uses -- computing per-symbol from history_as_of()
        # gives subtly different results (native-vs-aligned index, different
        # NaN handling) which caused a real ~6bp NAV drift the parity test
        # caught (test_paper_trader_matches_backtest_engine_at_a_shared_date).
        self._close_matrix = store.close_matrix()
        self._instrument_returns = self._close_matrix.pct_change()
        self.records: list[BlendedPaperTradeRecord] = []

    @property
    def nav(self) -> float:
        return self._nav

    @property
    def current_weights(self) -> dict[str, float]:
        return dict(self._current_weights)

    def _lazy_build_schedule(self) -> dict[str, list[pd.Timestamp]]:
        if self._schedule is not None:
            return self._schedule
        calendar = self._store.trading_calendar()
        schedule: dict[str, list[pd.Timestamp]] = {}
        for spec in self._specs:
            decision_dates = select_decision_dates(calendar, spec.rebalance_frequency)
            execution_dates = []
            for d in decision_dates:
                exec_date = next_execution_date(calendar, d, spec.execution_delay_sessions)
                if exec_date is not None:
                    execution_dates.append(exec_date)
            schedule[spec.sleeve.sleeve_id] = execution_dates
        self._schedule = schedule
        return schedule

    def _rebalancing_sleeves(self, day: pd.Timestamp) -> list[str]:
        schedule = self._lazy_build_schedule()
        return [sid for sid, dates in schedule.items() if day in set(dates)]

    def _covariance(self, active_symbols: list[str], as_of: pd.Timestamp) -> pd.DataFrame | None:
        """Covariance matrix over ``active_symbols`` using returns STRICTLY
        BEFORE ``as_of``, computed against the same forward-filled close
        matrix the engine uses -- byte-identical to the engine's own cov
        computation to preserve backtest/paper parity.
        """
        if not active_symbols:
            return None
        calendar = self._store.trading_calendar()
        i = calendar.get_loc(as_of)
        if i == 0:
            return None
        active = [s for s in active_symbols if s in self._instrument_returns.columns]
        if not active:
            return None
        returns_so_far = self._instrument_returns[active].iloc[:i]
        return rolling_annualized_covariance(returns_so_far, self._config.covariance_window_days)

    def _apply_pnl_since_last_step(self, day: pd.Timestamp) -> None:
        """Marks the portfolio to market at ``day``'s close using the
        previous day's positions. Uses the SAME forward-filled instrument-
        returns matrix the engine's run() uses (self._instrument_returns),
        so per-day P&L is byte-identical between backtest and paper paths.
        Reads only historical closes strictly at or before ``day``, so no
        look-ahead.
        """
        if not self._current_weights:
            return
        calendar = self._store.trading_calendar()
        pos = calendar.get_loc(day)
        if pos == 0:
            return
        day_return = 0.0
        for sym, w in self._current_weights.items():
            if sym not in self._instrument_returns.columns:
                continue
            r = self._instrument_returns[sym].iloc[pos]
            if pd.notna(r):
                day_return += w * r
        self._nav *= 1 + day_return

    def step(self, day: pd.Timestamp) -> BlendedPaperTradeRecord | None:
        """Advances one trading day. Returns a record if any sleeve rebalanced,
        or None if this day is a pure hold day.
        """
        self._apply_pnl_since_last_step(day)

        rebalancing = self._rebalancing_sleeves(day)
        if not rebalancing:
            return None

        calendar = self._store.trading_calendar()
        latest_signal_as_of = None

        for sleeve_id in rebalancing:
            spec = self._spec_by_id[sleeve_id]
            decision_date = self._decision_date_for_execution(sleeve_id, day)
            if decision_date is None:
                continue
            pos = calendar.get_loc(decision_date)
            if pos == 0:
                continue
            signal_as_of = calendar[pos - 1]
            if latest_signal_as_of is None or signal_as_of > latest_signal_as_of:
                latest_signal_as_of = signal_as_of

            self._guardrails.check_data_staleness(signal_as_of, day, calendar)

            raw_weights = spec.sleeve.compute_weights(self._store, signal_as_of)
            if spec.resolve_contracts:
                raw_weights = resolve_contracts(raw_weights, day, self._store.universe)

            if spec.participation_cap_fraction is not None:
                sleeve_nav = self._nav * spec.risk_share
                mtv = {
                    sym: median_traded_value(self._store, sym, signal_as_of)
                    for sym in set(raw_weights) | set(self._current_sleeve_weights[sleeve_id])
                }
                raw_weights = apply_participation_cap(
                    raw_weights,
                    self._current_sleeve_weights[sleeve_id],
                    sleeve_nav,
                    mtv,
                    spec.participation_cap_fraction,
                )

            self._current_sleeve_weights[sleeve_id] = raw_weights

        blended = blend_sleeves(self._current_sleeve_weights, self._risk_shares)
        cov = self._covariance(list(blended.keys()), day) if blended else None
        new_weights = scale_to_vol_target(blended, cov, self._config.portfolio_vol_target)

        self._guardrails.check_position_count(new_weights)

        self._order_counter += 1
        order_id = f"{day.date()}-{self._order_counter}"
        self._guardrails.check_duplicate_order(order_id)

        intended_trade: dict[str, float] = {}
        execution_price: dict[str, float] = {}
        total_cost = 0.0
        for sym in set(self._current_weights) | set(new_weights):
            old_w = self._current_weights.get(sym, 0.0)
            new_w = new_weights.get(sym, 0.0)
            delta_w = new_w - old_w
            if delta_w == 0:
                continue
            intended_trade[sym] = delta_w
            price = self._store.close_as_of(sym, day)
            if price is not None:
                execution_price[sym] = float(price)
            if sym not in self._asset_class_by_symbol:
                # Defense in depth: mirrors the same guard in
                # backtest/blended_engine.py -- refuses to silently
                # misclassify an unknown symbol as nse_equity for cost
                # calculation. See that engine's matching KeyError block.
                raise KeyError(
                    f"Symbol {sym!r} produced a trade but is not in the "
                    "store's universe -- refuse to fabricate an asset_class "
                    "for cost calculation."
                )
            asset_class = self._asset_class_by_symbol[sym]
            notional = delta_w * self._nav
            cost = india_trade_cost(notional, asset_class, is_buy=delta_w > 0, config=self._config.cost)
            total_cost += cost

        self._nav -= total_cost
        self._current_weights = {sym: w for sym, w in new_weights.items() if w != 0.0}

        self._guardrails.check_daily_loss(self._nav_start_of_day, self._nav)
        self._nav_start_of_day = self._nav
        # Peak-nav-relative drawdown enforcement -- see __init__ comment.
        if self._nav > self._peak_nav:
            self._peak_nav = self._nav
        current_drawdown = (self._nav - self._peak_nav) / self._peak_nav if self._peak_nav > 0 else 0.0
        self._guardrails.check_drawdown(current_drawdown)

        record = BlendedPaperTradeRecord(
            signal_timestamp=latest_signal_as_of if latest_signal_as_of is not None else day,
            decision_date=day,
            intended_trade=intended_trade,
            simulated_execution_price=execution_price,
            actual_market_price=dict(execution_price),
            slippage_estimate=total_cost,
            position=dict(self._current_weights),
            sleeve_positions={sid: dict(w) for sid, w in self._current_sleeve_weights.items()},
            portfolio_value=self._nav,
            expected_vs_simulated_execution_diff=0.0,
            rebalanced_sleeves=tuple(rebalancing),
        )
        self.records.append(record)
        return record

    def _decision_date_for_execution(
        self, sleeve_id: str, execution_date: pd.Timestamp
    ) -> pd.Timestamp | None:
        """Reverse the sleeve's execution-delay offset: given today is an
        execution date, return the decision date whose signal drove it.
        """
        spec = self._spec_by_id[sleeve_id]
        calendar = self._store.trading_calendar()
        pos = calendar.get_loc(execution_date)
        decision_pos = pos - spec.execution_delay_sessions
        if decision_pos < 0:
            return None
        return calendar[decision_pos]

    def run_replay(self, days: list[pd.Timestamp]) -> list[BlendedPaperTradeRecord]:
        for day in days:
            try:
                self.step(day)
            except GuardrailBreach as breach:
                self.records.append(
                    BlendedPaperTradeRecord(
                        signal_timestamp=day,
                        decision_date=day,
                        intended_trade={},
                        simulated_execution_price={},
                        actual_market_price={},
                        slippage_estimate=0.0,
                        position=dict(self._current_weights),
                        sleeve_positions={
                            sid: dict(w) for sid, w in self._current_sleeve_weights.items()
                        },
                        portfolio_value=self._nav,
                        expected_vs_simulated_execution_diff=0.0,
                        rebalanced_sleeves=(),
                        note=f"GUARDRAIL BREACH, replay halted: {breach.reason}",
                    )
                )
                break
        return self.records
