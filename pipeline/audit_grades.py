#!/usr/bin/env python3
"""
Fine-skew audit: independent blind re-classification by a DIFFERENT model (Sonnet), compared to
the Opus grades in recipe_resolution.json. Measures whether "Fine liqueurs" is over-assigned.
Deterministic sampling (no RNG): take the first K of each grade in id order.
"""
import argparse, json, re, threading
from pathlib import Path
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "build" / "site"
KES = Path.home() / "Development/kestrel-admin/public/liquorista/techniques.json"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-grade", type=int, default=16)
    ap.add_argument("--model", default="claude-sonnet-5")
    args = ap.parse_args()

    recs = {r["id"]: r for r in json.load(open(SITE / "recipes.json"))["recipes"]}
    res = json.load(open(SITE / "recipe_resolution.json"))["resolutions"]
    tech = json.load(open(KES))
    classes = [{"cls": r["cls"], "g_l": r["g_l"], "note": r.get("note", "")}
               for r in tech["sweetening_table"]["rows"]]

    # stratified deterministic sample of graded finished liqueurs/spirits
    by_grade = defaultdict(list)
    for r in res:
        if r.get("grade") and r.get("recipe_role") in ("finished_liqueur", "spirit"):
            by_grade[r["grade"]].append(r)
    sample = []
    for g, items in by_grade.items():
        sample += sorted(items, key=lambda r: r["id"])[:args.per_grade]
    print(f"auditing {len(sample)} recipes across {len(by_grade)} grades with {args.model}")

    rules = "\n".join(f"  - {c['cls']}: {c['g_l'][0]}-{c['g_l'][1]} g/L. {c['note']}" for c in classes)
    system = (
        "You are an independent grader classifying 1921 liqueur recipes into ONE sweetening class. "
        "Be discriminating: do NOT default to 'Fine' — distinguish Fine (refined, top-quality, higher "
        "sugar) from Ordinary (simple, rustic, moderate sugar) on the recipe's actual character; use "
        "Ratafias (fruit) for fruit macerations, Rosolios & creams for dense/creamy, Spirits/Double "
        "spirits for little/no sugar. Classes:\n" + rules +
        '\nReturn ONLY {"grade":"<exact cls>","confidence":0-1,"why":"<short>"}.')

    import anthropic
    client = anthropic.Anthropic(max_retries=4)
    lock = threading.Lock(); out = []

    def work(r):
        rr = recs[r["id"]]
        payload = {"title": rr.get("title_en"), "section": rr.get("section_en"),
                   "ingredients": [i.get("name_en") for i in rr.get("ingredients", [])]}
        m = client.messages.create(model=args.model, max_tokens=400,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": json.dumps(payload)}])
        raw = "".join(b.text for b in m.content if getattr(b, "type", None) == "text")
        try: g2 = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))["grade"]
        except Exception: g2 = "PARSE_FAIL"
        with lock: out.append((r["id"], r["grade"], g2))

    with ThreadPoolExecutor(max_workers=6) as ex:
        for f in as_completed([ex.submit(work, r) for r in sample]): f.result()

    agree = sum(1 for _, a, b in out if a == b)
    print(f"\nAGREEMENT: {agree}/{len(out)} ({100*agree/len(out):.0f}%)")
    print("\nOpus grade -> Sonnet grade (disagreements):")
    conf = Counter((a, b) for _, a, b in out if a != b)
    for (a, b), n in conf.most_common():
        print(f"  {n:>2}  {a}  ->  {b}")
    # the key question: Opus-Fine that Sonnet calls something lower
    fine_downgraded = sum(1 for _, a, b in out if a == "Fine liqueurs" and b not in ("Fine liqueurs", "PARSE_FAIL"))
    fine_total = sum(1 for _, a, _ in out if a == "Fine liqueurs")
    print(f"\nFINE-SKEW CHECK: {fine_downgraded}/{fine_total} Opus-'Fine' recipes were re-graded LOWER by {args.model}")
    Path(SITE / "grade_audit.json").write_text(json.dumps(
        [{"id": i, "opus": a, "sonnet": b} for i, a, b in out], ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
