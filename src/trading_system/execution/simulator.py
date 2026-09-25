"""Execution timing (Research.md "Entry logic", Prompt.md S15):
orders must be simulated *after* the information used to create them becomes
observable. A signal computed from data as-of session t is executed no
earlier than session t + delay_sessions, never at the same close that
produced it unless delay_sessions=0 is explicitly configured for comparison.
"""
from __future__ import annotations

import pandas as pd


def next_execution_date(
    calendar: pd.DatetimeIndex, decision_date: pd.Timestamp, delay_sessions: int
) -> pd.Timestamp | None:
    # A negative delay would place execution BEFORE the decision date, which
    # is look-ahead bias. Worse, without this guard exec_pos could go
    # negative and Python's negative indexing would silently return a
    # FUTURE calendar date (wraparound), executing on data that didn't exist
    # yet -- the exact failure this whole system exists to prevent. Reject it
    # here so no caller (either engine, either paper trader, or a SleeveSpec
    # with a bad delay) can ever produce a look-ahead execution, regardless
    # of whether upstream config validation caught it.
    if delay_sessions < 0:
        raise ValueError(
            f"next_execution_date: delay_sessions must be >= 0, got "
            f"{delay_sessions} -- a negative delay would execute before the "
            "decision date (look-ahead bias)."
        )
    pos = calendar.get_indexer([decision_date])[0]
    if pos == -1:
        return None
    exec_pos = pos + delay_sessions
    if exec_pos >= len(calendar):
        return None
    return calendar[exec_pos]
