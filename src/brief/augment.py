"""End-to-end augmentation: Docling extract + Claude judgment.

augment(pdf_path) returns an Augmented record with alt-text per picture and
detected header rows per table. CLI surface lives in cli.py; this module is
importable for tests and downstream callers.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from brief.judge import alt_text, header_rows


@dataclass
class AugmentedPicture:
    page: int
    bbox: tuple[float, float, float, float]
    alt_text: str


@dataclass
class AugmentedTable:
    page: int
    bbox: tuple[float, float, float, float]
    rows: int
    cols: int
    header_rows: list[int]


@dataclass
class Augmented:
    pdf: str
    pages: int
    pictures: list[AugmentedPicture] = field(default_factory=list)
    tables: list[AugmentedTable] = field(default_factory=list)


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


def _picture_png(picture, doc) -> bytes | None:
    img = picture.get_image(doc) if hasattr(picture, "get_image") else None
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _table_grid(table) -> list[list[str]]:
    data = getattr(table, "data", None)
    if not data:
        return []
    n_rows = int(getattr(data, "num_rows", 0))
    n_cols = int(getattr(data, "num_cols", 0))
    if n_rows == 0 or n_cols == 0:
        return []
    grid: list[list[str]] = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for cell in getattr(data, "table_cells", []) or []:
        r = int(getattr(cell, "start_row_offset_idx", 0))
        c = int(getattr(cell, "start_col_offset_idx", 0))
        if 0 <= r < n_rows and 0 <= c < n_cols:
            grid[r][c] = getattr(cell, "text", "") or ""
    return grid


def augment(
    pdf_path: str | Path,
    *,
    client: anthropic.Anthropic | None = None,
) -> Augmented:
    """Run Docling on PDF, then Claude over each picture and each table."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    if client is None:
        client = anthropic.Anthropic()

    opts = PdfPipelineOptions()
    opts.generate_picture_images = True
    opts.images_scale = 2.0

    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
    )
    result = converter.convert(str(pdf_path))
    doc = result.document

    pictures: list[AugmentedPicture] = []
    for pic in getattr(doc, "pictures", []) or []:
        provs = getattr(pic, "prov", None) or []
        if not provs:
            continue
        prov = provs[0]
        png = _picture_png(pic, doc)
        if png is None:
            continue
        try:
            text = alt_text(client, png, media_type="image/png")
        except Exception as exc:  # surface errors per-item; continue the run
            text = f"ERROR: {exc}"
        pictures.append(
            AugmentedPicture(
                page=int(getattr(prov, "page_no", 0)),
                bbox=_bbox(prov),
                alt_text=text,
            )
        )

    tables: list[AugmentedTable] = []
    for tbl in getattr(doc, "tables", []) or []:
        provs = getattr(tbl, "prov", None) or []
        if not provs:
            continue
        prov = provs[0]
        grid = _table_grid(tbl)
        try:
            hdrs = header_rows(client, grid) if grid else []
        except Exception:
            hdrs = []
        data = getattr(tbl, "data", None)
        rows = int(getattr(data, "num_rows", 0)) if data else 0
        cols = int(getattr(data, "num_cols", 0)) if data else 0
        tables.append(
            AugmentedTable(
                page=int(getattr(prov, "page_no", 0)),
                bbox=_bbox(prov),
                rows=rows,
                cols=cols,
                header_rows=hdrs,
            )
        )

    pages = len(getattr(doc, "pages", {}) or {})
    return Augmented(pdf=str(pdf_path), pages=pages, pictures=pictures, tables=tables)
