"""Regression test for a real bug found in this project: Python's built-in
hash() on strings is randomized per process (PYTHONHASHSEED), so every
synthetic data generator that derived a per-symbol RNG seed from hash(symbol)
was silently producing DIFFERENT "random" data every time a fresh process
ran it, even with an identical configured random_seed -- a direct violation
of Prompt.md S28 ("a backtest should be reproducible from its
configuration"). Found by comparing two robustness-suite runs that were
supposed to be identical and weren't. Fixed by trading_system/util.py's
stable_hash(). This test spawns two SEPARATE Python processes (a same-
process test cannot catch this class of bug, since PYTHONHASHSEED is fixed
for the lifetime of one process) with different explicit PYTHONHASHSEED
values and asserts they produce byte-identical synthetic data.
"""
from __future__ import annotations

import os
import subprocess
import sys

_SCRIPT = """
from datetime import date
from trading_system.data.synthetic import SyntheticFuturesDataSource
from trading_system.config.schema import DataConfig

config = DataConfig(
    asset_classes=("equity_index", "fx"),
    instruments_per_asset_class=2,
    start_date=date(2015, 1, 1),
    end_date=date(2016, 12, 31),
    random_seed=42,
)
source = SyntheticFuturesDataSource(config)
for meta in source.get_universe():
    df = source.get_prices(meta.symbol)
    print(meta.symbol, df["close"].sum())
"""


def _run_with_hashseed(hashseed: str) -> str:
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = hashseed
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_synthetic_data_is_identical_across_processes_with_different_hashseeds():
    output_a = _run_with_hashseed("111")
    output_b = _run_with_hashseed("999")
    assert output_a == output_b
    assert len(output_a) > 0
