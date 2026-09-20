"""Deterministic futures roll rule (India_Implementation_Spec.md MCX_TREND_01,
MCX_CARRY_01: "force roll before the exchange-defined delivery/staggered-
delivery deadline regardless of the liquidity signal... deadline comes from
the dated contract master, never a global days_before_expiry=N constant").

SIMPLIFICATION, documented not silent: the research's preferred rule also
migrates early when the NEXT contract's open interest/liquidity already
dominates the front contract's. This system has no real OI data yet
(Docs/India_Implementation_Spec.md S5), so this implementation uses only the
fixed-days-before-expiry trigger, applied per contract from that contract's
own dated ContractMeta.expiry_date (not a universal constant in the sense
that each commodity/contract generation can carry its own expiry, which is
what the research actually objects to hard-coding) -- the OI-based early-
migration trigger is a documented follow-up once real volume/OI data exists.
"""
from __future__ import annotations

from datetime import date

from trading_system.data.interfaces import ContractMeta


def active_contract_for(
    underlying: str,
    as_of: date,
    universe: list[ContractMeta],
    roll_days_before_expiry: int = 5,
) -> str | None:
    """The contract to hold for `underlying` on `as_of`: the nearest
    unexpired contract that is not within `roll_days_before_expiry` days of
    its own expiry, falling back to the nearest unexpired contract if none
    qualifies (e.g. right before a roll completes).
    """
    candidates = sorted(
        (
            c
            for c in universe
            if c.underlying == underlying and c.expiry_date is not None and c.expiry_date >= as_of
        ),
        key=lambda c: c.expiry_date,
    )
    if not candidates:
        return None
    eligible = [c for c in candidates if (c.expiry_date - as_of).days > roll_days_before_expiry]
    chosen = eligible[0] if eligible else candidates[0]
    return chosen.symbol


def front_and_next_contracts(
    underlying: str, as_of: date, universe: list[ContractMeta]
) -> tuple[ContractMeta | None, ContractMeta | None]:
    """The two nearest unexpired contracts for `underlying` -- MCX_CARRY_01
    requires exactly this pair to compute its curve slope.
    """
    candidates = sorted(
        (
            c
            for c in universe
            if c.underlying == underlying and c.expiry_date is not None and c.expiry_date >= as_of
        ),
        key=lambda c: c.expiry_date,
    )
    front = candidates[0] if len(candidates) > 0 else None
    next_ = candidates[1] if len(candidates) > 1 else None
    return front, next_
