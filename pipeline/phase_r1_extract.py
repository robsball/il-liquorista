#!/usr/bin/env python3
"""
R1 — rescue recipes trapped in prose. For candidate prose pages, extract any DISTINCT recipes
(named preparations with ingredient lists/tables) into structured form matching recipes.json.
Returns nothing for pure procedure/technique prose. Uses English prose + Italian source layout
so titles come out bilingual.

Output: data/recipes_r1/p####.json (list of recipe objects). Then merge_r1 folds them in.
"""
import argparse, json, re, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
PROSE = ROOT / "data" / "prose"
LAYOUT = ROOT / "data" / "pages_layout"
OUT = ROOT / "data" / "recipes_r1"
OUT.mkdir(parents=True, exist_ok=True)

SYSTEM = """You are rescuing recipes that were mis-filed as prose during extraction of a 1921
Italian liqueur manual. You get one page as (a) its English translation and (b) the raw Italian
OCR of the same page. Extract every DISTINCT recipe = a named preparation with an ingredient list
or table. Do NOT invent recipes: if the page is general prose, a procedure/technique description,
or a single continuous method with no discrete named recipes + ingredient lists, return {"recipes":[]}.

For each real recipe return an object matching this shape:
{"title_en":"", "title_it":"<from the Italian OCR if identifiable, else ''>", "section_en":"<the page's section>",
 "method":"distillation|infusion|maceration|essence|cold_mix|other|unknown",
 "ingredients":[{"name_en":"","name_it":"","qty":<number|null>,"unit":"<g|ml|drops|parts|...>",
    "unit_implicit":<true if inferred from section convention>,"variants":[<extra proportion columns>]|null,"note":""}],
 "steps_en":[], "notes_en":"", "confidence":0.0-1.0}

Resolve implicit units from the section (compound essences are by weight in grams, or by drops;
multiple numeric columns = variant proportions -> qty is column 1, rest in variants). Fix obvious
OCR errors. Return ONLY {"recipes":[...]}."""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True, help="comma list or a-b ranges")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--concurrency", type=int, default=6)
    args = ap.parse_args()
    pages = []
    for part in args.pages.split(","):
        if "-" in part: a, b = part.split("-"); pages += range(int(a), int(b) + 1)
        else: pages.append(int(part))

    import anthropic
    client = anthropic.Anthropic(max_retries=4)
    lock = threading.Lock(); done = {"n": 0, "rec": 0}

    def work(n):
        ck = OUT / f"p{n:04d}.json"
        if ck.exists(): return
        en = (PROSE / f"p{n:04d}.md")
        it = (LAYOUT / f"p{n:04d}.txt")
        if not en.exists(): return
        msg_text = (f"ENGLISH TRANSLATION:\n{en.read_text(encoding='utf-8')}\n\n"
                    f"ITALIAN OCR (for names/verification):\n{it.read_text(encoding='utf-8') if it.exists() else '(none)'}")
        with client.messages.stream(model=args.model, max_tokens=8000,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": msg_text}]) as s:
            m = s.get_final_message()
        raw = "".join(b.text for b in m.content if getattr(b, "type", None) == "text")
        try:
            blob = re.search(r"\{.*\}", raw, re.S).group(0)
            blob = re.sub(r",(\s*[}\]])", r"\1", blob)
            recs = json.loads(blob).get("recipes", [])
        except Exception:
            recs = []
        for r in recs:
            r["page"] = n
            r["source"] = "prose-rescue"
        ck.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
        with lock:
            done["n"] += 1; done["rec"] += len(recs)
            print(f"  {done['n']}/{len(pages)}  p{n}: {len(recs)} recipes  (running total {done['rec']})", flush=True)

    with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        for f in as_completed([ex.submit(work, n) for n in pages]):
            try: f.result()
            except Exception as e: print(f"  !! failed: {e}", flush=True)
    print(f"R1 extraction: {done['rec']} recipes recovered from {done['n']} pages")

if __name__ == "__main__":
    main()
