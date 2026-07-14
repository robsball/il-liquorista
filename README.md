# Il Liquorista — English Digital Edition

An English translation and structured digitization of **A. Castoldi, *Il Liquorista*** (Manuali
Hoepli, 1921) — a classic Italian liqueur-making manual ("Duemila ricette e procedimenti
pratici"). Public domain. This repo is the **content & data engine**: it turns the original
scan into a reset English PDF, a structured recipe dataset, and the data feeds a website consumes.

## What's here

| Deliverable | Path |
|---|---|
| Reset English **PDF** (~1,043 pp, illustrated) | `build/pdf/book.pdf` |
| **1,497 structured recipes** | `build/site/recipes.json` |
| **Inherited-knowledge resolution** (sweetening/dilution by grade, type-aware, calibrated) | `build/site/recipe_resolution.json` |
| **Variant groups** (same liqueur, different methods) | `build/site/variants.json` |
| **Techniques taxonomy** helper | `build/site/taxonomy.json` |
| Preserved **illustrations** (cropped/oriented engravings) | `build/figures/` |
| Original source scan (public domain) | `A. Castoldi - Il Liquorista.pdf` |

## Pipeline (`pipeline/`)
- `phase0_extract.py` — extract text layer + profile every page
- `phase2_translate.py` / `run_phase2.sh` — translate + structure (Sonnet prose / Haiku recipes)
- `phase2b_vision.py` — vision transcription for dense numeric tables
- `phase_r_resolve.py` / `_finalize.py` / `_calibrate.py` — grade-classify + resolve inherited sweetening
- `phase_r1_extract.py` — rescue recipes trapped in prose
- `phase_variants.py` — link variant groups
- `phase_figures.py` / `_vision.py` — detect, crop, orient, caption illustrations
- `phase3_build_pdf.py` / `phase3_build_site.py` — generate the PDF and site data
- `audit_grades.py`, `phase_index_parse.py` — QA / index reconciliation

Details in [`PROJECT.md`](PROJECT.md) and [`docs/RECIPE_RESOLUTION_DESIGN.md`](docs/RECIPE_RESOLUTION_DESIGN.md).

## Build

```bash
python3 -m venv .venv && .venv/bin/pip install anthropic Pillow numpy
export ANTHROPIC_API_KEY=sk-...      # only needed to (re)run translation/resolution
polish/build.sh                      # regenerate build/pdf/book.pdf from data/ + corrections
```

The **PDF polish system** (systematic fixes + a hand-fix overlay) is documented in
[`polish/README.md`](polish/README.md). Requires `typst` and Poppler (`pdftoppm`, `pdftotext`).

## Website

`build/site/` holds the data feeds (canonical) and a self-contained static site shell.
The **live website UI** is currently deployed inside the `kestrel-admin` app
(`public/liquorista/`), where a separate agent maintains the UI + a curated `techniques.json`.
The feeds published here are host-portable (recipe-id keyed) and can move to any host.
Reconciling the repo's site shell with the evolved kestrel UI is a pending decision.

## License / rights
The original work is **public domain** (author Castoldi d. 1910; pre-1929 publication).
Pipeline code © this project.
