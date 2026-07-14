#!/usr/bin/env bash
# Phase 2 driver: translate + structure the whole book with the pilot-chosen split.
#   Prose pages (intro + Parte Prima)  -> Sonnet  (readability matters)
#   Recipe pages (PREPARAZIONI)         -> Haiku   (accurate + cheap at volume)
# Fully resumable: re-running skips pages that already have a checkpoint.
#
# Setup:  export ANTHROPIC_API_KEY=sk-...   &&   pip install anthropic
# Cost preview only:  ./pipeline/run_phase2.sh --dry-run
set -euo pipefail
cd "$(dirname "$0")/.."

PY="$(dirname "$0")/../.venv/bin/python"; [ -x "$PY" ] || PY=python3
SONNET="claude-sonnet-5"
HAIKU="claude-haiku-4-5-20251001"
PROSE_PAGES="12-213"      # introduction + Parte Prima (prose + reference tables)
RECIPE_PAGES="214-715"    # PREPARAZIONI — the ~2000 recipes

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "### PROSE (Sonnet) ###";  "$PY" pipeline/phase2_translate.py --pages "$PROSE_PAGES"  --dry-run
  echo "### RECIPES (Haiku) ###"; "$PY" pipeline/phase2_translate.py --pages "$RECIPE_PAGES" --dry-run
  exit 0
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then echo "Set ANTHROPIC_API_KEY first."; exit 1; fi

CONC="${CONCURRENCY:-8}"
echo ">>> Prose pages on Sonnet (concurrency=$CONC)..."
"$PY" pipeline/phase2_translate.py --pages "$PROSE_PAGES"  --model "$SONNET" --concurrency "$CONC"
echo ">>> Recipe pages on Haiku (concurrency=$CONC)..."
"$PY" pipeline/phase2_translate.py --pages "$RECIPE_PAGES" --model "$HAIKU" --concurrency "$CONC"

echo ">>> Done. Token usage summary:"
python3 - <<'PY'
import json
from pathlib import Path
u = Path("data/usage.jsonl")
if not u.exists(): print("  (no usage logged)"); raise SystemExit
rows = [json.loads(l) for l in u.read_text().splitlines() if l.strip()]
tin = sum(r["in"] for r in rows); tout = sum(r["out"] for r in rows)
print(f"  pages={len(rows)}  input={tin:,} tok  output={tout:,} tok")
PY
echo ">>> Next: review data/recipes/*.json and data/prose/*.md, then Phase 3 (Typst PDF + site)."
