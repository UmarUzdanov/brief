"""Reading-order verification.

For each page, gather items (texts, pictures, tables) with their bounding
boxes, ask Claude what the visual reading order should be, and report any
mismatch between Docling's document order and the visual order.

Used standalone for ad-hoc checks; not wired into augment() yet because it
adds one Claude call per page (heavy on long PDFs).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from brief.judge import _claude_p


@dataclass
class Item:
    idx: int
    kind: str  # "text" | "picture" | "table"
    bbox: tuple[float, float, float, float]
    preview: str


@dataclass
class OrderIssue:
    page: int
    docling_order: list[int]
    suggested_order: list[int]


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


def items_per_page(doc) -> dict[int, list[Item]]:
    """Walk the doc, group items by page in document order."""
    by_page: dict[int, list[Item]] = defaultdict(list)
    for kind, source in (
        ("text", getattr(doc, "texts", []) or []),
        ("picture", getattr(doc, "pictures", []) or []),
        ("table", getattr(doc, "tables", []) or []),
    ):
        for item in source:
            provs = getattr(item, "prov", None) or []
            if not provs:
                continue
            prov = provs[0]
            preview_src = getattr(item, "text", "") or ""
            preview = preview_src[:60].strip() if preview_src else f"[{kind}]"
            by_page[int(getattr(prov, "page_no", 0))].append(
                Item(idx=-1, kind=kind, bbox=_bbox(prov), preview=preview)
            )
    out: dict[int, list[Item]] = {}
    for page, items in by_page.items():
        for i, it in enumerate(items):
            it.idx = i
        out[page] = items
    return out


def _parse_int_list(text: str) -> list[int]:
    out: list[int] = []
    for tok in text.replace("\n", ",").split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.append(int(tok))
    return out


def reading_order_for_page(items: list[Item]) -> list[int]:
    """Ask Claude for the visual reading order. Returns indices in suggested order."""
    if len(items) <= 1:
        return [it.idx for it in items]
    rendered = "\n".join(
        f"[{it.idx}] {it.kind} bbox=({it.bbox[0]:.0f},{it.bbox[1]:.0f},"
        f"{it.bbox[2]:.0f},{it.bbox[3]:.0f}) preview={it.preview!r}"
        for it in items
    )
    prompt = (
        "Below are layout items on a PDF page. Return ONLY a comma-separated "
        "list of item indices in visual reading order (top-to-bottom, "
        "left-to-right, accounting for columns).\n\n"
        f"{rendered}\n\n"
        'Reply with just the indices, e.g. "0,2,1,3" — no preamble.'
    )
    return _parse_int_list(_claude_p(prompt, allowed_tools=[]))


def check(pdf_path: str | Path) -> list[OrderIssue]:
    """Run Docling, then ask Claude for reading-order on each page; return mismatches."""
    from docling.document_converter import DocumentConverter

    doc = DocumentConverter().convert(str(pdf_path)).document
    issues: list[OrderIssue] = []
    for page, items in items_per_page(doc).items():
        if len(items) <= 1:
            continue
        original = [it.idx for it in items]
        try:
            suggested = reading_order_for_page(items)
        except Exception:
            continue
        # Suggestions might be incomplete; only flag when the prefix differs.
        if suggested and suggested[: len(original)] != original:
            issues.append(
                OrderIssue(page=page, docling_order=original, suggested_order=suggested)
            )
    return issues
