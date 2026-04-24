"""End-to-end remediation: brief judgment + pdfua-ac writer.

Pipeline:
  1. brief.augment(pdf) -> Claude judgment per picture (alt-text)
     (or load a pre-computed augment JSON via from_json=)
  2. pythonproject.remediate(pdf, out) -> tagged PDF with "Figure" placeholders
  3. Walk output PDF's StructTreeRoot, replace /Alt on Figure elements with
     Claude's alt-text in document order.

The pythonproject library (Umar's prior work) handles the 89 machine-checkable
PDF/UA-1 conditions (struct tree, fonts, ToUnicode, catalog, XMP). brief
contributes the judgment for the remaining 47.
"""
from __future__ import annotations

import json
from pathlib import Path

import pikepdf

from brief.augment import (
    Augmented,
    AugmentedLink,
    AugmentedPicture,
    AugmentedTable,
    augment,
)


def _load_augmented(path: Path) -> Augmented:
    data = json.loads(path.read_text())
    return Augmented(
        pdf=data["pdf"],
        pages=data["pages"],
        pictures=[AugmentedPicture(**p) for p in data["pictures"]],
        tables=[AugmentedTable(**t) for t in data["tables"]],
        links=[AugmentedLink(**lk) for lk in data.get("links", [])],
    )


def _find_figures(elem, out: list) -> None:
    """Walk a StructTreeRoot, collecting Figure struct elements in document order."""
    if not isinstance(elem, pikepdf.Dictionary):
        return
    s = elem.get("/S")
    if s is not None and str(s) == "/Figure":
        out.append(elem)
    kids = elem.get("/K")
    if kids is None:
        return
    if isinstance(kids, pikepdf.Array):
        for kid in kids:
            _find_figures(kid, out)
    else:
        _find_figures(kids, out)


def pipeline(
    input_pdf: Path,
    output_pdf: Path,
    *,
    from_json: Path | None = None,
) -> dict:
    """Run the full brief + pdfua-ac pipeline. Returns a report dict.

    from_json: optional path to a pre-computed augment JSON. If given,
    skip the brief.augment step (no Claude calls).
    """
    # Local import: pythonproject defines a top-level `remediate` module
    # whose main function is also called `remediate`. Keep the import scoped.
    from remediate import remediate as pdfua_write

    # 1. brief judgment (or load from cache)
    if from_json is not None:
        augmented = _load_augmented(from_json)
    else:
        augmented = augment(input_pdf)

    # 2. pdfua-ac writes the tagged PDF (placeholders for /Alt)
    pdfua_report = pdfua_write(input_pdf, output_pdf)

    # 3. Inject Claude alt-text into Figure struct elements
    pdf = pikepdf.open(output_pdf, allow_overwriting_input=True)
    figures: list = []
    root_obj = pdf.Root.get("/StructTreeRoot")
    if root_obj is not None:
        _find_figures(root_obj, figures)

    pictures = augmented.pictures
    injected = 0
    for fig, pic in zip(figures, pictures):
        alt = pic.alt_text.strip()
        if not alt:
            continue
        if alt.upper().startswith("ERROR") or alt.upper() == "DECORATIVE":
            continue
        fig["/Alt"] = pikepdf.String(alt)
        injected += 1

    pdf.save(output_pdf)

    return {
        "input": str(input_pdf),
        "output": str(output_pdf),
        "figures_in_pdf": len(figures),
        "pictures_from_brief": len(pictures),
        "alt_text_injected": injected,
        "pdfua_report": pdfua_report,
    }
