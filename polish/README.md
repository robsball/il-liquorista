# PDF Polish System

The book PDF is **generated from data** (`data/prose/*.md` + `data/recipes/*.json`) by
`pipeline/phase3_build_pdf.py`. So edits made directly to `book.typ`/`book.pdf` are lost on
the next rebuild. Polish therefore lives in two durable layers:

1. **Systematic fixes** — baked into the generator; fix whole classes of issues at once.
2. **Hand-fix overlay** — `polish/corrections.json`; targets specific pages/tables and
   survives regeneration.

## Workflow

```bash
python3 polish/review.py --sample 30     # render 30 spread pages to polish/review/
python3 polish/review.py 74 92 305       # or specific pages
#  ...eyeball polish/review/*.png, find an issue on a page...
#  ...add a fix to polish/corrections.json (see below)...
polish/build.sh                          # regenerate + compile
python3 polish/review.py 305             # re-check that page
```

The page numbers in `corrections.json` are **source pages** (the `pNNNN` from
`data/prose/`, shown in each page's `<!-- source page N -->` comment), NOT final PDF pages —
so fixes stay valid even as pagination shifts.

## Systematic fixes already in the generator
- **Markdown emphasis** → real Typst italic/bold (Latin names italic, term headers bold) —
  no more literal `*asterisks*`.
- **Spacing cleanup** — space-before-punctuation, `85 °`→`85°`, `l ' amido`→`l'amido`,
  collapsed double spaces.
- **Stripped running headers** — OCR-captured `Il Liquorista — N` / `Manuale del liquorista`
  lines removed from the text flow.
- **Tables** — repeating header row across page breaks, bold headers, per-column numeric
  right-alignment, clean horizontal hairlines (no heavy grid), font auto-scaled by width.

## Hand-fix overlay — `polish/corrections.json`

### Text fix
```json
{ "find": "teh", "replace": "the", "scope": "all" }
{ "find": "\\bcl\\b", "replace": "cL", "scope": "page:250", "regex": true }
```
`scope` is `all` (default) or `page:NNN` (source page). `regex:true` uses Python `re`
(backreferences `\1`).

### Table override
Key by source page `pNNNN` (all tables on the page) or `pNNNN:INDEX` (0-based table on the page):
```json
"table_overrides": {
  "p0067": { "landscape": true, "font_pt": 6 }
}
```
- `landscape` — put this (very wide) table on its own rotated page.
- `font_pt` — override the auto font size.

## Files
- `pipeline/phase3_build_pdf.py` — the generator (systematic fixes live here).
- `polish/corrections.json` — the hand-fix overlay.
- `polish/build.sh` — regenerate + compile.
- `polish/review.py` — render pages to `polish/review/` for inspection.
