"""Per-sleeve blended portfolio backtest engine
(Docs/India_Implementation_Spec.md S3: "new engine, not a modification of
the existing one").

Each sleeve (EQ_MOM_01 monthly, MCX_TREND_01 daily -- genuinely different
native frequencies per their own source spec) rebalances on its own
schedule. Whenever any sleeve's execution date arrives, the portfolio is
re-blended from each sleeve's latest known weights at a configured risk
share (Docs/India_Implementation_Spec.md RISK_01: 50:50 NSE/MCX baseline),
then scaled to a portfolio vol target using a rolling covariance estimate
(portfolio/covariance.py) -- a real methodological upgrade over the
zero-correlation simplification the original global-futures BacktestEngine
uses, kept as a SEPARATE code path precisely so that engine's tested,
already-reported behavior is untouched.

Sleeves whose weights are keyed by an underlying commodity rather than a
directly tradable symbol (MCX_TREND_01: "GOLD", not "GOLD_202601") are
resolved to their currently active dated contract (data/roll.py) at each
of that sleeve's own execution dates -- so a roll shows up simply as the
weight moving from the old contract's symbol to the new one's, charged
exactly like any other trade (this is where "roll cost" comes from; no
separate roll-cost code path exists or is needed).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from trading_system.data.pit_store import PointInTimeStore
from trading_system.data.roll import active_contract_for
from trading_system.execution.india_costs import IndiaCostConfig, india_trade_cost
from trading_system.execution.simulator import next_execution_date
from trading_system.portfolio.blend import blend_sleeves, scale_to_vol_target
from trading_system.portfolio.covariance import rolling_annualized_covariance
from trading_system.portfolio.participation import apply_participation_cap


class Sleeve(Protocol):
    sleeve_id: str

    def compute_weights(self, store: PointInTimeStore, as_of: pd.Timestamp) -> dict[str, float]:
        ...


@dataclass
class SleeveSpec:
    sleeve: Sleeve
    rebalance_frequency: str  # "daily" | "weekly" | "monthly"
    risk_share: float
    execution_delay_sessions: int = 0
    resolve_contracts: bool = False  # True: weights keyed by underlying, need roll resolution
    participation_cap_fraction: float | None = None  # None disables the cap


@dataclass
class BlendedBacktestResult:
    equity_curve: pd.Series
    weights_history: pd.DataFrame
    turnover: pd.Series
    trade_log: pd.DataFrame
    sleeve_weights_history: dict[str, pd.DataFrame]


class BlendedPortfolioEngine:
    def __init__(
        self,
        store: PointInTimeStore,
        sleeve_specs: list[SleeveSpec],
        cost_config: IndiaCostConfig,
        initial_capital: float = 1_000_000.0,
        portfolio_vol_target: float = 0.10,
        covariance_window_days: int = 120,
    ):
        self._store = store
        self._specs = sleeve_specs
        self._cost_config = cost_config
        self._initial_capital = initial_capital
        self._vol_target = portfolio_vol_target
        self._cov_window = covariance_window_days
        self._asset_class_by_symbol = {m.symbol: m.asset_class for m in store.universe}
        self._risk_shares = {s.sleeve.sleeve_id: s.risk_share for s in sleeve_specs}

    def _select_decision_dates(
        self, calendar: pd.DatetimeIndex, frequency: str
    ) -> list[pd.Timestamp]:
        if frequency == "daily":
            return list(calendar[1:])
        if frequency == "weekly":
            iso = pd.Series(calendar, index=calendar).index.isocalendar()
            grouped = pd.DataFrame({"date": calendar, "year": iso["year"], "week": iso["week"]})
            weekly = grouped.groupby(["year", "week"])["date"].max().sort_values()
            return [d for d in weekly.tolist() if d != calendar[0]]
        if frequency == "monthly":
            grouped = pd.DataFrame({"date": calendar, "period": calendar.to_period("M")})
            monthly = grouped.groupby("period")["date"].max().sort_values()
            return [d for d in monthly.tolist() if d != calendar[0]]
        raise ValueError(f"Unknown rebalance_frequency: {frequency!r}")

    def _resolve_contracts(
        self, weights_by_underlying: dict[str, float], as_of: pd.Timestamp
    ) -> dict[str, float]:
        resolved: dict[str, float] = {}
        for underlying, w in weights_by_underlying.items():
            symbol = active_contract_for(underlying, as_of.date(), self._store.universe)
            if symbol is None:
                continue
            resolved[symbol] = resolved.get(symbol, 0.0) + w
        return resolved

    def _median_traded_value(self, symbol: str, as_of: pd.Timestamp, window: int = 60) -> float:
        history = self._store.history_as_of(symbol, as_of)
        if len(history) < 2:
            return 0.0
        recent = history.iloc[-window:]
        traded_value = recent["close"] * recent["volume"]
        return float(traded_value.median())

    def run(self) -> BlendedBacktestResult:
        calendar = self._store.trading_calendar()
        close_matrix = self._store.close_matrix()
        instrument_returns = close_matrix.pct_change()

        # Precompute each sleeve's raw (unresolved, un-participation-capped)
        # weights at every one of its own execution dates.
        pending: dict[str, dict[pd.Timestamp, dict[str, float]]] = {}
        spec_by_id: dict[str, SleeveSpec] = {}
        for spec in self._specs:
            sleeve_id = spec.sleeve.sleeve_id
            spec_by_id[sleeve_id] = spec
            pending[sleeve_id] = {}
            decision_dates = self._select_decision_dates(calendar, spec.rebalance_frequency)
            for decision_date in decision_dates:
                pos = calendar.get_loc(decision_date)
                if pos == 0:
                    continue
                signal_as_of = calendar[pos - 1]
                raw_weights = spec.sleeve.compute_weights(self._store, signal_as_of)
                if spec.resolve_contracts:
                    raw_weights = self._resolve_contracts(raw_weights, decision_date)
                execution_date = next_execution_date(
                    calendar, decision_date, spec.execution_delay_sessions
                )
                if execution_date is None:
                    continue
                pending[sleeve_id][execution_date] = {
                    "as_of": signal_as_of,
                    "weights": raw_weights,
                }

        nav = self._initial_capital
        current_weights: dict[str, float] = {}
        current_sleeve_weights: dict[str, dict[str, float]] = {sid: {} for sid in pending}
        sleeve_weight_records: dict[str, dict[pd.Timestamp, dict[str, float]]] = {
            sid: {} for sid in pending
        }
        equity_records: list[tuple[pd.Timestamp, float]] = []
        weights_records: dict[pd.Timestamp, dict[str, float]] = {}
        turnover_records: dict[pd.Timestamp, float] = {}
        trade_rows: list[dict] = []

        for i, day in enumerate(calendar):
            if i > 0 and current_weights:
                day_return = sum(
                    w * instrument_returns[sym].iloc[i]
                    for sym, w in current_weights.items()
                    if sym in instrument_returns.columns and pd.notna(instrument_returns[sym].iloc[i])
                )
                nav *= 1 + day_return

            rebalanced_today = False
            for sleeve_id, schedule in pending.items():
                if day not in schedule:
                    continue
                rebalanced_today = True
                spec = spec_by_id[sleeve_id]
                raw_weights = schedule[day]["weights"]

                if spec.participation_cap_fraction is not None:
                    signal_as_of = schedule[day]["as_of"]
                    sleeve_nav = nav * spec.risk_share
                    median_tv = {
                        sym: self._median_traded_value(sym, signal_as_of)
                        for sym in set(raw_weights) | set(current_sleeve_weights[sleeve_id])
                    }
                    raw_weights = apply_participation_cap(
                        raw_weights,
                        current_sleeve_weights[sleeve_id],
                        sleeve_nav,
                        median_tv,
                        spec.participation_cap_fraction,
                    )

                current_sleeve_weights[sleeve_id] = raw_weights
                sleeve_weight_records[sleeve_id][day] = dict(raw_weights)

            if rebalanced_today:
                blended = blend_sleeves(current_sleeve_weights, self._risk_shares)
                if i > 0 and blended:
                    # Only the symbols actually held need a covariance
                    # estimate -- slicing columns first avoids recomputing a
                    # full-universe (hundreds of instruments) covariance
                    # matrix every day when a handful are actually active.
                    active_symbols = [s for s in blended if s in instrument_returns.columns]
                    returns_so_far = instrument_returns[active_symbols].iloc[:i]
                    cov = rolling_annualized_covariance(returns_so_far, self._cov_window)
                else:
                    cov = None
                new_weights = scale_to_vol_target(blended, cov, self._vol_target)

                all_symbols = set(current_weights) | set(new_weights)
                gross_change = 0.0
                for sym in all_symbols:
                    old_w = current_weights.get(sym, 0.0)
                    new_w = new_weights.get(sym, 0.0)
                    delta_w = new_w - old_w
                    if delta_w == 0:
                        continue
                    notional_traded = delta_w * nav
                    asset_class = self._asset_class_by_symbol.get(sym, "nse_equity")
                    cost = india_trade_cost(
                        notional_traded, asset_class, is_buy=delta_w > 0, config=self._cost_config
                    )
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
                current_weights = {sym: w for sym, w in new_weights.items() if w != 0.0}
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
        sleeve_weights_history = {
            sid: pd.DataFrame(records).T.sort_index()
            for sid, records in sleeve_weight_records.items()
        }

        return BlendedBacktestResult(
            equity_curve=equity_curve,
            weights_history=weights_history,
            turnover=turnover,
            trade_log=trade_log,
            sleeve_weights_history=sleeve_weights_history,
        )
