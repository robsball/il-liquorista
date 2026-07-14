#!/usr/bin/env python3
"""
Detect & crop illustrations (engravings) embedded in the scanned source pages, so they can be
placed into the reset PDF. Detection is free/local: a figure page has a large vertical band
with NO OCR words but lots of INK.

For each page: parse pdftotext -bbox → find biggest word-free vertical gap → render page →
confirm ink in that band → crop tight to the ink → save build/figures/p####.png.
Records data/figures.json: [{page, crop, bbox_frac, ink_frac, height_frac}].

Usage: python3 pipeline/phase_figures.py --pages 146-180        # a range
       python3 pipeline/phase_figures.py --pages 12-715 --min-gap 0.16
"""
import argparse, json, re, subprocess, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "A. Castoldi - Il Liquorista.pdf"
OUT_IMG = ROOT / "build" / "figures"
OUT_JSON = ROOT / "data" / "figures.json"
OUT_IMG.mkdir(parents=True, exist_ok=True)

def _load_manual():
    p = ROOT / "data" / "figures_manual.json"
    try: return json.loads(p.read_text(encoding="utf-8")).get("rotation", {}) if p.exists() else {}
    except Exception: return {}
MANUAL_ROT = _load_manual()

def page_words(n):
    out = subprocess.run(["pdftotext", "-bbox", "-f", str(n), "-l", str(n), str(PDF), "-"],
                         capture_output=True, text=True).stdout
    mw = re.search(r'page width="([\d.]+)" height="([\d.]+)"', out)
    if not mw: return None
    W, H = float(mw.group(1)), float(mw.group(2))
    words = [tuple(map(float, m)) for m in
             re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)"', out)]
    return W, H, words

def render(n, dpi):
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / "p"
        subprocess.run(["pdftoppm", "-f", str(n), "-l", str(n), "-r", str(dpi), "-gray", "-png",
                        str(PDF), str(base)], check=True, capture_output=True)
        png = next(Path(td).glob("p*.png"))
        return np.asarray(Image.open(png).convert("L"))

def detect(n, dpi=200, min_gap=0.16, ink_thr=0.02, margin_frac=0.01):
    pw = page_words(n)
    if not pw: return None
    W, H, words = pw
    B = 500
    occ = np.zeros(B, bool)
    for (x0, y0, x1, y1) in words:
        occ[int(y0 / H * B): min(B, int(y1 / H * B) + 1)] = True
    # largest contiguous word-free run
    best = (0, 0, 0)
    i = 0
    while i < B:
        if not occ[i]:
            j = i
            while j < B and not occ[j]: j += 1
            if j - i > best[0]: best = (j - i, i, j)
            i = j
        else: i += 1
    runlen, bs, be = best
    if runlen < B * min_gap: return None
    img = render(n, dpi)                      # grayscale page
    ih, iw = img.shape
    py0, py1 = int(bs / B * ih), int(be / B * ih)
    band = img[py0:py1]
    ink = band < 110                          # dark pixels
    if ink.mean() < ink_thr: return None      # word-free but blank -> not a figure
    # isolate the FIGURE BODY on BOTH axes: pick the ink-heaviest connected block (merging small
    # gaps). Rows -> drops caption slivers above/below; columns -> drops sideways-caption strips
    # beside rotated engravings (the p174/p180 bleed).
    def dominant(weight, dense, keep_frac=0.15):
        # split into ink runs; keep only runs whose ink mass is a real fraction of the heaviest
        # (drops thin sparse caption lines beside/above the dense engraving); span the kept runs.
        runs, i, n = [], 0, len(weight)
        while i < n:
            if dense[i]:
                j = i
                while j < n and dense[j]: j += 1
                runs.append((i, j, float(weight[i:j].sum()))); i = j
            else: i += 1
        if not runs: return None
        mx = max(r[2] for r in runs)
        keep = [r for r in runs if r[2] >= keep_frac * mx]
        return (keep[0][0], keep[-1][1])
    rw = ink.sum(1)
    rr = dominant(rw, rw > iw * 0.01)
    if not rr: return None
    fs, fe = rr
    sub = ink[fs:fe]
    cw = sub.sum(0)
    cc = dominant(cw, cw > sub.shape[0] * 0.02)
    if not cc: return None
    cs, ce = cc
    m = int(margin_frac * ih)
    r0, r1 = max(0, py0 + fs - m), min(ih, py0 + fe + m)
    c0, c1 = max(0, cs - m), min(iw, ce + m)
    crop = Image.fromarray(img[r0:r1, c0:c1])
    rot = int(MANUAL_ROT.get(str(n), 0)) % 360     # deterministic pinned rotation (upright)
    if rot:
        crop = crop.rotate(-rot, expand=True)      # PIL rotate is CCW; -rot = CW
    path = OUT_IMG / f"p{n:04d}.png"
    crop.save(path)
    return {"page": n, "crop": f"build/figures/p{n:04d}.png", "rotation_cw": rot,
            "height_frac": round((r1 - r0) / ih, 3), "width_frac": round((c1 - c0) / iw, 3),
            "ink_frac": round(float(ink.mean()), 3)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--min-gap", type=float, default=0.16)
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()
    pages = []
    for part in args.pages.split(","):
        if "-" in part: a, b = part.split("-"); pages += range(int(a), int(b) + 1)
        else: pages.append(int(part))
    figs = []
    for n in pages:
        try:
            r = detect(n, dpi=args.dpi, min_gap=args.min_gap)
            if r: figs.append(r); print(f"  p{n}: figure  {int(r['width_frac']*100)}%w x {int(r['height_frac']*100)}%h  ink {r['ink_frac']}")
        except Exception as e:
            print(f"  !! p{n}: {e}")
    OUT_JSON.write_text(json.dumps(figs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\ndetected {len(figs)} figures across {len(pages)} pages -> {OUT_JSON}")

if __name__ == "__main__":
    main()
