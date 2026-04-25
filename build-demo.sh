#!/usr/bin/env bash
# Build the demo HTML.
#
# Pipeline:
#   1. pdfua-ac  remediates every PDF in src/brief/cogent-binaries/ ->
#      src/brief/cogent-binaries_remediated/  (PDF/UA-1 tagged output).
#   2. verapdf-diff.py  validates both folders against the PDF/UA-1 profile
#      and emits an HTML report comparing before vs after.
#
# Output: ./demo.html
#
# Usage:
#   ./build-demo.sh           # default profile = ua1
#   ./build-demo.sh wcag      # any verapdf-diff profile alias

set -euo pipefail

PROFILE="${1:-ua1}"

ROOT="$(cd "$(dirname "$0")" && pwd)"
BEFORE="$ROOT/src/brief/cogent-binaries"
AFTER="$ROOT/src/brief/cogent-binaries_remediated"
OUT="$ROOT/demo.html"

PDFUA_PROJECT="/Users/umar/PycharmProjects/PythonProject"

echo "[1/2] pdfua-ac remediation: $BEFORE"
cd "$ROOT/src/brief"
uv run --project "$PDFUA_PROJECT" pdfua-ac cogent-binaries

echo "[2/2] verapdf-diff (--profile $PROFILE): -> $OUT"
cd "$ROOT"
uv run verapdf-diff.py "$BEFORE" "$AFTER" --profile "$PROFILE" --output "$OUT"

echo "done: $OUT"
