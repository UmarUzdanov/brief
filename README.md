# brief

A judgment layer for PDF accessibility.

Docling extracts structure — pictures with bounding boxes, tables with cells,
hyperlinks with surrounding context. Claude reads what Docling found and
produces metadata that screen readers can actually use: figure descriptions,
content-aware table header detection, in-context link purpose text.

The PDF/UA spec has 136 failure conditions. About 89 are machine-checkable
(structure, fonts, metadata) — those are solved by existing tooling. The
remaining 47 need human judgment. brief is a swing at that 47, executed at
the c0mpiled-10/DC hackathon (Apr 24, 2026).

## Status

End-to-end pipeline running on real PDFs. Four of the deck's five judgment
dimensions wired:

| Dimension | Status |
| --- | --- |
| Figure alt-text | ✅ live (claude vision) |
| Table header detection | ✅ live (multi-row support) |
| Link purpose text | ✅ live |
| Reading-order check | ✅ live (`brief order <pdf>`, standalone) |
| Form-field labels | ⏳ next |

## Demos

Self-contained HTML reports — open in any browser, no server needed. View
on htmlpreview.github.io for direct rendering, or clone and open locally.

| File | PDF | Numbers |
| --- | --- | --- |
| [`demo.html`](https://htmlpreview.github.io/?https://github.com/UmarUzdanov/brief/blob/main/demo.html) | Cogent Q4-05 earnings release (9 pages) | 1 picture described, **7 tables — 4 with multi-row headers, one with 6 header rows** |
| [`demo-ir.html`](https://htmlpreview.github.io/?https://github.com/UmarUzdanov/brief/blob/main/demo-ir.html) | Cogent IR Presentation 4Q25 (25 pages) | **42/42 pictures described**, 0 decorative, 0 errors; 6 tables, 2 multi-row |

The "4 of 7 multi-row headers" and "42/42 described" are the pitch numbers:
they're what a "first row is header" rule and a "Figure" placeholder fail to
produce, on real SEC-filed PDFs.

## Auth

Calls go through `claude -p` (Claude Code Pro/Max subscription) — no API key
needed. The `claude` CLI must be on PATH and logged in.

## Install

```sh
uv sync
```

## Commands

```sh
# 1. Just the Docling pass — see what was extracted, no Claude calls.
uv run brief extract <pdf>

# 2. Single-image alt-text — smallest possible demo surface.
uv run brief alt <image.png>

# 3. Full augment — Claude over each picture, table, and link. JSON out.
uv run brief augment <pdf> --out augment.json --with-images

# 4. Augment + render to a self-contained HTML report.
uv run brief report <pdf> --out report.html --save-json augment.json

# 5. Re-render HTML from a saved JSON (no Claude calls).
uv run brief render augment.json --out report.html
```

## Architecture

```
PDF
 │
 ▼
Docling (DocumentConverter)               extracts structure + image bboxes
 │
 ▼
brief.augment.augment()                   orchestration
 │   ├── for each PictureItem:
 │   │     crop image → claude -p (vision) → alt_text
 │   ├── for each TableItem:
 │   │     build cell grid → claude -p → header rows (multi-row aware)
 │   └── for each hyperlink:
 │         text + context + URL → claude -p → suggested purpose text
 │
 ▼
brief.report.render()                     side-by-side HTML
 │                                        (placeholder vs claude, embedded PNGs)
 ▼
report.html
```

## Layout

```
src/brief/
  extract.py    Docling-only pass; for sniffing what's in a PDF
  judge.py      three single-purpose `claude -p` callers (alt/headers/links)
  links.py      hyperlink collection from a Docling document
  augment.py    orchestration: extract + judge per item
  report.py     HTML renderer (navy/ice palette, side-by-side layout)
  cli.py        click commands
tests/          17 unit tests for parsers and helpers (no Claude required)
```

## Tests

```sh
uv run pytest -q
```

17 passing. None of them call Claude or load Docling models.

## License

Built tonight. License TBD.
