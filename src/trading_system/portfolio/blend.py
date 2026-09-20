"""Blend sleeves at equal (or configured) ex-ante risk share, then scale to
a portfolio vol target -- Docs/India_Implementation_Spec.md RISK_01:

    k_t = min(1, 0.10 / sigma_hat_p,t)     -- scale DOWN only, never up

Deliberately simpler than portfolio/aggregation.py's
compute_multi_strategy_target_weights: each sleeve here has ALREADY fully
sized itself (selection, inverse-vol weighting, caps all done inside the
sleeve -- see cross_sectional_momentum.py, mcx_trend_sleeve.py), so blending
is just a risk-share-weighted sum, not another layer of asset-class
equalization. This is the right shape for combining heterogeneous sleeve
types (a cross-sectional equity selector and a time-series commodity
trend), which don't share one internal sizing formula the way the
global-futures trend+carry sleeves do.
"""
from __future__ import annotations

import pandas as pd

from trading_system.portfolio.covariance import portfolio_vol_from_covariance


def blend_sleeves(
    sleeve_weights: dict[str, dict[str, float]],
    risk_shares: dict[str, float],
) -> dict[str, float]:
    combined: dict[str, float] = {}
    for sleeve_id, weights in sleeve_weights.items():
        share = risk_shares.get(sleeve_id, 0.0)
        if share == 0.0:
            continue
        for symbol, w in weights.items():
            combined[symbol] = combined.get(symbol, 0.0) + w * share
    return combined


def scale_to_vol_target(
    weights: dict[str, float],
    cov: pd.DataFrame | None,
    vol_target_annualized: float,
) -> dict[str, float]:
    if not weights or cov is None:
        return weights
    estimated_vol = portfolio_vol_from_covariance(weights, cov)
    if estimated_vol <= 0:
        return weights
    k = min(1.0, vol_target_annualized / estimated_vol)
    return {sym: w * k for sym, w in weights.items()}
