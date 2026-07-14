#!/usr/bin/env python3
"""
Phase 0 — Extraction & structure map (100% local, zero LLM tokens).

Produces, per page:
  - data/pages_layout/p####.txt   layout-preserved Italian text (best for tables)
  - data/structure_map.json       one record per page with profiling signals
  - data/structure_summary.txt    human-readable overview

Profiling signals let later phases route each page to the cheapest path:
  empty   -> needs image OCR (tesseract -l ita)
  table   -> may need image fallback if -layout is garbled
  heading -> chapter/section boundary (structure)
  recipe  -> likely recipe content (dense short lines, quantities/units)
"""
import json, re, subprocess, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "A. Castoldi - Il Liquorista.pdf"
LAYOUT_DIR = ROOT / "data" / "pages_layout"
MAP_JSON = ROOT / "data" / "structure_map.json"
SUMMARY = ROOT / "data" / "structure_summary.txt"

# Italian units/quantity cues -> a page rich in these is likely recipe content.
UNIT_RE = re.compile(r"\b(gr(?:ammi)?|kg|litr[oi]|cl|ml|dl|once|libbre|gocce|"
                     r"cucchia[it]|manciata|pizzico|°|grad[oi])\b", re.I)
NUM_RE = re.compile(r"\d")
# A heading line: short, mostly letters, often Title-Case or ALL CAPS, few digits.
def looks_like_heading(line: str) -> bool:
    s = line.strip()
    if not (3 <= len(s) <= 60): return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 3: return False
    caps = sum(1 for c in letters if c.isupper())
    return caps / len(letters) > 0.6  # ALL-CAPS-ish

def extract_page(n: int) -> str:
    out = subprocess.run(
        ["pdftotext", "-layout", "-f", str(n), "-l", str(n), str(PDF), "-"],
        capture_output=True, text=True)
    return out.stdout

def profile(text: str) -> dict:
    stripped = text.strip()
    lines = [l for l in text.splitlines() if l.strip()]
    chars = len(stripped)
    # "table-ish": lines with runs of >=3 spaces (columnar gaps) are common
    gap_lines = sum(1 for l in lines if re.search(r"\S {3,}\S", l))
    gap_ratio = gap_lines / len(lines) if lines else 0
    unit_hits = len(UNIT_RE.findall(text))
    headings = [l.strip() for l in lines if looks_like_heading(l)]
    avg_line_len = statistics.mean(len(l) for l in lines) if lines else 0
    tags = []
    if chars < 40: tags.append("empty")
    if gap_ratio > 0.35 and chars > 60: tags.append("table")
    if headings: tags.append("heading")
    # recipe heuristic: several unit cues + shortish lines
    if unit_hits >= 3 and avg_line_len < 55 and chars > 80: tags.append("recipe")
    return {"chars": chars, "lines": len(lines), "gap_ratio": round(gap_ratio, 2),
            "unit_hits": unit_hits, "avg_line_len": round(avg_line_len, 1),
            "headings": headings[:4], "tags": tags}

def main():
    import sys
    # page count from pdfinfo
    info = subprocess.run(["pdfinfo", str(PDF)], capture_output=True, text=True).stdout
    npages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else npages
    records = []
    for n in range(1, limit + 1):
        text = extract_page(n)
        (LAYOUT_DIR / f"p{n:04d}.txt").write_text(text, encoding="utf-8")
        rec = {"page": n, **profile(text)}
        records.append(rec)
        if n % 50 == 0: print(f"  ...{n}/{limit}", flush=True)
    MAP_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")

    # summary
    def count(tag): return sum(1 for r in records if tag in r["tags"])
    total_chars = sum(r["chars"] for r in records)
    lines = [
        f"Pages profiled: {len(records)}",
        f"Total characters (text layer): {total_chars:,}",
        f"  empty   (need image OCR): {count('empty')}",
        f"  table   (watch layout):   {count('table')}",
        f"  recipe  (structure to JSON): {count('recipe')}",
        f"  heading (section boundary):  {count('heading')}",
        "",
        "First 60 heading lines (rough table of contents):",
    ]
    shown = 0
    for r in records:
        for h in r["headings"]:
            if shown >= 60: break
            lines.append(f"  p{r['page']:>4}  {h}")
            shown += 1
        if shown >= 60: break
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
