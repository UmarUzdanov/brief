"""Unit tests for reading-order parsing + per-page item grouping."""
from __future__ import annotations

from types import SimpleNamespace as N

from brief.order import _parse_int_list, items_per_page


def test_parse_int_list_simple():
    assert _parse_int_list("0,1,2") == [0, 1, 2]


def test_parse_int_list_with_spaces():
    assert _parse_int_list("0, 2, 1, 3") == [0, 2, 1, 3]


def test_parse_int_list_with_newlines():
    assert _parse_int_list("0\n2\n1") == [0, 2, 1]


def test_parse_int_list_mixed_garbage():
    assert _parse_int_list("0, foo, 2, bar") == [0, 2]


def test_parse_int_list_empty():
    assert _parse_int_list("") == []


def test_items_per_page_groups_by_page():
    doc = N(
        texts=[
            N(prov=[N(page_no=1, bbox=N(l=10, t=20, r=30, b=40))], text="hello"),
            N(prov=[N(page_no=2, bbox=N(l=11, t=21, r=31, b=41))], text="world"),
        ],
        pictures=[
            N(prov=[N(page_no=1, bbox=N(l=50, t=60, r=70, b=80))], text=""),
        ],
        tables=[
            N(prov=[N(page_no=2, bbox=N(l=12, t=22, r=32, b=42))], text=""),
        ],
    )
    grouped = items_per_page(doc)
    assert sorted(grouped.keys()) == [1, 2]
    assert {it.kind for it in grouped[1]} == {"text", "picture"}
    assert {it.kind for it in grouped[2]} == {"text", "table"}
    # idx is contiguous within each page
    assert [it.idx for it in grouped[1]] == [0, 1]
    assert [it.idx for it in grouped[2]] == [0, 1]


def test_items_per_page_skips_no_prov():
    doc = N(
        texts=[N(prov=[], text="orphan"), N(prov=[N(page_no=1, bbox=N(l=0, t=0, r=0, b=0))], text="kept")],
        pictures=[],
        tables=[],
    )
    grouped = items_per_page(doc)
    assert grouped[1][0].preview == "kept"
    assert len(grouped[1]) == 1
