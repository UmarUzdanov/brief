"""Unit tests for judge.py response parsers (no Claude calls)."""
from __future__ import annotations

from brief.judge import _parse_header_rows


def test_none_returns_empty():
    assert _parse_header_rows("NONE") == []
    assert _parse_header_rows("none") == []
    assert _parse_header_rows("  NONE  ") == []


def test_single_index():
    assert _parse_header_rows("0") == [0]
    assert _parse_header_rows("3") == [3]


def test_multiple_indices():
    assert _parse_header_rows("0, 1") == [0, 1]
    assert _parse_header_rows("0,1,2") == [0, 1, 2]


def test_tolerates_extra_whitespace_and_blanks():
    assert _parse_header_rows("0,, 2") == [0, 2]
    assert _parse_header_rows("  0 , 1 ") == [0, 1]


def test_garbage_returns_empty():
    assert _parse_header_rows("the first row is the header") == []
    assert _parse_header_rows("") == []
