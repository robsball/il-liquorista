# Corpus-Wide Recipe Resolution — Design

*Owner: the Il-Liquorista data pipeline. Consumer: the kestrel-admin Liqueurist site.*
*Status: DESIGN (not yet implemented). Created 2026-07-09.*

## 0. Purpose in one paragraph

Make every recipe in *Il Liquorista* **stand on its own** by (a) capturing the ~500 recipes
currently trapped as unstructured prose, and (b) resolving the book's *inherited* knowledge —
sweetening, dilution-to-strength, finishing, and cross-references — into structured,
provenance-tagged data. The output is a **one-directional data feed** the kestrel-admin site
consumes. We generate data; the site owns presentation.

## 1. Context & the two-agent split

Two agents now work this corpus. To avoid divergent sources of truth, we split by **layer**:

| Concern | Owner | Artifact |
|---|---|---|
| Curated "teachings" (rules, base formulas, technique articles) | **kestrel agent** | `public/liquorista/techniques.json` |
| Site UI, recipe pages, the "Where's the sugar?" panel | **kestrel agent** | `app.js`, `styles.css` |
| **Corpus-wide recipe data: completeness + per-recipe resolution** | **this pipeline** | `recipes.json` (v2) + new `recipe_resolution.json` + `ingredient_index.json` |

Inputs we consume (read-only) from the kestrel agent's work:
- `techniques.json` — **vocabulary source of truth.** Use its class names verbatim
  (`Spirits (eaux-de-vie)`, `Double spirits`, `Ordinary liqueurs`, `Fine liqueurs`,
  `Ratafias (fruit)`, `Rosolios & creams`), its `sweetening_table.rows[].g_l` ranges, its
  `syrup` formula, and its topic `slug`s for method→technique links.
- `docs/LIQUORISTA_REVIEW.md` — the overnight full-book audit. Authoritative on structure,
  page constants, and the cross-reference trap. This design builds on it.

## 2. Principles (non-negotiable)

1. **Derive, never fabricate.** We never silently insert sugar. We *derive* inherited
   elements from the book's own stated rules and mark them `derived: true` with a `source`
   and a `confidence`. A liqueur missing sugar gets `inherited.sweetening` computed from its
   grade class — labeled, sourced, editable — not an invented ingredient row.
2. **Provenance on everything.** Every resolved field carries the page(s) and rule it came
   from. If we can't source it, we don't assert it.
3. **Data, not presentation.** We emit values and confidences; the site decides how to show
   them. We do **not** duplicate the site's scaling/panel logic.
4. **Respect the pagination trap.** Per LIQUORISTA_REVIEW §3, in-text `(See p. X)` refs use
   the *original Italian edition's* numbers and are **not resolvable** — do not link them.
   Only **relative** cross-refs (`as above`, `like the preceding`, `in the same way`) are
   resolvable, and only to the immediately-preceding sibling recipe.
5. **Additive & reversible.** Never overwrite `recipes.json` in place without a backup;
   every phase writes to a namespace and is diffable. Confidence-scored, human-reviewable.

## 3. Grounded gap analysis (from our data + the review)

- **1,431** recipes structured (`data/recipes/`), pages tagged 214–715 (Italian source PDF).
- **114** pages in the recipe range went to `data/prose/` instead of structured recipes
  (~198k chars); ~26 are recipe-dense essence-blend pages → **est. ~450–550 recipes trapped**.
  Matches the review's "~550–620 uncaptured (second collection)."
- **858 / 1,431 (60%)** list no sugar/syrup — the inheritance problem, by grade class.
- Cross-refs in recipe notes: ~18 *relative* (`as above` ×11, etc.) — resolvable; an unknown
  number of *absolute* `(See p. X)` — **not** resolvable (trap).
- OCR-damaged pages flagged by the review: 418 (page lost), 923–925, 68, 70; plus ~15
  ingredient-only stubs and the blank Rosolio row in the p.220 table.

### Page-numbering reconciliation (prerequisite)
Our data uses **Italian source PDF** page numbers (1–734). `techniques.json` and the review
use **English edition** page numbers (`book.pdf`, 1–1043). Provenance links must be
unambiguous. **R0 produces a `page_map.json`** (Italian source page → English PDF page range),
generated during `phase3_build_pdf` (it already walks pages in order). Recipes keep their
Italian `page`; resolution records add `page_en` for links into the hosted PDF.

## 4. Output artifacts (the contract)

### 4.1 `recipes.json` v2 (extended, backward-compatible)
Existing fields unchanged. Added per recipe:
- `grade` — one of the `sweetening_table` classes, or `null` (R2).
- `page_en` — English-edition page for PDF deep-links (R0).
- `xref` — `{type: "relative"|"absolute", raw, resolved_id?}` when a recipe references another.
- `ingredients[].name_key` — normalized ingredient key for the index (R5).
- New recipes from R1 appended with `source: "prose-extraction"` and a confidence.

### 4.2 `recipe_resolution.json` (new — the core deliverable)
One record per recipe id:
```json
{
  "id": "amaro-alla-china",
  "grade": "Fine liqueurs",
  "inherited": {
    "sweetening": { "g_per_l": [175, 325], "derived": true,
      "source": {"rule": "dosage-table", "page_en": 220, "slug": "sweetening"},
      "confidence": 0.8, "note": "range for the Fine class; adjust to taste" },
    "dilution":   { "to_degrees": 40, "derived": true, "source": {...}, "confidence": 0.6 },
    "finishing":  ["clarify", "rest 2–3 days", "age"]   // technique slugs, derived
  },
  "derived_from": null,          // parent recipe id if this is an "as above" child
  "method_slug": "maceration",   // link into techniques.json topics
  "flags": ["ocr-stub"]          // quality signals for the site to badge
}
```
The site already computes a sugar panel from `techniques.json` + yield; this feed makes that
resolution **durable, queryable, and consistent even when yield is unknown** (grade-inferred),
and adds dilution/finishing/cross-ref that the UI panel doesn't cover.

### 4.3 `ingredient_index.json` (new — enables the ingredient index feature)
`{ name_key: { display, recipe_ids: [...], count } }` after R5 normalization.

## 5. Phased plan (the "lot of work")

Each phase is independently shippable, backed up, and confidence-scored. Run a **vertical
slice first** (see §7).

| Phase | Work | Model | Notes |
|---|---|---|---|
| **R0** | Page-map (IT↔EN); wire `page_en` | none (deterministic) | prerequisite for provenance |
| **R1** | Extract ~500 trapped recipes from the 114 prose pages → structured, merge | **Sonnet** (vision on dense pages) | biggest chunk; reuse `phase2b_vision` pattern |
| **R2** | Classify each recipe → `grade` class (map to `sweetening_table`) | **Opus** batch | reasoning: quality class from name/ingredients/section |
| **R3** | Resolve `inherited{}` (sweetening/dilution/finishing) w/ provenance + confidence | **Opus** | derives from techniques.json rules; the honesty-critical step |
| **R4** | Resolve **relative** cross-refs → `derived_from`, inherit parent's ingredients | **Opus** | ignore absolute `(See p.X)` refs (trap) |
| **R5** | Ingredient-name normalization + `ingredient_index.json` | **Haiku**→**Opus** verify | `Alcool di 85°`≈`Alcohol 85°`; enables index/search |
| **R6** | Data-quality fixes: OCR-damaged pages 418/923–925/68/70, stubs | **Sonnet** vision | targeted, small |

Cross-cutting: every phase writes `*_pre_<phase>/` backups, logs confidence, and emits a
human-reviewable diff summary. Prompt-cache the fixed schema/rules prefix (repeated per call).

## 6. Model & cost strategy

- **Breadth extraction (R1, R6):** Sonnet vision — numeric/name fidelity on dense pages.
- **Reasoning (R2–R4):** Opus — grade classification and faithful inheritance are high-stakes,
  low-volume; this is where correctness matters most.
- **Mechanical (R5 first pass):** Haiku, Opus-verified.
- **Efficiency:** prompt caching on the rules prefix (~2k tokens × hundreds of calls);
  reuse rendered page images; `--max-tokens` generous + streaming (learned gotcha: Sonnet's
  default thinking silently eats the budget → empty responses).
- **Rough estimate:** R1 ~$4–6 (500 recipes, vision), R2–R4 ~$6–10 (Opus over 1,900 recipes),
  R5–R6 ~$2. **Total order ~$15–20.** Confirm against a slice before committing.

## 7. Vertical slice first (strongly recommended)

Before the full corpus: take **Liqueurs** (the worst missing-sugar case) end to end —
R2 classify + R3 resolve for that category only — and hand the kestrel agent a sample
`recipe_resolution.json` covering it. Validate that the completed view reads *right and
honest* on the site, that the vocabulary matches `techniques.json`, and that the data contract
works, before scaling to all 23 categories and running the expensive R1 extraction.

## 8. Interface contract with the kestrel agent

- We publish `recipe_resolution.json`, `ingredient_index.json`, and `recipes.json` v2 into
  `public/liquorista/` (or a location they specify). **One-directional**: they read, we write.
- We treat `techniques.json` as read-only vocabulary; if we need a class/slug that doesn't
  exist, we **request** it from the kestrel agent rather than inventing one.
- Versioning: each feed carries `meta.generated` + `meta.schema_version`; changes are additive.
- The site keeps owning all UI (the sugar panel, technique pages, scaler). We only enrich data.

## 9. Non-goals / risks

- **Not** rebuilding techniques/base formulas — the kestrel agent owns that curated layer.
- **Not** resolving absolute `(See p. X)` cross-refs (pagination trap).
- **Not** fabricating any ingredient or quantity the book doesn't state or imply by rule.
- Risk: grade misclassification propagates wrong sweetening → mitigate with confidence
  thresholds + the vertical-slice validation + human-reviewable diffs.
- Risk: two agents editing `public/liquorista/` → mitigate via the one-directional contract
  and distinct filenames (we never touch `techniques.json`/`app.js`).

## 10. Decisions (resolved 2026-07-09)

1. **Vertical slice = Liqueurs**, then fan out & generalize the same machine to all categories.
2. **Endgame = public**, intended as a gift to the botanist/liqueur community. → **Build to a
   very high bar from the start.** Every derived value must be sourced, confidence-scored, and
   honest; provenance is a feature, not an afterthought.
3. **Feeds live in `public/liquorista/`** — BUT must be **host-portable**: recipe-id references
   only, no absolute paths/hosts, self-contained relative links, so the whole `liquorista/`
   folder can be lifted to a different host unchanged. (Current location is temporary.)
4. **Link second-collection duplicates as VARIANTS** — a first-class feature, not a merge.
   Schema: a recipe gains `variant_of` (canonical recipe id) + `variant_kind` (e.g.
   `"by distillation"` / `"by essence"`); the canonical recipe exposes `variants: [ids]`.
   Full linking needs the R1-extracted second collection; the field is defined now and
   populated during fan-out.
