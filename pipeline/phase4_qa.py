#!/usr/bin/env python3
"""
Phase 4 — QA re-extraction of low-confidence / zero-ingredient recipe pages via VISION.

For each target page: read the actual page IMAGE (OCR was the weak link) and re-extract all
recipes with a strong model. Originals are backed up to data/recipes_pre_qa/ so results can
be diffed. Only pages given on --pages are touched.

Usage: python3 pipeline/phase4_qa.py --pages 226,234,237 --model claude-sonnet-5
"""
import argparse, base64, json, re, shutil, subprocess, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "A. Castoldi - Il Liquorista.pdf"
SCHEMA = (ROOT / "pipeline" / "recipe.schema.json").read_text(encoding="utf-8")
OUT = ROOT / "data" / "recipes"
BACKUP = ROOT / "data" / "recipes_pre_qa"
IMG = ROOT / "data" / "page_images"
BACKUP.mkdir(parents=True, exist_ok=True)

PROMPT = """This is one page IMAGE from a 1900s Italian liqueur manual ("Il Liquorista").
An earlier text-based pass was low-confidence on this page (OCR was unreliable), so read the
printed text DIRECTLY from the image and re-extract every recipe accurately.

Correct obvious archaic-Italian/printing quirks; resolve implicit units from section context
(essences by weight in grams or by drops); keep multiple proportion columns as `variants`
(qty = column 1). Translate names/steps to natural English. Set a calibrated confidence.

Return ONE JSON object: {"kind":"recipes","page":PAGE,"recipes":[ ...schema objects... ]}
Recipe schema:
%s
Replace PAGE with %d. Return only the JSON."""

def render(n):
    png = IMG / f"qa_p{n:04d}.png"
    if not png.exists():
        subprocess.run(["pdftoppm","-f",str(n),"-l",str(n),"-r","200","-png",str(PDF),
                        str(IMG / f"qa_p{n:04d}")], check=True, capture_output=True)
        for c in IMG.glob(f"qa_p{n:04d}-*.png"): c.rename(png); break
    return png

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args()
    pages=[]
    for p in args.pages.split(","):
        if "-" in p: a,b=p.split("-"); pages+=range(int(a),int(b)+1)
        else: pages.append(int(p))

    import anthropic
    client = anthropic.Anthropic(max_retries=4)
    lock=threading.Lock(); done={"n":0}

    def work(n):
        dst = OUT / f"p{n:04d}.json"
        if dst.exists() and not (BACKUP / f"p{n:04d}.json").exists():
            shutil.copy(dst, BACKUP / f"p{n:04d}.json")     # back up original once
        b64 = base64.standard_b64encode(render(n).read_bytes()).decode()
        with client.messages.stream(model=args.model, max_tokens=16000, messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":"image/png","data":b64}},
                {"type":"text","text":PROMPT % (SCHEMA, n)}]}]) as s:
            msg=s.get_final_message()
        raw="".join(b.text for b in msg.content if getattr(b,"type",None)=="text")
        try:
            data=json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            recipes=data.get("recipes",[])
            if recipes:
                dst.write_text(json.dumps(recipes,ensure_ascii=False,indent=1),encoding="utf-8")
            status=f"{len(recipes)} recipes"
        except Exception as e:
            status=f"PARSE FAIL ({e})"
        with lock:
            done["n"]+=1; print(f"  {done['n']}/{len(pages)}  p{n}: {status}", flush=True)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs={ex.submit(work,n):n for n in pages}
        for f in as_completed(futs):
            try: f.result()
            except Exception as e: print(f"  !! p{futs[f]} failed: {e}", flush=True)
    print("QA done. Originals in data/recipes_pre_qa/")

if __name__=="__main__":
    main()
