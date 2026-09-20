"""Regression tests for validate_symbol_name -- the layer that keeps
symbol-derived file paths safe from traversal attacks
(src/trading_system/util.py's docstring for the incident writeup).
"""
import pytest

from trading_system.util import validate_symbol_name


def test_accepts_typical_symbols():
    for good in ("RELIANCE", "NIFTY", "GOLD_202601", "NSE.FUT", "us-tech-100", "aaa"):
        assert validate_symbol_name(good) == good


def test_rejects_path_separators():
    for bad in ("A/B", "..\\C", "foo\\bar", "a/../b"):
        with pytest.raises(ValueError):
            validate_symbol_name(bad)


def test_rejects_dotdot_and_hidden_prefix():
    for bad in ("..", "..evil", ".hidden", "a..b", "..\\"):
        with pytest.raises(ValueError):
            validate_symbol_name(bad)


def test_rejects_nul_and_unusual_chars():
    for bad in ("A B", "A;rm", "A$B", "A\x00B", ""):
        with pytest.raises(ValueError):
            validate_symbol_name(bad)


def test_rejects_non_string():
    for bad in (None, 123, ["A"], b"A"):
        with pytest.raises(ValueError):
            validate_symbol_name(bad)  # type: ignore[arg-type]
