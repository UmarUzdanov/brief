"""Unit tests for augment.py pure helpers (no Docling, no Claude)."""
from __future__ import annotations

from types import SimpleNamespace as N

from brief.augment import _bbox, _table_grid


def test_bbox_full():
    prov = N(bbox=N(l=10.0, t=20.0, r=30.0, b=40.0))
    assert _bbox(prov) == (10.0, 20.0, 30.0, 40.0)


def test_bbox_missing_zeros():
    assert _bbox(N(bbox=None)) == (0.0, 0.0, 0.0, 0.0)
    assert _bbox(N()) == (0.0, 0.0, 0.0, 0.0)


def test_bbox_partial():
    prov = N(bbox=N(l=5.0))
    assert _bbox(prov) == (5.0, 0.0, 0.0, 0.0)


def test_table_grid_dense():
    cells = [
        N(start_row_offset_idx=0, start_col_offset_idx=0, text="A"),
        N(start_row_offset_idx=0, start_col_offset_idx=1, text="B"),
        N(start_row_offset_idx=1, start_col_offset_idx=0, text="C"),
        N(start_row_offset_idx=1, start_col_offset_idx=1, text="D"),
    ]
    table = N(data=N(num_rows=2, num_cols=2, table_cells=cells))
    assert _table_grid(table) == [["A", "B"], ["C", "D"]]


def test_table_grid_sparse_fills_blanks():
    cells = [
        N(start_row_offset_idx=0, start_col_offset_idx=0, text="A"),
        N(start_row_offset_idx=1, start_col_offset_idx=1, text="D"),
    ]
    table = N(data=N(num_rows=2, num_cols=2, table_cells=cells))
    assert _table_grid(table) == [["A", ""], ["", "D"]]


def test_table_grid_empty():
    table = N(data=N(num_rows=0, num_cols=0, table_cells=[]))
    assert _table_grid(table) == []


def test_table_grid_no_data():
    assert _table_grid(N(data=None)) == []
