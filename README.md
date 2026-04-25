# pdfua-ac — how the remediation works

A six-stage pipeline that turns an unstructured PDF into a PDF/UA-1 compliant
tagged PDF that passes veraPDF. Each stage is byte-level work on the PDF object
graph; nothing is regenerated from scratch. The pipeline preserves visual
fidelity while building the accessibility tree the original PDF lacks.

Source lives at `/Users/umar/PycharmProjects/PythonProject/` — top-level
`remediate.py`, `structure.py`, `fonts*.py`, `tika.py`.

## Stage 1 — Tika structure extraction (`tika.py`)

HTTP client to a local Apache Tika server (`localhost:9998` by default; override
via `TIKA_URL`).

- `extract_structure(pdf)` → Tika-marked XHTML with class hints
  (`<p class="page">…</p>`, `<table>`, `<h1>` …)
- `extract_metadata(pdf)` → JSON with embedded font names + document language
- **B48 fix**: retry + exponential backoff handles Tika's intermittent OOM on
  large PDFs

Tika is the *semantic oracle* for the pipeline — it answers "what role does
this content play?" Downstream stages take that answer and write it into the
PDF's structure tree.

## Stage 2 — Font pipeline (`fonts.py` + 5 siblings)

The largest part of the codebase. PDFs ship with fonts in many half-broken
states; veraPDF fails on each in a different way. This stage normalizes them.

**Public entry points** (`fonts.py`):
- `embed_fonts()` — embed system fonts referenced but not subset
- `fix_cidtogidmap()` — repair broken CID-to-GID mappings on CID fonts
- `fix_cidset()` — rebuild missing/wrong CIDSets for subsetted fonts
- `fix_preexisting_fonts()` — apply per-font fixes inferred from font tables
- `fix_tounicode()` / `augment_tounicode_coverage()` — repair / extend
  `/ToUnicode` CMaps so screen readers can read the text
- `fix_notdef_glyphs()` / `strip_notdef_operators()` — handle invalid `.notdef`
  glyph references
- `verify_fonts()` — pre-output validation gate
- `fix_widget_tu()` — write `/TU` (UI tooltip) on form widget annotations

**Format coverage**: `.ttf` → `/FontFile2`, `.otf` → `/FontFile3`,
`.ttc` → face extraction.

**Symbol fonts** (`Wingdings`, `ZapfDingbats`, `Symbol`) get *synthesized*
`/ToUnicode` CMaps from a hardcoded table — these fonts have no inherent text
mapping, so the map is invented from glyph-name conventions.

**Sibling modules**:
- `fonts_util.py` — small shared helpers
- `fonts_tables.py` — static lookup tables: standard 14 PDF font metrics,
  glyph-name → Unicode tables, symbol-font conventions
- `fonts_discovery.py` — locate system fonts by name (macOS/Linux paths)
- `fonts_cmap.py` — CMap parsing + emission
- `fonts_program.py` — TrueType / CFF byte-level manipulation via `fontTools`
  (subsetting, table rewriting, `/Widths` recalc per **B62-B63**)

## Stage 3 — Structure builder (`structure.py`)

Walks Tika's XHTML, builds an in-memory `StructNode` tree, then writes it into
the PDF as the `/StructTreeRoot`.

**Tag mapping**: `TIKA_CLASS_MAP` and `TAG_MAP` translate Tika's HTML-ish
classes (`p`, `h1`, `td`, `li`) into PDF/UA standard structure types
(`/P`, `/H1`, `/TD`, `/LI`).

**Per-page MCID allocation (B4)**: Marked Content IDs are page-local. Each page
restarts at MCID 0; the `/ParentTree` indexes by `(page, mcid)`.

**Heading clamping (B5 / B23)**: forces the first heading to `/H1` and clamps
level jumps to `previous + 1` (PDF/UA forbids skipping levels).

**Table structure**: `Table > THead > TR > TH` and `Table > TBody > TR > TD`,
synthesizing missing wrappers. `TH` cells get `/Scope = /Column` by default.

**List structure (B8)**: `L > LI > Lbl + LBody`. `Lbl` nodes deliberately get
**no** MCID — labels are part of the marker, not the content stream.

**Content stream rewriting** (`rewrite_content_streams()`): walks every page's
content stream, wraps every drawing operator in either:
- `/<StructType> << /MCID n >> BDC … EMC` — tagged content
- `/Artifact BMC … EMC` — decorative / non-content

**MCID reconciliation** (`compute_reconciliation()`): if the count of allocated
MCIDs doesn't match the count of `BT` (begin-text) blocks on a page, picks one
of three plans:
- `AlignedPlan` — clean 1:1 map, normal case
- `MaskPlan` — partial alignment, mask the gaps as `/Artifact`
- `FallbackPlan` — **B34**: bail to wrapping the entire page's content as
  `/Artifact` so the PDF still validates structurally even if granular tagging
  is lost

**Form XObject MCIDs (B6)**: stripped, because Form XObject `BT` counts don't
align with the parent page's count.

**Orphan table cells (B64)**: bare `TH` / `TD` / `TR` without a `Table`
ancestor get wrapped in synthetic `Table` / `TR` nodes.

## Stage 4 — Catalog, XMP, annotations (`remediate.py`)

The orchestrator. Calls the previous stages in order and writes catalog-level
metadata.

- `fix_catalog()` — sets `/MarkInfo << /Marked true >>`,
  `/ViewerPreferences << /DisplayDocTitle true >>`, `/Lang` from Tika's detected
  language
- `fix_xmp()` — writes complete XMP packet: `dc:title`, `pdfuaid:part = 1`,
  producer, current `xmp:ModifyDate`, conformance level
- `fix_annotations()` — wires every annotation into the structure tree:
  - `/Link` annotations get `/StructParent` and a structure-element parent
  - Form widgets (`/Subtype /Widget`) get `/TU` from form-field tooltips
  - **B2 fix**: `/Subtype /TrapNet` annotations are deleted (PDF/UA forbids them)
  - **B3 fix**: `/ParentTree` is rebuilt to include every annotation
- `guard_checks()` — final sanity pass: ensures OC `/Name`, file-spec `/F`+`/UF`
  parity, removes XFA, deletes `/Ref` entries that PDF/UA forbids
- `strip_existing_tags()` — first step of every run: wipes any pre-existing
  `/StructTreeRoot`, `/StructParents`, and `BMC` / `BDC` / `EMC` markers from
  the input. Pdfua-ac always builds the tree from scratch — never tries to
  patch a partial existing tree.

## Stage 5 — Output

`pikepdf.save()` with `linearize=False`, deterministic object IDs. Output PDF
contains:
- Full `/StructTreeRoot`
- `/MarkInfo`, `/ViewerPreferences`, `/Lang` on the catalog
- Complete XMP with `pdfuaid:part = 1`
- Embedded fonts with valid `/ToUnicode` for every glyph
- Every visible content operator either tagged or marked `/Artifact`

## Stage 6 — Verification (`demo/verapdf_runner.py`)

Subprocess wrapper around the `verapdf` CLI. Returns a `ScanResult` with
passed/failed rules and per-rule check counts. Used both for pre-flight scans
(diagnose what to fix) and post-flight scans (confirm the fixes worked).

## The B-comment scheme

Every fix in the codebase is tagged with a `B##` identifier (B1–B66+). Each one
references a real veraPDF failure observed on a real DC Courts PDF. The tag in
the code points to:
- The specific PDF that triggered the failure
- The veraPDF rule that flagged it
- The fix applied

Reading any `B##` comment tells you what the surrounding code is defending
against and why deleting that code would re-break a real document.
