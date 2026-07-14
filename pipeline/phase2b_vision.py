#!/usr/bin/env python3
"""
Phase 2b — Vision transcription for dense numeric tables that defeated OCR.

For pages the text pass flagged (kind=error or needs_image), read the rendered page
IMAGE with a vision model and transcribe the table exactly. Writes data/prose/p####.md
(kind=table) so the Phase 3 PDF generator picks it up unchanged. Resumable via a
separate checkpoint namespace so it never clobbers text-pass results.

Usage:
  python3 pipeline/phase2b_vision.py --pages 49-81 --model claude-sonnet-5
Requires ANTHROPIC_API_KEY, `pip install anthropic`, and pdftoppm on PATH.
"""
import argparse, base64, json, re, subprocess, sys, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "A. Castoldi - Il Liquorista.pdf"
OUT_PROSE = ROOT / "data" / "prose"
IMG_DIR = ROOT / "data" / "page_images"
CKPT = ROOT / "data" / "checkpoints_vision"
for d in (OUT_PROSE, IMG_DIR, CKPT):
    d.mkdir(parents=True, exist_ok=True)

PROMPT = """This is one page from a 1921 Italian manual on liqueur-making ("Il Liquorista").
It contains a DENSE NUMERIC REFERENCE TABLE (e.g. alcoholometer scale conversions, or
weights & measures) that ordinary OCR could not read. Transcribe it faithfully.

Rules:
- Reproduce EVERY number exactly as printed. Do not round, interpolate, or invent values.
  Italian decimals use a comma (0,9948) — keep the comma.
- Translate only the caption and column HEADERS into English; leave numeric data untouched.
- If a cell is genuinely illegible, put "?" — never guess a digit.
- These are standard physical conversion tables; use that to sanity-check, not to fabricate.

Return ONE JSON object, nothing else:
{"kind":"table","page":PAGE,"heading_en":"<English caption>","markdown":"<GitHub-Markdown table>"}
Replace PAGE with the integer %d."""

def render(n: int) -> Path:
    out = IMG_DIR / f"vis_p{n:04d}"
    png = IMG_DIR / f"vis_p{n:04d}.png"
    if not png.exists():
        subprocess.run(["pdftoppm", "-f", str(n), "-l", str(n), "-r", "200", "-png",
                        str(PDF), str(out)], check=True, capture_output=True)
        # pdftoppm appends -NN; normalize to a stable name
        for c in IMG_DIR.glob(f"vis_p{n:04d}-*.png"):
            c.rename(png); break
    return png

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True)
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    pages = []
    for part in args.pages.split(","):
        if "-" in part: a, b = part.split("-"); pages += list(range(int(a), int(b)+1))
        else: pages.append(int(part))

    import anthropic
    client = anthropic.Anthropic(max_retries=4)
    lock = threading.Lock(); done = {"n": 0}
    todo = [n for n in pages if args.force or not (CKPT / f"p{n:04d}.json").exists()]
    print(f"vision transcribing {len(todo)} pages, concurrency={args.concurrency}", flush=True)

    def work(n):
        png = render(n)
        b64 = base64.standard_b64encode(png.read_bytes()).decode()
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text", "text": PROMPT % n}]
        # stream so large tables can exceed the SDK's 10-minute non-streaming guard
        with client.messages.stream(model=args.model, max_tokens=args.max_tokens,
                                    messages=[{"role": "user", "content": content}]) as stream:
            msg = stream.get_final_message()
        raw = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        try:
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        except Exception:
            data = {"kind": "error", "page": n, "raw": raw}
        (CKPT / f"p{n:04d}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if data.get("kind") == "table":
            head = data.get("heading_en", "")
            body = (f"# {head}\n\n" if head else "") + data.get("markdown", "") + f"\n\n<!-- source page {n} (vision) -->\n"
            (OUT_PROSE / f"p{n:04d}.md").write_text(body, encoding="utf-8")
        with lock:
            done["n"] += 1
            print(f"  {done['n']}/{len(todo)}  p{n} -> {data.get('kind')}", flush=True)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(work, n): n for n in todo}
        for f in as_completed(futs):
            try: f.result()
            except Exception as e: print(f"  !! p{futs[f]} failed: {e}", flush=True)
    print("done.")

if __name__ == "__main__":
    main()
