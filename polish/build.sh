#!/usr/bin/env bash
# Regenerate the book from data + polish/corrections.json, then compile to PDF.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="$(dirname "$0")/../.venv/bin/python"; [ -x "$PY" ] || PY=python3
"$PY" pipeline/phase3_build_pdf.py
# --root = project root so figure images under build/figures are reachable from build/pdf/book.typ
if ! typst compile --root "$PWD" build/pdf/book.typ build/pdf/book.pdf; then
  echo "!!! typst compile FAILED" >&2; exit 1
fi
pages=$(pdfinfo build/pdf/book.pdf 2>/dev/null | awk '/Pages:/{print $2}')
echo ">>> built build/pdf/book.pdf ($pages pages)"
