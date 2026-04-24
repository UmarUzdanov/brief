"""Docling extraction layer.

Surfaces the items the judgment layer cares about: pictures (with bounding
boxes for cropping), tables (with row/col counts), and a count of text blocks
and pages. Downstream modules will feed these to Claude.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Picture:
    page: int
    bbox: tuple[float, float, float, float]


@dataclass
class Table:
    page: int
    bbox: tuple[float, float, float, float]
    rows: int
    cols: int


@dataclass
class Extracted:
    pages: int
    text_blocks: int
    pictures: list[Picture] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)


def _bbox(prov) -> tuple[float, float, float, float]:
    b = getattr(prov, "bbox", None)
    if b is None:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        float(getattr(b, "l", 0.0)),
        float(getattr(b, "t", 0.0)),
        float(getattr(b, "r", 0.0)),
        float(getattr(b, "b", 0.0)),
    )


def extract(pdf_path: str | Path) -> Extracted:
    """Run Docling on a PDF, return the items the judgment layer needs."""
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    doc = result.document

    pictures: list[Picture] = []
    for pic in getattr(doc, "pictures", []) or []:
        provs = getattr(pic, "prov", None) or []
        if not provs:
            continue
        prov = provs[0]
        pictures.append(Picture(page=int(getattr(prov, "page_no", 0)), bbox=_bbox(prov)))

    tables: list[Table] = []
    for tbl in getattr(doc, "tables", []) or []:
        provs = getattr(tbl, "prov", None) or []
        if not provs:
            continue
        prov = provs[0]
        data = getattr(tbl, "data", None)
        rows = int(getattr(data, "num_rows", 0)) if data else 0
        cols = int(getattr(data, "num_cols", 0)) if data else 0
        tables.append(
            Table(page=int(getattr(prov, "page_no", 0)), bbox=_bbox(prov), rows=rows, cols=cols)
        )

    text_blocks = sum(1 for _ in getattr(doc, "texts", []) or [])
    pages = len(getattr(doc, "pages", {}) or {})

    return Extracted(pages=pages, text_blocks=text_blocks, pictures=pictures, tables=tables)
