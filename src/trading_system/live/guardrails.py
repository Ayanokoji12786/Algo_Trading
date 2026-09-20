"""Hard risk safeguards (Prompt.md S35).

These are pure, independently testable checks. They do not depend on any
live broker/data connection existing yet -- the point is that when a live
feed is eventually wired in (Prompt.md S34: separately gated, disabled by
default), the trading loop calls these same checks rather than inventing ad
hoc safety logic at that point. Each check raises GuardrailBreach with a
specific reason on failure; the caller (paper or, eventually, live loop) is
expected to treat any breach as "stop and require human attention," per
Prompt.md S35's "fail safely rather than blindly trade."

Not yet implemented here (require an actual live connection to be
meaningful): API failure handling, order rejection handling, and margin-call
handling from a real broker. These are explicitly out of scope until a
broker integration exists (Docs/Implementation_Spec.md S3) -- listed here so
the gap is visible rather than silently absent.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


class GuardrailBreach(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class GuardrailConfig:
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.25
    max_data_staleness_sessions: int = 2
    max_simultaneous_positions: int = 50


@dataclass
class RiskGuardrails:
    config: GuardrailConfig = field(default_factory=GuardrailConfig)
    _seen_order_ids: set[str] = field(default_factory=set)
    _tripped: bool = False
    _trip_reason: str | None = None

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    def trip(self, reason: str) -> None:
        self._tripped = True
        self._trip_reason = reason

    def _check_not_tripped(self) -> None:
        if self._tripped:
            raise GuardrailBreach(f"Emergency shutdown already active: {self._trip_reason}")

    def check_data_staleness(
        self, last_data_date: pd.Timestamp, as_of: pd.Timestamp, calendar: pd.DatetimeIndex
    ) -> None:
        self._check_not_tripped()
        sessions_stale = calendar.searchsorted(as_of) - calendar.searchsorted(last_data_date)
        if sessions_stale > self.config.max_data_staleness_sessions:
            self.trip(
                f"Data is {sessions_stale} sessions stale as of {as_of} "
                f"(limit {self.config.max_data_staleness_sessions})"
            )
            raise GuardrailBreach(self._trip_reason)

    def check_daily_loss(self, nav_start_of_day: float, nav_now: float) -> None:
        self._check_not_tripped()
        if nav_start_of_day <= 0:
            return
        loss_pct = (nav_start_of_day - nav_now) / nav_start_of_day
        if loss_pct > self.config.max_daily_loss_pct:
            self.trip(f"Daily loss {loss_pct:.2%} exceeds limit {self.config.max_daily_loss_pct:.2%}")
            raise GuardrailBreach(self._trip_reason)

    def check_drawdown(self, current_drawdown: float) -> None:
        self._check_not_tripped()
        if abs(current_drawdown) > self.config.max_drawdown_pct:
            self.trip(
                f"Drawdown {current_drawdown:.2%} exceeds limit "
                f"{self.config.max_drawdown_pct:.2%}"
            )
            raise GuardrailBreach(self._trip_reason)

    def check_position_count(self, target_weights: dict[str, float]) -> None:
        self._check_not_tripped()
        n_positions = sum(1 for w in target_weights.values() if w != 0.0)
        if n_positions > self.config.max_simultaneous_positions:
            raise GuardrailBreach(
                f"{n_positions} simultaneous positions exceeds limit "
                f"{self.config.max_simultaneous_positions}"
            )

    def check_duplicate_order(self, order_id: str) -> None:
        self._check_not_tripped()
        if order_id in self._seen_order_ids:
            raise GuardrailBreach(f"Duplicate order id rejected: {order_id}")
        self._seen_order_ids.add(order_id)
