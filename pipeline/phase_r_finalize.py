#!/usr/bin/env python3
"""
Finalize/validate a recipe_resolution.json feed against the kestrel techniques.json:
  - snap each `grade` to the EXACT canonical class string (fix model vocabulary drift)
  - OVERWRITE sweetening.g_per_l DETERMINISTICALLY from the table (Opus judges class,
    the table supplies the numbers) — so no model-recalled figure ships
  - null out sweetening for unclassifiable (grade=None) — honest, no false claim
  - emit a validation report

Idempotent. Run after phase_r_resolve.py, before handing the feed to the site.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "build" / "site" / "recipe_resolution.json"
KES_TECH = Path.home() / "Development/kestrel-admin/public/liquorista/techniques.json"

def main():
    tech = json.load(open(KES_TECH, encoding="utf-8"))
    table = {r["cls"]: r["g_l"] for r in tech["sweetening_table"]["rows"]}
    allowed = list(table.keys())

    def snap(grade):
        if grade in table: return grade, False
        if not grade: return None, False
        g = grade.strip().lower()
        for cls in allowed:                       # fuzzy: shared prefix/substring
            base = cls.split(" (")[0].lower()
            if g == cls.lower() or g.startswith(base) or base.startswith(g) or g in cls.lower():
                return cls, True
        return None, True                          # unmatchable -> unclassified

    feed = json.load(open(FEED, encoding="utf-8"))
    snapped = unclassified = numeric_fixed = 0
    for r in feed["resolutions"]:
        canon, changed = snap(r.get("grade"))
        if changed and canon: snapped += 1
        r["grade"] = canon
        sw = r.setdefault("inherited", {}).get("sweetening")
        if canon is None:
            r["inherited"]["sweetening"] = None    # no class -> no inherited sugar claim
            # only a PROBLEM if the recipe is a drink that should have a grade; bases are meant to be null
            if r.get("recipe_role") in ("finished_liqueur", "spirit"):
                r.setdefault("flags", []).append("unclassified-grade")
                unclassified += 1
        elif sw is not None:
            table_range = table[canon]
            if sw.get("g_per_l") != table_range:
                sw["g_per_l"] = table_range         # authoritative from the table
                numeric_fixed += 1
            sw["source"]["class"] = canon
    feed["meta"]["validated"] = "2026-07-09"
    feed["meta"]["validation"] = {"snapped_grades": snapped, "unclassified": unclassified,
                                  "numeric_corrected": numeric_fixed}
    FEED.write_text(json.dumps(feed, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Validated {len(feed['resolutions'])} resolutions:")
    print(f"  grade strings snapped to canonical: {snapped}")
    print(f"  g/L ranges corrected from table:    {numeric_fixed}")
    print(f"  unclassified (sweetening nulled):   {unclassified}")

if __name__ == "__main__":
    main()
