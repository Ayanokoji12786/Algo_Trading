"""Cross-sectional statistics (India_Implementation_Spec.md EQ_MOM_01:
``score = 0.5*zscore_cross_section(mom6_adj) + 0.5*zscore_cross_section(mom12_adj)``).

Unlike every other feature in this package, a cross-sectional z-score is not
a pure function of one instrument's own history -- it needs the whole
eligible universe's values on the SAME as_of date at once. The leakage rule
is therefore about the caller, not this function: every value passed in
must already be computed from information available as of the same
decision date (each value itself comes from features.returns/volatility
functions fed PIT-sliced history), so standardizing across them here
introduces no additional look-ahead.
"""
from __future__ import annotations

import numpy as np


def zscore_cross_section(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    arr = np.array(list(values.values()), dtype=float)
    mean = arr.mean()
    std = arr.std(ddof=1) if len(arr) > 1 else 0.0
    if std == 0.0:
        return {k: 0.0 for k in values}
    return {k: float((v - mean) / std) for k, v in values.items()}
