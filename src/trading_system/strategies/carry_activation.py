"""Carry activation gate (Research.md "Carry satellite" -- activation
criteria).

IMPORTANT SCOPE NOTE: this implements a NECESSARY SUBSET of Research.md's
full gate -- positive net value after base costs, survival under 2x cost
stress, and low return-correlation with trend. It does NOT implement the
parameter/sign-definition stability sweep or the joint "portfolio
improvement that survives across folds and regimes" check, both of which
require real multi-regime data to test meaningfully (Docs/Implementation_Spec.md
S3). A True result from evaluate_carry_activation() is therefore a
first-pass filter, not sufficient on its own to flip carry_enabled=True in
production -- flagging this explicitly per Prompt.md S3's "do not silently
modify/simplify a validation requirement" instruction.
"""
from __future__ import annotations

import pandas as pd


def evaluate_carry_activation(
    trend_daily_returns: pd.Series,
    carry_daily_returns: pd.Series,
    carry_metrics_base: dict[str, float],
    carry_metrics_stress_2x: dict[str, float],
    correlation_threshold: float = 0.3,
) -> dict[str, object]:
    aligned = pd.concat(
        [trend_daily_returns.rename("trend"), carry_daily_returns.rename("carry")],
        axis=1,
        join="inner",
    ).dropna()
    correlation = (
        float(aligned["trend"].corr(aligned["carry"])) if len(aligned) > 2 else float("nan")
    )

    positive_net_value = (
        carry_metrics_base.get("cagr", float("-inf")) > 0
        and carry_metrics_base.get("sharpe", float("-inf")) > 0
    )
    survives_2x_costs = carry_metrics_stress_2x.get("sharpe", float("-inf")) > 0
    low_correlation = (not pd.isna(correlation)) and abs(correlation) < correlation_threshold

    return {
        "positive_net_value_after_base_costs": positive_net_value,
        "survives_2x_cost_stress": survives_2x_costs,
        "low_correlation_with_trend": low_correlation,
        "measured_correlation_with_trend": correlation,
        "passes_implemented_subset_of_gate": (
            positive_net_value and survives_2x_costs and low_correlation
        ),
        "note": (
            "This does not evaluate parameter stability or cross-fold/regime "
            "portfolio improvement -- see this module's docstring. A True "
            "result here is necessary, not sufficient, for enabling carry."
        ),
    }
