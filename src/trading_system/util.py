"""Shared, process-independent utilities.

stable_hash exists because Python's built-in hash() on strings is
randomized per-process (PYTHONHASHSEED, on by default since Python 3.3) --
using it to derive an RNG seed from a symbol name means "the same config"
silently produces DIFFERENT synthetic data every time a fresh Python
process runs it, which is a direct violation of Prompt.md S28's
reproducibility requirement ("a backtest should be reproducible from its
configuration"). This was a real bug, found by comparing two robustness-
suite runs from separate process invocations that were supposed to be
identical and weren't -- see Docs/Implementation_Spec.md's assumptions
register for the incident writeup. Every per-symbol RNG seed derivation in
this codebase must use this function, never the bare hash() builtin.
"""
from __future__ import annotations

import hashlib


def stable_hash(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16)
