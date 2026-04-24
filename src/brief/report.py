"""HTML report rendering for an Augmented run.

Self-contained: images embedded as base64. The view mirrors the deck's slide-6
argument — for each picture and table, show what a non-AI tool would output
("Today") next to what brief produces ("With brief").
"""
from __future__ import annotations

import html
from pathlib import Path

from brief.augment import Augmented


_CSS = """
:root { --ink:#1E2761; --ice:#CADCFC; --paper:#FFFFFF; --rule:#E5E7EB; --muted:#6B7280; --warn:#D97706; --good:#065F46; }
* { box-sizing:border-box; }
body { font: 15px/1.5 -apple-system, system-ui, sans-serif; color: var(--ink); margin: 0; background: #F9FAFB; }
header { background: var(--ink); color: var(--paper); padding: 22px 32px; }
header h1 { font: 600 24px/1 Georgia, serif; margin: 0; letter-spacing: 0.01em; }
header p { margin: 6px 0 0; color: var(--ice); font-size: 13px; }
main { max-width: 1200px; margin: 0 auto; padding: 24px 32px; }
section { background: var(--paper); border: 1px solid var(--rule); border-radius: 6px; margin: 16px 0; }
section h2 { font: 600 16px/1 Georgia, serif; margin: 0; padding: 14px 18px; border-bottom: 1px solid var(--rule); }
.summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; }
.summary > div { padding: 14px 18px; border-right: 1px solid var(--rule); }
.summary > div:last-child { border-right: none; }
.summary .n { font: 600 28px/1 Georgia, serif; }
.summary .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; margin-top: 4px; }
.colhead { display: grid; grid-template-columns: 220px 1fr 1fr; gap: 18px; padding: 10px 18px; border-bottom: 1px solid var(--rule); background: #F9FAFB; }
.colhead div { font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
.row { display: grid; grid-template-columns: 220px 1fr 1fr; gap: 18px; padding: 16px 18px; border-bottom: 1px solid var(--rule); align-items: start; }
.row:last-child { border-bottom: none; }
.row img { max-width: 220px; max-height: 180px; border: 1px solid var(--rule); border-radius: 3px; display: block; }
.row .meta { color: var(--muted); font-size: 12px; margin-bottom: 6px; }
.today { color: var(--muted); font-style: italic; }
.brief { font-size: 14px; color: var(--ink); }
.brief.decorative { color: var(--muted); font-style: italic; }
.brief.error { color: var(--warn); font-family: monospace; font-size: 12px; }
.tag { display: inline-block; padding: 2px 7px; border-radius: 3px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; margin-right: 6px; }
.tag.fail { background: #FEF2F2; color: #991B1B; }
.tag.win { background: #ECFDF5; color: var(--good); }
footer { padding: 18px 32px; color: var(--muted); font-size: 12px; text-align: center; }
"""


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def render(augmented: Augmented) -> str:
    a = augmented
    pdf_name = Path(a.pdf).name
    pic_n = len(a.pictures)
    tbl_n = len(a.tables)
    decor = sum(1 for p in a.pictures if p.alt_text.strip().upper() == "DECORATIVE")
    described = pic_n - decor - sum(
        1 for p in a.pictures if p.alt_text.strip().upper().startswith("ERROR")
    )

    out: list[str] = []
    out.append("<!doctype html>")
    out.append('<html lang="en"><head><meta charset="utf-8">')
    out.append(f"<title>brief — {_esc(pdf_name)}</title>")
    out.append(f"<style>{_CSS}</style></head><body>")
    out.append(
        f'<header><h1>brief</h1><p>{_esc(pdf_name)} · '
        f"{a.pages} pages · {pic_n} pictures · {tbl_n} tables · "
        f"{described} pictures described, {decor} flagged decorative</p></header><main>"
    )

    out.append('<section><h2>At a glance</h2><div class="summary">')
    out.append(f'<div><div class="n">{a.pages}</div><div class="label">pages</div></div>')
    out.append(f'<div><div class="n">{pic_n}</div><div class="label">pictures</div></div>')
    out.append(f'<div><div class="n">{described}</div><div class="label">described by claude</div></div>')
    out.append(f'<div><div class="n">{tbl_n}</div><div class="label">tables</div></div>')
    out.append("</div></section>")

    if a.pictures:
        out.append("<section><h2>Pictures — placeholder vs claude</h2>")
        out.append('<div class="colhead"><div></div>'
                   '<div>today (no judgment layer)</div>'
                   '<div>with brief</div></div>')
        for i, pic in enumerate(a.pictures, 1):
            txt = pic.alt_text.strip()
            klass = "brief"
            if txt.upper() == "DECORATIVE":
                klass += " decorative"
            elif txt.upper().startswith("ERROR"):
                klass += " error"
            img_html = ""
            if pic.image_b64:
                img_html = (
                    f'<img alt="picture {i}" src="data:image/png;base64,{pic.image_b64}">'
                )
            today_text = '"Figure"'
            today_tag = '<span class="tag fail">fails screen reader</span>'
            out.append('<div class="row">')
            out.append(f"<div>{img_html}<div class='meta' style='margin-top:6px'>"
                       f"page {pic.page}</div></div>")
            out.append(f"<div>{today_tag}<div class='today'>{today_text}</div></div>")
            out.append(f"<div><span class='tag win'>described</span>"
                       f"<div class='{klass}'>{_esc(txt)}</div></div>")
            out.append("</div>")
        out.append("</section>")

    if a.tables:
        out.append("<section><h2>Tables — placeholder vs claude</h2>")
        out.append('<div class="colhead"><div></div>'
                   '<div>today (assume row 0 is header)</div>'
                   '<div>with brief</div></div>')
        for i, tbl in enumerate(a.tables, 1):
            hdrs = ", ".join(str(h) for h in tbl.header_rows) or "no header detected"
            today_label = "row 0 (always)"
            brief_label = f"row(s) {hdrs}" if tbl.header_rows else "no header"
            out.append('<div class="row">')
            out.append(
                f"<div><div class='meta'>table {i} · page {tbl.page}<br>"
                f"{tbl.rows}×{tbl.cols}</div></div>"
            )
            out.append(f"<div><span class='tag fail'>structural assumption</span>"
                       f"<div class='today'>{today_label}</div></div>")
            out.append(f"<div><span class='tag win'>content-aware</span>"
                       f"<div class='brief'>{_esc(brief_label)}</div></div>")
            out.append("</div>")
        out.append("</section>")

    out.append("</main>")
    out.append('<footer>brief · c0mpiled-10/DC · 2026-04-24 · '
               'github.com/UmarUzdanov/brief</footer>')
    out.append("</body></html>")
    return "\n".join(out)
