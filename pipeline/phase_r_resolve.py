#!/usr/bin/env python3
"""
Phase R (slice) — Grade-classify + resolve inherited sweetening for recipes, using the
kestrel agent's techniques.json as the RULE SOURCE (so vocabulary matches the site).

Output: build/site/recipe_resolution.json  (host-portable: recipe-id keyed, no paths/hosts).
Derive-not-fabricate: every inherited value carries source + confidence + derived:true.

Usage: python3 pipeline/phase_r_resolve.py --category "Compound & Generic Liqueurs" --limit 10
Requires ANTHROPIC_API_KEY.
"""
import argparse, json, re, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "build" / "site"
KES_TECH = Path.home() / "Development/kestrel-admin/public/liquorista/techniques.json"
OUT = SITE / "recipe_resolution.json"
CKPT = ROOT / "data" / "resolution_ckpt"
CKPT.mkdir(parents=True, exist_ok=True)

def load_rules():
    t = json.load(open(KES_TECH, encoding="utf-8"))
    classes = [{"cls": r["cls"], "g_l": r["g_l"], "note": r.get("note", "")}
               for r in t["sweetening_table"]["rows"]]
    slugs = [top["slug"] for top in t.get("topics", [])]
    return {
        "sweetening_classes": classes,
        "sweetening_refs": t["sweetening_table"].get("refs", ""),
        "syrup": t.get("syrup", {}),
        "technique_slugs": slugs,
    }

SYSTEM_TMPL = """You are resolving the INHERITED knowledge a 1921 manual (Il Liquorista) assumes
but omits from individual recipes, so each recipe can stand on its own. The manual mixes several
kinds of recipe, and they must be treated DIFFERENTLY — applying a sweetening dosage to an essence
or a colorant would be WRONG.

STEP 1 — classify each recipe's ROLE:
- "finished_liqueur": a sweetened liqueur meant to drink (gets an inherited sweetening grade).
- "spirit": eau-de-vie / brandy/rum/gin imitation / absinthe — little or NO sugar (grade =
  "Spirits (eaux-de-vie)" or "Double spirits"; sweetening usually minimal).
- "flavoring_base": essence, essential oil, aromatized-spirit base, tincture/alcoholate,
  compound-essence — NOT sweetened; it is dosed INTO other liqueurs. No sweetening grade.
- "colorant": a coloring/dye preparation. No sweetening.
- "aromatic_water": distilled/aromatic water — usually a base; no inherited sweetening unless clearly a drink.
- "syrup": the recipe IS sugar syrup; sweetening is intrinsic, not inherited.
- "wine_aromatized": vermouth / aromatized wine — wine-based; different regime (do NOT apply the liqueur table).
- "punch": punch/grog — assembled to serve; no inherited liqueur sweetening.
- "other": anything that fits none of the above.

STEP 2 — resolve ONLY what the role warrants:
- finished_liqueur (and, lightly, spirit): assign a grade class and DERIVE sweetening from the table.
- flavoring_base / colorant / syrup / aromatic_water / wine_aromatized / punch: sweetening = null.
  Instead give a `usage_note`: how the base is used or dosed (e.g. "dose ~1 kg per 40-50 L of liqueur",
  "used to tint liqueurs", "sweetened intrinsically"). This is how a base recipe stands alone.

THE BOOK'S RULES (authoritative — cite, never contradict, never invent a number):
Sweetening dosage by grade class (g sugar / litre of finished liqueur), refs {refs}:
{classes}
Standard syrup: {syrup}
Technique slugs (method/finishing links): {slugs}

Return ONE JSON array, same order as input, each object:
{{
 "id": "<unchanged>",
 "recipe_role": "<one of the roles above>",
 "grade": "<exact class 'cls' string, or null if role isn't a sweetened liqueur>",
 "inherited": {{
   "sweetening": {{"g_per_l": [lo, hi], "derived": true,
       "source": {{"rule": "dosage-table", "page_en": 220, "class": "<cls>"}},
       "confidence": 0.0-1.0, "note": "<short>"}}   OR null,
   "dilution": {{"to_degrees": <int|null>, "derived": true, "confidence": 0.0-1.0}} OR null,
   "finishing": ["<technique slug>", ...]
 }},
 "usage_note": "<for bases/spirits/etc: role & dosage; else empty>",
 "method_slug": "<slug or null>",
 "already_sweetened": <true if the recipe ALREADY lists sugar/syrup>,
 "rationale": "<one sentence>"
}}

Conduct: classify grade from character (refined aromatic -> Fine; simple/rustic -> Ordinary; fruit
maceration -> Ratafias (fruit); dense/creamy -> Rosolios & creams; spirit imitation -> Spirits/Double
spirits). Honest, calibrated confidence. This dataset is PUBLIC — never assert what you can't defend."""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="Compound & Generic Liqueurs")
    ap.add_argument("--all", action="store_true", help="resolve ALL recipes not already in the feed")
    ap.add_argument("--ids", default="", help="comma-separated recipe ids (overrides category)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    recs = json.load(open(SITE / "recipes.json"))["recipes"]
    mp = json.load(open(SITE / "taxonomy.json"))["mapping"]
    canon = lambda r: mp.get(r.get("section_en") or "", r.get("section_en") or "") or "Miscellaneous"
    already = set()
    if OUT.exists():
        already = {r["id"] for r in json.load(open(OUT)).get("resolutions", [])}
    if args.ids:
        want = set(args.ids.split(",")); sel = [r for r in recs if r["id"] in want]
    elif args.all:
        sel = [r for r in recs if r["id"] not in already]
    else:
        sel = [r for r in recs if canon(r) == args.category]
    if args.limit: sel = sel[:args.limit]
    scope = "ALL remaining" if args.all else args.category
    print(f"resolving {len(sel)} recipes ({scope}), skipping {len(already)} already done, batches of {args.batch}")

    rules = load_rules()
    system = SYSTEM_TMPL.format(
        refs=rules["sweetening_refs"],
        classes="\n".join(f"  - {c['cls']}: {c['g_l'][0]}-{c['g_l'][1]} g/L. {c['note']}" for c in rules["sweetening_classes"]),
        syrup=rules["syrup"].get("formula", ""),
        slugs=", ".join(rules["technique_slugs"]))

    def slim(r):  # only what the model needs (token economy)
        return {"id": r["id"], "title_en": r.get("title_en"), "section_en": r.get("section_en"),
                "method": r.get("method"),
                "ingredients": [i.get("name_en") for i in r.get("ingredients", [])],
                "already_has_sugar": any("sugar" in (i.get("name_en") or "").lower()
                                         or "syrup" in (i.get("name_en") or "").lower()
                                         for i in r.get("ingredients", []))}

    batches = [sel[i:i+args.batch] for i in range(0, len(sel), args.batch)]
    import anthropic
    client = anthropic.Anthropic(max_retries=4)
    lock = threading.Lock(); results = {}

    import hashlib
    def work(bi, batch):
        # content-addressed checkpoint (model + recipe ids) — safe across runs, no index collision
        key = hashlib.md5((args.model + "|" + ",".join(r["id"] for r in batch)).encode()).hexdigest()[:12]
        ck = CKPT / f"b_{key}.json"
        if ck.exists():
            return json.load(open(ck))
        payload = json.dumps([slim(r) for r in batch], ensure_ascii=False)
        with client.messages.stream(
            model=args.model, max_tokens=16000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Resolve these recipes:\n{payload}"}]) as s:
            msg = s.get_final_message()
        raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        blob = re.search(r"\[.*\]", raw, re.S).group(0)
        blob = re.sub(r",(\s*[}\]])", r"\1", blob)   # tolerate trailing commas from the model
        arr = json.loads(blob)
        ck.write_text(json.dumps(arr, ensure_ascii=False), encoding="utf-8")
        u = msg.usage
        with lock:
            with (ROOT / "data" / "resolve_usage.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"batch": bi, "model": args.model, "in": u.input_tokens,
                    "out": u.output_tokens, "cache_read": getattr(u, "cache_read_input_tokens", 0),
                    "cache_write": getattr(u, "cache_creation_input_tokens", 0)}) + "\n")
            print(f"  batch {bi}: {len(arr)} resolved (out {u.output_tokens} tok, cache {getattr(u,'cache_read_input_tokens',0)} read)", flush=True)
        return arr

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(work, i, b): i for i, b in enumerate(batches)}
        for f in as_completed(futs):
            for rec in f.result():
                results[rec["id"]] = rec

    feed = {"meta": {"generated": "2026-07-09", "schema_version": 1,
                     "scope": args.category, "count": len(results),
                     "rule_source": "techniques.json sweetening_table",
                     "portable": "recipe-id keyed; no host/path deps"},
            "resolutions": list(results.values())}
    # merge with any existing feed (fan-out will accumulate)
    if OUT.exists():
        prev = {r["id"]: r for r in json.load(open(OUT)).get("resolutions", [])}
        prev.update(results); feed["resolutions"] = list(prev.values()); feed["meta"]["count"] = len(prev)
    OUT.write_text(json.dumps(feed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUT}: {feed['meta']['count']} resolutions")

if __name__ == "__main__":
    main()
