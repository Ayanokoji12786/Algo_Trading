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
    pos = calendar.get_indexer([decision_date])[0]
    if pos == -1:
        return None
    exec_pos = pos + delay_sessions
    if exec_pos >= len(calendar):
        return None
    return calendar[exec_pos]
