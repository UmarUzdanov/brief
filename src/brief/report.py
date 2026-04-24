"""HTML report rendering for an Augmented run.

Self-contained: images are embedded as base64 data URIs. No external CSS or
JS. Open in any browser.
"""
from __future__ import annotations

import html
from pathlib import Path

from brief.augment import Augmented


_CSS = """
:root { --ink:#1E2761; --ice:#CADCFC; --paper:#FFFFFF; --rule:#E5E7EB; --muted:#6B7280; --warn:#D97706; }
* { box-sizing:border-box; }
body { font: 15px/1.5 -apple-system, system-ui, sans-serif; color: var(--ink); margin: 0; background: #F9FAFB; }
header { background: var(--ink); color: var(--paper); padding: 20px 32px; }
header h1 { font: 600 22px/1 Georgia, serif; margin: 0; letter-spacing: 0.01em; }
header p { margin: 6px 0 0; color: var(--ice); font-size: 13px; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 32px; }
section { background: var(--paper); border: 1px solid var(--rule); border-radius: 6px; margin: 16px 0; }
section h2 { font: 600 16px/1 Georgia, serif; margin: 0; padding: 14px 18px; border-bottom: 1px solid var(--rule); }
.summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; }
.summary > div { padding: 14px 18px; border-right: 1px solid var(--rule); }
.summary > div:last-child { border-right: none; }
.summary .n { font: 600 28px/1 Georgia, serif; }
.summary .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 4px; }
.row { display: grid; grid-template-columns: 220px 1fr; gap: 18px; padding: 16px 18px; border-bottom: 1px solid var(--rule); }
.row:last-child { border-bottom: none; }
.row img { max-width: 220px; max-height: 160px; border: 1px solid var(--rule); border-radius: 3px; }
.row .meta { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
.row .alt { font-size: 14px; }
.row .alt.decorative { color: var(--muted); font-style: italic; }
.row .alt.error { color: var(--warn); }
.tablegrid { padding: 14px 18px; }
.tablegrid table { border-collapse: collapse; font-size: 13px; }
.tablegrid td { border: 1px solid var(--rule); padding: 4px 8px; }
.tablegrid tr.header td { background: var(--ice); font-weight: 600; }
.tablemeta { color: var(--muted); font-size: 12px; padding: 0 18px 14px; }
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def render(augmented: Augmented) -> str:
    a = augmented
    pdf_name = Path(a.pdf).name
    pic_n = len(a.pictures)
    tbl_n = len(a.tables)
    decor = sum(1 for p in a.pictures if p.alt_text.strip().upper() == "DECORATIVE")

    out: list[str] = []
    out.append("<!doctype html>")
    out.append('<html lang="en"><head><meta charset="utf-8">')
    out.append(f"<title>brief — {_esc(pdf_name)}</title>")
    out.append(f"<style>{_CSS}</style></head><body>")
    out.append(
        f'<header><h1>brief</h1><p>{_esc(pdf_name)} · '
        f"{a.pages} pages · {pic_n} pictures · {tbl_n} tables</p></header><main>"
    )

    out.append('<section><h2>Summary</h2><div class="summary">')
    out.append(f'<div><div class="n">{a.pages}</div><div class="label">pages</div></div>')
    out.append(f'<div><div class="n">{pic_n}</div><div class="label">pictures</div></div>')
    out.append(f'<div><div class="n">{decor}</div><div class="label">decorative</div></div>')
    out.append(f'<div><div class="n">{tbl_n}</div><div class="label">tables</div></div>')
    out.append("</div></section>")

    if a.pictures:
        out.append("<section><h2>Pictures &amp; Claude alt-text</h2>")
        for i, pic in enumerate(a.pictures, 1):
            klass = "alt"
            txt = pic.alt_text.strip()
            if txt.upper() == "DECORATIVE":
                klass += " decorative"
            elif txt.upper().startswith("ERROR"):
                klass += " error"
            img_html = ""
            if pic.image_b64:
                img_html = (
                    f'<img alt="picture {i}" '
                    f'src="data:image/png;base64,{pic.image_b64}">'
                )
            out.append('<div class="row">')
            out.append(f"<div>{img_html}</div>")
            out.append(
                f'<div><div class="meta">page {pic.page} · bbox '
                f"({pic.bbox[0]:.0f}, {pic.bbox[1]:.0f}, "
                f"{pic.bbox[2]:.0f}, {pic.bbox[3]:.0f})</div>"
                f'<div class="{klass}">{_esc(txt)}</div></div>'
            )
            out.append("</div>")
        out.append("</section>")

    if a.tables:
        out.append("<section><h2>Tables &amp; detected header rows</h2>")
        for i, tbl in enumerate(a.tables, 1):
            hdrs = ", ".join(str(h) for h in tbl.header_rows) or "none"
            out.append(
                f'<div class="tablemeta">table {i} · page {tbl.page} · '
                f"{tbl.rows}×{tbl.cols} · header row(s): {hdrs}</div>"
            )
        out.append("</section>")

    out.append("</main></body></html>")
    return "\n".join(out)
