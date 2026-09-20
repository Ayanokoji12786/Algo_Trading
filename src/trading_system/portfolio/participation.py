"""Liquidity participation cap (Docs/India_Implementation_Spec.md EQ_MOM_01:
``proposed_trade / median(daily_traded_value, 60d) <= 5%``, tested at 1%/2.5%/5%).

Needs trade-size context (sleeve NAV, current vs. target weight) that a
sleeve's own compute_weights() doesn't have, so it's applied as a
post-processing step by the engine, not inside the strategy.
"""
from __future__ import annotations


def apply_participation_cap(
    target_weights: dict[str, float],
    current_weights: dict[str, float],
    sleeve_nav: float,
    median_traded_value: dict[str, float],
    cap_fraction: float,
) -> dict[str, float]:
    """Limits |target_w - current_w| * sleeve_nav <= cap_fraction * median_traded_value[symbol].

    A symbol with no (or zero) known median traded value gets no capacity --
    the trade is blocked (weight held at its current value) rather than
    silently allowed unlimited size.

    BUG FIX (audit): iterate over the UNION of target and current keys.
    Previous implementation only iterated ``target_weights.items()``, which
    meant a symbol we wanted to fully exit (present in current, absent from
    target) bypassed the cap entirely and disappeared from the returned
    dict -- letting the caller sell the whole position in one bar,
    regardless of liquidity. Now: a full exit is treated as delta = -current_w
    and clipped like any other trade; symbols we're neither entering nor
    exiting stay put.
    """
    capped: dict[str, float] = {}
    all_symbols = set(target_weights) | set(current_weights)
    for sym in all_symbols:
        target_w = target_weights.get(sym, 0.0)
        current_w = current_weights.get(sym, 0.0)
        delta = target_w - current_w
        if delta == 0:
            capped[sym] = current_w
            continue
        mtv = median_traded_value.get(sym, 0.0)
        if mtv <= 0 or sleeve_nav <= 0:
            # No liquidity information: hold current, don't trade.
            capped[sym] = current_w
            continue
        max_delta_weight = (cap_fraction * mtv) / sleeve_nav
        if abs(delta) <= max_delta_weight:
            capped[sym] = target_w
        else:
            allowed_delta = max_delta_weight * (1.0 if delta > 0 else -1.0)
            capped[sym] = current_w + allowed_delta
    return capped
