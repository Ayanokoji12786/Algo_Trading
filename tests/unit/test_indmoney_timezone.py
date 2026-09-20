"""Regression test for the INDmoney IST-timezone bug found in the audit:
_to_epoch_ms previously used a naive datetime and called .timestamp(),
which interprets the datetime as LOCAL TIME on the host machine. That
meant a US-Eastern user and an IST user would send DIFFERENT epoch ms
values for "the same date", breaking reproducibility. Fixed by attaching
IST tzinfo explicitly.

This test locks in the tz-fixed behavior: the epoch ms for
_to_epoch_ms(2024-01-01) must correspond exactly to 2024-01-01 00:00 IST,
regardless of the host's timezone -- because _to_epoch_ms now builds a
tz-aware datetime, its .timestamp() output does not depend on TZ.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from trading_system.brokers.indmoney import _to_epoch_ms


def test_to_epoch_ms_is_ist_start_of_day():
    epoch_ms = _to_epoch_ms(date(2024, 1, 1), end_of_day=False)
    ist_midnight = datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert epoch_ms == int(ist_midnight.timestamp() * 1000)


def test_to_epoch_ms_is_ist_end_of_day():
    epoch_ms = _to_epoch_ms(date(2024, 1, 1), end_of_day=True)
    ist_eod = datetime(2024, 1, 1, 23, 59, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert epoch_ms == int(ist_eod.timestamp() * 1000)


def test_to_epoch_ms_independent_of_host_tz(monkeypatch):
    """Verify the output does not vary with the TZ env var. Attaching IST
    explicitly should make it invariant.
    """
    monkeypatch.setenv("TZ", "America/New_York")
    a = _to_epoch_ms(date(2024, 6, 15))
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    b = _to_epoch_ms(date(2024, 6, 15))
    monkeypatch.setenv("TZ", "UTC")
    c = _to_epoch_ms(date(2024, 6, 15))
    assert a == b == c
