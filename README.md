# brief

A judgment layer for PDF accessibility.

Docling extracts structure (pictures with bounding boxes, tables with cells,
hyperlinks with surrounding context). Claude reads the extracted items and
produces metadata that screen readers can actually use: figure descriptions,
table header detection, link purpose text, form-field labels by proximity.

The PDF/UA spec has 136 failure conditions. About 89 are machine-checkable
(structure, fonts, metadata) — those are solved by existing tooling. The
remaining 47 require human judgment. brief is a swing at that 47.

Built at c0mpiled-10/DC, 2026-04-24.

## Run

```sh
uv sync
uv run brief extract path/to/file.pdf
```

## Layout

- `src/brief/extract.py` — Docling extraction; surfaces pictures, tables, links with bboxes
- `src/brief/cli.py` — CLI entrypoint (`brief extract`, more to come)

## Next

- `src/brief/judge.py` — Claude vision pass on extracted PictureItems
- `src/brief/tables.py` — header-row detection
- `src/brief/links.py` — context-aware link purpose text
