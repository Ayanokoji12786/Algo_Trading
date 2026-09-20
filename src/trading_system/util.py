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

validate_symbol_name exists because any code that builds a filesystem path
from a symbol name (LocalFileDataSource, brokers/base.py's cache) is a
path-traversal vulnerability if the symbol is ever attacker-controlled --
e.g. a symbol like ``../../../etc/passwd`` would let a hostile universe
listing read or write outside the intended directory. ContractMeta.symbol
is a plain string with no built-in validation, so this check is the layer
that keeps that class of bug from existing. Every function that concatenates
a symbol into a filesystem path must call this first.
"""
from __future__ import annotations

import hashlib
import re

_SAFE_SYMBOL_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def stable_hash(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest(), 16)


def validate_symbol_name(symbol: str) -> str:
    """Return ``symbol`` unchanged after asserting it is safe to embed in a
    filesystem path. Rejects any symbol containing path separators, ``..``,
    a leading dot (hidden-file convention), or characters outside the
    allowlist ``[A-Za-z0-9._-]``. Raises ValueError otherwise.
    """
    if not isinstance(symbol, str) or not symbol:
        raise ValueError(f"Symbol name must be a non-empty string, got {symbol!r}")
    if not _SAFE_SYMBOL_RE.fullmatch(symbol):
        raise ValueError(
            f"Symbol name {symbol!r} contains unsafe characters -- only "
            "letters, digits, '.', '_', '-' are allowed (this restriction "
            "prevents path-traversal attacks via symbol names used as file "
            "paths in the vendor cache and LocalFileDataSource; see "
            "trading_system/util.py's docstring)."
        )
    if symbol.startswith(".") or ".." in symbol:
        raise ValueError(
            f"Symbol name {symbol!r} is not permitted -- must not start with "
            "'.' or contain '..' (path-traversal protection)."
        )
    return symbol
