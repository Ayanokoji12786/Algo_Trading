"""Historical regime series and regime-conditioned performance
(Prompt.md S10: "Produce a historical regime series so that I can inspect:
date -> detected regime. Then evaluate whether strategy performance
actually differs across detected regimes.")

Builds on features/regime.py's diagnostics-only functions -- nothing here
feeds back into strategy sizing, it only reports.
"""
from __future__ import annotations

import pandas as pd

from trading_system.backtest.metrics import compute_metrics
from trading_system.config.schema import TrendStrategyConfig
from trading_system.data.pit_store import PointInTimeStore
from trading_system.features.regime import compute_regime_snapshot
from trading_system.features.trend_signal import composite_trend_score
from trading_system.features.volatility import ewma_annualized_vol


def build_regime_history(
    store: PointInTimeStore,
    trend_config: TrendStrategyConfig,
    dates: list[pd.Timestamp],
    correlation_window_days: int = 60,
) -> pd.DataFrame:
    close_matrix = store.close_matrix()
    instrument_returns = close_matrix.pct_change()

    rows = []
    for as_of in dates:
        trend_scores: dict[str, float] = {}
        vol_by_symbol: dict[str, float] = {}
        vol_history_by_symbol: dict[str, pd.Series] = {}

        for meta in store.universe:
            history = store.history_as_of(meta.symbol, as_of)
            if history.empty:
                continue
            close = history["close"]
            score = composite_trend_score(close, trend_config.lookback_days)
            if score is not None:
                trend_scores[meta.symbol] = score
            vol_series = close.pct_change().rolling(trend_config.vol_window_days).std() * (
                252**0.5
            )
            current_vol = ewma_annualized_vol(close, trend_config.vol_window_days)
            if current_vol is not None:
                vol_by_symbol[meta.symbol] = current_vol
                vol_history_by_symbol[meta.symbol] = vol_series

        if as_of not in instrument_returns.index:
            continue
        pos = instrument_returns.index.get_loc(as_of)
        returns_so_far = instrument_returns.iloc[: pos + 1]

        snapshot = compute_regime_snapshot(
            trend_scores, vol_by_symbol, vol_history_by_symbol, returns_so_far, correlation_window_days
        )
        rows.append({"date": as_of, **snapshot})

    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


def performance_by_regime_bucket(
    equity_curve: pd.Series,
    regime_history: pd.DataFrame,
    regime_column: str,
    n_buckets: int = 3,
) -> pd.DataFrame:
    """Quantile-buckets `regime_column`'s values, then reports
    compute_metrics on daily returns whose date falls in each bucket
    (Prompt.md S10's "evaluate whether performance actually differs across
    detected regimes" -- an honest answer requires this even if it shows no
    meaningful difference).
    """
    daily_returns = equity_curve.pct_change().dropna()
    series = regime_history[regime_column].dropna()
    if len(series) < n_buckets * 5:
        return pd.DataFrame()

    try:
        buckets = pd.qcut(series, q=n_buckets, duplicates="drop")
    except ValueError:
        return pd.DataFrame()

    rows = []
    for bucket_label in buckets.cat.categories:
        bucket_dates = series.index[buckets == bucket_label]
        bucket_returns = daily_returns.reindex(bucket_dates).dropna()
        if len(bucket_returns) < 5:
            continue
        rebased = (1 + bucket_returns).cumprod()
        metrics = compute_metrics(rebased)
        rows.append({"bucket": str(bucket_label), "n_days": len(bucket_returns), **metrics})
    return pd.DataFrame(rows)
