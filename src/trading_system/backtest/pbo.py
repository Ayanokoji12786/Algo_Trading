"""Probability of Backtest Overfitting (PBO) via Combinatorially Symmetric
Cross-Validation (CSCV) -- Bailey, Borwein, Lopez de Prado & Zhu (2017),
"The Probability of Backtest Overfitting". Required alongside DSR by
Docs/India_Implementation_Spec.md S1.6 ("PBO assessed and not obviously
indicative of selection instability"), and equally applicable to the
global-futures system's robustness sweeps (Docs/Implementation_Spec.md).

Procedure: split the T periods of a returns matrix (columns = trial
configurations) into `n_splits` contiguous blocks. For every way of
choosing half the blocks as "in-sample" and the rest as "out-of-sample",
find whichever configuration performed best in-sample, then see where that
same configuration RANKS out-of-sample. If picking the in-sample winner is
no better than a coin flip at finding a real out-of-sample winner, half the
splits will show that pick landing in the OOS bottom half (logit <= 0) --
PBO is exactly that fraction. PBO near 0.5 means the "best" configuration
found here is indistinguishable from what many trials on noise would
produce; PBO near 0 means it consistently wasn't just noise.

This operates on a plain returns matrix (T x N DataFrame), not on this
system's own robustness-sweep output directly -- callers assemble that
matrix from whatever trials they ran (e.g. by rerunning the sweep with
per-trial return series retained). Kept decoupled so it isn't tied to one
sweep's code shape.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd


def _default_metric(returns: pd.Series) -> float:
    std = returns.std()
    return float(returns.mean() / std) if std > 0 else 0.0


def probability_of_backtest_overfitting(
    returns_matrix: pd.DataFrame,
    n_splits: int = 16,
    metric_fn=None,
) -> dict:
    if n_splits % 2 != 0:
        raise ValueError("n_splits must be even (CSCV splits into equal in/out halves)")

    metric_fn = metric_fn or _default_metric
    t_total, n_configs = returns_matrix.shape
    block_size = t_total // n_splits
    if block_size < 1:
        raise ValueError(
            f"Not enough observations ({t_total}) for {n_splits} splits "
            f"(need at least {n_splits})"
        )

    trimmed = returns_matrix.iloc[: block_size * n_splits]
    blocks = [trimmed.iloc[i * block_size : (i + 1) * block_size] for i in range(n_splits)]

    half = n_splits // 2
    logits: list[float] = []
    for is_indices in itertools.combinations(range(n_splits), half):
        oos_indices = [i for i in range(n_splits) if i not in is_indices]
        is_data = pd.concat([blocks[i] for i in is_indices])
        oos_data = pd.concat([blocks[i] for i in oos_indices])

        is_perf = is_data.apply(metric_fn)
        oos_perf = oos_data.apply(metric_fn)

        best_is_config = is_perf.idxmax()
        oos_rank = oos_perf.rank(ascending=True)[best_is_config]  # 1..N, N = best
        omega = oos_rank / (n_configs + 1)
        if omega <= 0 or omega >= 1:
            continue
        logits.append(float(np.log(omega / (1 - omega))))

    logits_arr = np.array(logits)
    if len(logits_arr) == 0:
        return {"pbo": float("nan"), "n_combinations": 0, "logits_mean": float("nan")}

    return {
        "pbo": float(np.mean(logits_arr <= 0)),
        "n_combinations": len(logits_arr),
        "logits_mean": float(logits_arr.mean()),
        "n_splits": n_splits,
        "n_configs": n_configs,
    }
