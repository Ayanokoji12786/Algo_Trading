"""Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014), the multiple-
testing correction Research.md names as its default recommendation
("DSR or an equivalent procedure" -- Implementation_Spec.md audit item 14
picks DSR as the concrete choice).

Why this matters here specifically: Docs/Implementation_Spec.md S6/S8
requires tracking "number of experiments... number of tested combinations"
(Prompt.md S26) and warns that a good-looking result among many tested
configurations may just be the best of a large search, not a real edge. DSR
answers "how surprising is this Sharpe ratio, given how many configurations
were actually tried and how noisy Sharpe estimation is for this sample
size and return distribution?" It deflates the observed Sharpe by the
expected maximum Sharpe one would see from pure noise across that many
trials, then reports the probability the true Sharpe exceeds zero.

This module intentionally requires the caller to supply the actual set of
trial Sharpe ratios that were tried (e.g. from a robustness sweep's results)
rather than a bare trial count, so the correction reflects what was really
searched -- Prompt.md S26 explicitly requires not hiding unsuccessful
experiments, and passing a fabricated/round trial count would silently
violate that.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

_EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe_under_null(sharpe_std_across_trials: float, n_trials: int) -> float:
    """Expected maximum Sharpe ratio observed across n_trials independent
    noise trials with the given cross-trial standard deviation, via the
    Euler-Mascheroni approximation to the expectation of the max of n iid
    standard normals (Bailey & Lopez de Prado, eq. 8).
    """
    if n_trials <= 1 or sharpe_std_across_trials <= 0:
        return 0.0
    z1 = norm.ppf(1 - 1.0 / n_trials)
    z2 = norm.ppf(1 - 1.0 / (n_trials * np.e))
    return sharpe_std_across_trials * (
        (1 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2
    )


def deflated_sharpe_ratio(
    trial_sharpes: pd.Series,
    selected_sharpe: float,
    daily_returns: pd.Series,
) -> dict[str, float]:
    """Returns a dict with the deflated Sharpe probability and its inputs,
    so the correction is auditable rather than a single opaque number.

    trial_sharpes: Sharpe ratios from every configuration actually tested in
        this experiment family (the search whose multiple-testing risk we're
        correcting for) -- must include the selected configuration's Sharpe.
    selected_sharpe: the Sharpe ratio of the configuration being evaluated
        (normally the frozen baseline, or the best of the sweep).
    daily_returns: the selected configuration's daily returns, used for the
        skew/kurtosis adjustment to the Sharpe ratio's own sampling variance.
    """
    n_trials = len(trial_sharpes)
    sharpe_std = float(trial_sharpes.std(ddof=1)) if n_trials > 1 else 0.0
    sr_benchmark = expected_max_sharpe_under_null(sharpe_std, n_trials)

    n_obs = len(daily_returns)
    skew = float(daily_returns.skew()) if n_obs > 2 else 0.0
    excess_kurtosis = float(daily_returns.kurt()) if n_obs > 3 else 0.0  # pandas .kurt() is already excess

    if n_obs <= 1:
        return {
            "deflated_sharpe_probability": float("nan"),
            "sharpe_benchmark_from_multiple_testing": sr_benchmark,
            "n_trials": n_trials,
            "n_observations": n_obs,
        }

    variance_of_sharpe = (
        1
        - skew * selected_sharpe
        + ((excess_kurtosis) / 4.0) * selected_sharpe**2
    ) / (n_obs - 1)

    if variance_of_sharpe <= 0:
        dsr = float("nan")
    else:
        dsr = float(
            norm.cdf((selected_sharpe - sr_benchmark) / np.sqrt(variance_of_sharpe))
        )

    return {
        "deflated_sharpe_probability": dsr,
        "sharpe_benchmark_from_multiple_testing": sr_benchmark,
        "n_trials": n_trials,
        "n_observations": n_obs,
        "skew": skew,
        "excess_kurtosis": excess_kurtosis,
    }
