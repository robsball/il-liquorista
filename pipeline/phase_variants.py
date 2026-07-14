#!/usr/bin/env python3
"""
Variant linking — group recipes that are the SAME liqueur prepared differently (e.g. Curaçao by
distillation vs by essence, or Kümmel I / II). Conservative: groups by the full normalized title
minus version/number suffixes, so distinct products ("Anisette" vs "Anisette olandese") stay separate.

Output: build/site/variants.json (host-portable, id-keyed) — consumed by the site alongside
recipe_resolution.json. One-directional data feed.
"""
import json, re, unicodedata
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "build" / "site"
OUT = SITE / "variants.json"

def norm_title(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\b([ivx]+|no\.?\s*\d+|\d+)\b", " ", t)      # drop roman numerals / numbers
    t = re.sub(r"\(.*?\)", " ", t)                            # drop parentheticals
    t = re.sub(r"[^a-z ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def main():
    recs = json.load(open(SITE / "recipes.json"))["recipes"]
    res = {r["id"]: r for r in json.load(open(SITE / "recipe_resolution.json"))["resolutions"]}
    # generic class names aren't a real "same liqueur" group
    GENERIC = {"liqueur", "bitter liqueur", "fine liqueur", "ordinary liqueur", "compound liqueur",
               "elixir", "cream", "ratafia", "essence", "tincture", "syrup", "cordial", "bitters",
               "aromatic liqueur", "table liqueur"}
    groups = defaultdict(list)
    for r in recs:
        key = norm_title(r.get("title_en"))
        if len(key) >= 3 and key not in GENERIC:
            groups[key].append(r)

    out_groups = []
    by_id = {}
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda r: r.get("page", 0))
        methods = [(res.get(m["id"], {}).get("method_slug") or m.get("method")) for m in members]
        distinct_methods = len(set(m for m in methods if m)) > 1
        canonical = members[0]["id"]
        gm = []
        for i, m in enumerate(members):
            meth = res.get(m["id"], {}).get("method_slug") or m.get("method")
            kind = (f"by {meth}" if distinct_methods and meth else f"version {i+1}")
            gm.append({"id": m["id"], "title_en": m.get("title_en"), "page": m.get("page"),
                       "variant_kind": kind, "method": meth})
            by_id[m["id"]] = {"group": key, "canonical_id": canonical,
                              "is_canonical": m["id"] == canonical, "variant_kind": kind,
                              "sibling_ids": [x["id"] for x in members if x["id"] != m["id"]]}
        out_groups.append({"key": key, "canonical_id": canonical, "count": len(members), "members": gm})

    out_groups.sort(key=lambda g: -g["count"])
    feed = {"meta": {"generated": "2026-07-09", "schema_version": 1,
                     "portable": "recipe-id keyed; no host/path deps",
                     "group_count": len(out_groups),
                     "linked_recipes": len(by_id)},
            "groups": out_groups, "by_id": by_id}
    OUT.write_text(json.dumps(feed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {OUT}: {len(out_groups)} variant groups covering {len(by_id)} recipes")
    print("largest groups:")
    for g in out_groups[:15]:
        print(f"  {g['count']:>2}x  {g['key']}  ({', '.join(sorted(set(m['variant_kind'] for m in g['members'])))[:60]})")

if __name__ == "__main__":
    main()
