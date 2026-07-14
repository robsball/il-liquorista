#!/usr/bin/env python3
"""
Phase 2 — Batch translate + clean + structure (the one LLM pass).

Design goals (token economy):
  * ONE model call per page does clean+translate+structure together.
  * Resumable: each page's result is checkpointed to disk; re-runs skip done pages.
  * Cheap tier by default (Haiku/Sonnet); escalate only flagged pages to Opus.
  * Logs token usage per page so cost is measurable, not guessed.

Requires: ANTHROPIC_API_KEY, `pip install anthropic`.

Usage:
  python3 pipeline/phase2_translate.py --pages 214-715 --model claude-haiku-4-5-20251001
  python3 pipeline/phase2_translate.py --pages 30,240,250 --dry-run   # cost estimate only
  python3 pipeline/phase2_translate.py --retry-low 0.6                 # redo low-confidence pages
"""
import argparse, json, os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = ROOT / "data" / "pages_layout"
SCHEMA = ROOT / "pipeline" / "recipe.schema.json"
PROMPT_TPL = ROOT / "pipeline" / "translate_prompt.md"
OUT_RECIPES = ROOT / "data" / "recipes"
OUT_PROSE = ROOT / "data" / "prose"
CKPT = ROOT / "data" / "checkpoints"
USAGE_LOG = ROOT / "data" / "usage.jsonl"
for d in (OUT_RECIPES, OUT_PROSE, CKPT):
    d.mkdir(parents=True, exist_ok=True)

def parse_pages(spec: str):
    pages = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-"); pages.update(range(int(a), int(b) + 1))
        else:
            pages.add(int(part))
    return sorted(pages)

def page_text(n: int) -> str:
    """Prefer the layout text; fall back to the OCR sidecar for image-only pages."""
    p = LAYOUT / f"p{n:04d}.txt"
    txt = p.read_text(encoding="utf-8") if p.exists() else ""
    if len(txt.strip()) < 40:
        ocr = LAYOUT / f"p{n:04d}_ocr.txt"
        if ocr.exists(): txt = ocr.read_text(encoding="utf-8")
    return txt

def build_prompt(schema: str, tpl: str, n: int, text: str) -> str:
    return tpl.replace("{{SCHEMA}}", schema).replace("{{PAGE}}", str(n)).replace("{{TEXT}}", text)

def _emit(n: int, data: dict):
    """Write final artifacts from the model's JSON envelope, dispatched by kind."""
    kind = data.get("kind")
    if kind == "prose" or kind == "table":
        md = data.get("markdown", "")
        head = data.get("heading_en", "")
        body = (f"# {head}\n\n" if head else "") + md + f"\n\n<!-- source page {n} -->\n"
        (OUT_PROSE / f"p{n:04d}.md").write_text(body, encoding="utf-8")
    elif kind == "recipes":
        recipes = data.get("recipes", [])
        (OUT_RECIPES / f"p{n:04d}.json").write_text(
            json.dumps(recipes, ensure_ascii=False, indent=1), encoding="utf-8")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True, help="e.g. 214-715 or 30,240,250")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--dry-run", action="store_true", help="estimate input tokens, no API calls")
    ap.add_argument("--force", action="store_true", help="ignore existing checkpoints")
    ap.add_argument("--max-tokens", type=int, default=8000)
    ap.add_argument("--concurrency", type=int, default=8, help="parallel in-flight requests")
    args = ap.parse_args()

    schema = SCHEMA.read_text(encoding="utf-8")
    if not PROMPT_TPL.exists():
        sys.exit(f"Missing prompt template: {PROMPT_TPL} (write it after the pilot).")
    tpl = PROMPT_TPL.read_text(encoding="utf-8")
    pages = parse_pages(args.pages)

    if args.dry_run:
        total_chars = sum(len(page_text(n)) for n in pages)
        # ~4 chars/token for text + prompt overhead; output ~= input for translate+structure
        in_tok = total_chars / 4 + len(tpl) / 4 * len(pages)
        print(f"pages={len(pages)}  src_chars={total_chars:,}")
        print(f"est input tokens  ~{int(in_tok):,}")
        print(f"est output tokens ~{int(total_chars/4):,} (rough)")
        print("Run without --dry-run (and with ANTHROPIC_API_KEY) to execute.")
        return

    import anthropic
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    client = anthropic.Anthropic(max_retries=4)   # SDK retries 429/5xx with backoff
    log_lock = threading.Lock()
    counter = {"done": 0}

    todo = [n for n in pages if args.force or not (CKPT / f"p{n:04d}.json").exists()]
    print(f"{len(pages)-len(todo)} already done; processing {len(todo)} with concurrency={args.concurrency}", flush=True)

    def work(n: int):
        ck = CKPT / f"p{n:04d}.json"
        text = page_text(n)
        if len(text.strip()) < 40:
            ck.write_text(json.dumps({"page": n, "type": "blank"}), encoding="utf-8"); return
        prompt = build_prompt(schema, tpl, n, text)
        resp = client.messages.create(
            model=args.model, max_tokens=args.max_tokens,
            messages=[{"role": "user", "content": prompt}])
        # models with extended thinking emit ThinkingBlock(s) before the text block
        raw = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        try:
            data = json.loads(re.search(r"\{.*\}|\[.*\]", raw, re.S).group(0))
        except Exception:
            data = {"kind": "error", "raw": raw}
        ck.write_text(json.dumps({"page": n, "data": data}, ensure_ascii=False), encoding="utf-8")
        _emit(n, data)
        with log_lock:
            with USAGE_LOG.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"page": n, "model": args.model,
                                    "in": resp.usage.input_tokens,
                                    "out": resp.usage.output_tokens}) + "\n")
            counter["done"] += 1
            if counter["done"] % 20 == 0:
                print(f"  ...{counter['done']}/{len(todo)} pages done", flush=True)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(work, n): n for n in todo}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception as e:
                print(f"  !! page {futs[fut]} failed: {e}", flush=True)
    print(f"Complete. {counter['done']} pages processed this run.")

if __name__ == "__main__":
    main()
