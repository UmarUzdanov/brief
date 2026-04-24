"""Hyperlink extraction from a Docling document.

Pulls each hyperlink with its visible text, target URL, and a window of
surrounding text we can pass to link_purpose() in judge.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Link:
    page: int
    visible_text: str
    target_url: str
    surrounding_text: str


def _coerce_url(item) -> str | None:
    """Best-effort target URL extraction; Docling's hyperlink representation varies."""
    for attr in ("hyperlink", "url", "uri", "target"):
        v = getattr(item, attr, None)
        if isinstance(v, str) and v:
            return v
        if v is not None and hasattr(v, "__str__"):
            s = str(v)
            if s.startswith(("http://", "https://", "mailto:")):
                return s
    return None


def collect(doc, *, context_chars: int = 200) -> list[Link]:
    """Walk the doc, yield links with their surrounding text window."""
    texts = list(getattr(doc, "texts", []) or [])
    full_text = " ".join((getattr(t, "text", "") or "") for t in texts)

    out: list[Link] = []
    for item in texts:
        url = _coerce_url(item)
        if not url:
            continue
        text = (getattr(item, "text", "") or "").strip()
        provs = getattr(item, "prov", None) or []
        page = int(getattr(provs[0], "page_no", 0)) if provs else 0

        # cheap context: first occurrence of the visible text in the joined corpus
        ctx = ""
        if text:
            i = full_text.find(text)
            if i != -1:
                left = max(0, i - context_chars)
                right = min(len(full_text), i + len(text) + context_chars)
                ctx = full_text[left:right]
        out.append(
            Link(
                page=page,
                visible_text=text,
                target_url=url,
                surrounding_text=ctx,
            )
        )
    return out
