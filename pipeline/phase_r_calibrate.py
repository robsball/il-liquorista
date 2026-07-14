#!/usr/bin/env python3
"""
Calibrate sweetening honesty after the grade audit (cross-model agreement ~59%; 'Fine' not robust).
For the ambiguous liqueur core (Ordinary/Fine) at low confidence, present the UNION range
(ordinary-to-fine, 100-325 g/L) instead of a false-precise single class band, and mark the grade
as an estimate. Distinct classes (Rosolios, Ratafias, Spirits, Double) are kept. Pure data step,
idempotent, reversible (best-guess grade retained in `grade`).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "build" / "site" / "recipe_resolution.json"
AMBIG = {"Ordinary liqueurs", "Fine liqueurs"}
UNION = [100, 325]            # Ordinary low .. Fine high
THRESH = 0.7                  # below this, the Ordinary/Fine call isn't trustworthy -> widen

def main():
    d = json.load(open(FEED, encoding="utf-8"))
    widened = estimated = 0
    for r in d["resolutions"]:
        sw = r.get("inherited", {}).get("sweetening")
        if not sw or r.get("recipe_role") not in ("finished_liqueur", "spirit"):
            continue
        conf = sw.get("confidence", 0)
        if conf < THRESH:
            r["grade_estimated"] = True
            estimated += 1
        if r.get("grade") in AMBIG and conf < THRESH:
            sw["g_per_l"] = UNION
            sw["note"] = "ordinary-to-fine liqueur — the manual leaves the exact amount to taste"
            sw["source"]["class"] = "Ordinary–Fine (estimated)"
            widened += 1
    d["meta"]["calibrated"] = "2026-07-09"
    d["meta"]["calibration"] = {"note": "grade audit: ~59% cross-model agreement; low-confidence "
        "Ordinary/Fine widened to union range to avoid false precision",
        "widened": widened, "grade_estimated": estimated}
    FEED.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"calibrated: {widened} low-confidence Ordinary/Fine widened to {UNION} g/L; "
          f"{estimated} grades marked estimated (conf<{THRESH})")

if __name__ == "__main__":
    main()
