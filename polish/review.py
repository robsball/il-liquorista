#!/usr/bin/env python3
"""Render pages of build/pdf/book.pdf to polish/review/*.png for visual review of layout polish.
Usage: python3 polish/review.py 74 92 305      # specific pages
       python3 polish/review.py --sample 24     # 24 evenly-spaced pages across the book
"""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "build" / "pdf" / "book.pdf"
OUT = ROOT / "polish" / "review"; OUT.mkdir(exist_ok=True)
def npages():
    o = subprocess.run(["pdfinfo", str(PDF)], capture_output=True, text=True).stdout
    return int([l for l in o.splitlines() if l.startswith("Pages:")][0].split()[1])
args = sys.argv[1:]
if args and args[0] == "--sample":
    k = int(args[1]); n = npages(); pages = [max(1, n*i//k) for i in range(k)]
else:
    pages = [int(a) for a in args] or [1]
for p in pages:
    subprocess.run(["pdftoppm", "-f", str(p), "-l", str(p), "-r", "110", "-png",
                    str(PDF), str(OUT / f"p{p:04d}")], check=True)
print(f"rendered {len(pages)} page(s) to {OUT}")
