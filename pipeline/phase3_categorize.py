#!/usr/bin/env python3
"""
Normalize 377 raw recipe-section labels into a clean canonical taxonomy.

Robust design: the LLM returns only ~20 canonical categories, each with a blurb and a list
of keyword patterns (small, sturdy JSON). Python then maps every raw label to the first
category whose keyword matches (categories ordered specific->general), else Miscellaneous.
This avoids a fragile 377-key JSON mapping. Output: build/site/taxonomy.json
  { categories:[{name,blurb}], mapping:{raw:canonical} }
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = json.load(open(ROOT / "build" / "site" / "recipes.json", encoding="utf-8"))
OUT = ROOT / "build" / "site" / "taxonomy.json"
raw = [(c["name"], c["count"]) for c in SITE["categories"]]
listing = "\n".join(f"{n!r}: {c}" for n, c in raw)

PROMPT = f"""Organize recipes from a 1900s Italian liqueur manual into a clean web taxonomy.
Below are the raw section labels the extractor produced (label: recipe_count) — noisy and
redundant (e.g. 'Bitters', 'Bitter Liqueurs', 'Amaro (Bitters)' are one thing).

Design a taxonomy of ~15-22 canonical categories a home liqueur-maker would browse by. For
each, give a one-sentence factual blurb and a list of lowercase keyword fragments that appear
in the raw labels belonging to it. ORDER categories from MOST SPECIFIC to most general (e.g.
'Fruit Liqueurs' before 'Liqueurs') so keyword matching assigns the specific one first.

Return ONLY compact JSON (keep blurbs free of double-quote characters):
{{"categories":[{{"name":"Bitters & Amari","blurb":"...","keywords":["bitter","amaro","amari","china"]}}, ...]}}

Raw labels:
{listing}
"""

def main():
    import anthropic
    client = anthropic.Anthropic(max_retries=4)
    with client.messages.stream(model="claude-sonnet-5", max_tokens=32000,
                                messages=[{"role": "user", "content": PROMPT}]) as s:
        msg = s.get_final_message()
    txt = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
    (OUT.parent / "taxonomy_raw.txt").write_text(txt, encoding="utf-8")
    blob = re.search(r"\{.*\}", txt, re.S).group(0)
    cats = json.loads(blob)["categories"]

    # deterministic mapping: first category whose keyword is a substring of the lowercased label
    def classify(label):
        L = (label or "").lower()
        for c in cats:
            for kw in c.get("keywords", []):
                if kw and kw in L:
                    return c["name"]
        return "Miscellaneous"

    mapping = {name: classify(name) for name, _ in raw}
    taxonomy = {
        "categories": [{"name": c["name"], "blurb": c.get("blurb", "")} for c in cats]
                      + [{"name": "Miscellaneous", "blurb": "Assorted preparations that don't fit a single family."}],
        "mapping": mapping,
    }
    OUT.write_text(json.dumps(taxonomy, ensure_ascii=False, indent=1), encoding="utf-8")
    # report distribution
    from collections import Counter
    dist = Counter(mapping[n] for n, c in raw for _ in range(c))
    print(f"Wrote {OUT}: {len(cats)+1} categories")
    for name, cnt in dist.most_common():
        print(f"  {cnt:>4}  {name}")

if __name__ == "__main__":
    main()
