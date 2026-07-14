# Il Liquorista — Translation & Recipe Digitization

Translating **A. Castoldi, _Il Liquorista_** (Hoepli; "Duemila ricette e procedimenti
pratici") from Italian to English, producing (1) a reset English **PDF** and (2) a
**JSON recipe dataset** powering a website with dynamic quantity scaling.

Source: `A. Castoldi - Il Liquorista.pdf` — 734 pp, A4, image-based **but carries an
extractable OCR text layer** (~1.95M chars). Private use. Recipes are uncopyrightable
facts; surrounding prose is treated as copyrighted (US public domain; EU status unclear).

## Guiding principle — minimal LLM tokens
Push every step to free local tooling; spend tokens only on the irreducible LLM work
(translate + clean OCR + structure), done in **one combined pass per chunk**, checkpointed
per page so re-runs touch only changed pages. Reserve Opus for QA/hard passages; run bulk
prose on a cheaper tier (Haiku/Sonnet).

## Book structure (from Phase 0 structure map)
| Section | Pages | Handling |
|---|---|---|
| Front matter + INDICE GENERALE | 1–11 | Skip/optional; index = free recipe map |
| INTRODUZIONE | 12–21 | Prose (text path) |
| PARTE PRIMA (materials, oils, drugs, weights & measures) | 22–213 | Prose + hard numeric tables |
| Alcoholometer / weights numeric tables | ~51–84, 199–210 | **Image path** — OCR garbled; numbers are physics, only headers translate |
| PREPARAZIONI (the ~2,000 recipes) | 214–715 | Core — text path → structured JSON |
| INDICE ALFABETICO | 716–734 | Regenerate from JSON |
| Empty / image-only pages | 2,3,5,11,22,23,70,211,212,213,307,308,309,715,734 | OCR with `tesseract -l ita` |

## Recipe shape (observed)
Recipes are grouped under section headers; each = **title + ingredient rows** with dotted
leaders and one-or-more **quantity columns** (multiple columns = variant proportions).
**Units are frequently implicit**, set by section convention (e.g. "essences by weight in
grams, or by drops") — so structuring requires the LLM, not regex.

## Next phase — corpus-wide recipe resolution
See [docs/RECIPE_RESOLUTION_DESIGN.md](docs/RECIPE_RESOLUTION_DESIGN.md). The site now lives in
`kestrel-admin` (a separate agent owns it + a curated `techniques.json` knowledge layer). This
pipeline owns making every recipe stand alone: extract the ~500 recipes trapped in `data/prose`,
and resolve inherited sweetening/dilution/cross-refs into a `recipe_resolution.json` data feed
the site consumes. One-directional; derive-not-fabricate.

## Pipeline stages
- **Phase 0** — Local extraction + structure map. `pipeline/phase0_extract.py` → `data/`.
- **Phase 1** — Pilot: translate+structure representative pages, measure tokens, lock schema/model.
- **Phase 2** — Full batch translate+structure (resumable) → `data/recipes/*.json` + `data/prose/*.md`.
- **Phase 3** — Typst → English PDF; static site over JSON with dynamic scaling.

## Layout
```
pipeline/            scripts (extraction, batch engine, typeset, site build)
data/pages_layout/   per-page layout-preserved IT text (p####.txt)  [Phase 0 output]
data/structure_map.json, structure_summary.txt                      [Phase 0 output]
data/recipes/        structured recipe JSON                          [Phase 2 output]
data/prose/          translated prose markdown                       [Phase 2 output]
build/pdf/  build/site/                                              [Phase 3 output]
```
