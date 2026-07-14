#!/usr/bin/env python3
"""
Phase 3 (site) — consolidate structured recipes into a single web dataset.

Reads   data/recipes/p####.json
Writes  build/site/recipes.json   { meta, categories:[{name,count}], recipes:[...] }
The static site (index.html + app.js) reads this file; dynamic scaling works because
every ingredient carries qty + unit.
"""
import json, re, glob
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "site" / "recipes.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-") or "recipe"

def main():
    recipes, seen = [], {}
    for f in sorted(glob.glob(str(ROOT / "data" / "recipes" / "p*.json"))):
        try: page_recipes = json.load(open(f, encoding="utf-8"))
        except Exception: continue
        for r in page_recipes:
            if not r.get("title_en"): continue
            rid = r.get("id") or slug(r["title_en"])
            seen[rid] = seen.get(rid, 0) + 1
            if seen[rid] > 1: rid = f"{rid}-{seen[rid]}"   # disambiguate duplicate titles
            r["id"] = rid
            r.setdefault("section_en", "Miscellaneous")
            recipes.append(r)
    cats = Counter(r["section_en"] for r in recipes)
    categories = [{"name": n, "count": c} for n, c in sorted(cats.items(), key=lambda x: -x[1])]
    data = {
        "meta": {
            "title": "The Liqueurist",
            "subtitle": "Two Thousand Recipes and Practical Procedures",
            "author": "Dott. A. Castoldi",
            "source": "Manuale Hoepli, 1921 — public domain",
            "recipe_count": len(recipes),
        },
        "categories": categories,
        "recipes": recipes,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT}: {len(recipes)} recipes, {len(categories)} categories")
    print("Top categories:")
    for c in categories[:20]:
        print(f"  {c['count']:>4}  {c['name']}")

if __name__ == "__main__":
    main()
