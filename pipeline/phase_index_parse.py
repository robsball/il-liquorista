#!/usr/bin/env python3
"""
Parse the book's Italian alphabetical index (source pages 716-734, noisy 2-column OCR) into
structured entries, so we can reconcile it against our extracted recipes and find any gaps.

Each index entry = an aromatic/fantasy name + the methods it is made by (each method+page ≈ one
recipe). Output: data/index_entries.json = [{name, refs:[{method, pages:[...]}]}].
"""
import json, re, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parent.parent
LAYOUT = ROOT / "data" / "pages_layout"
OUT = ROOT / "data" / "index_entries.json"

SYSTEM = """You are parsing ONE page of the Italian alphabetical index of a 1921 liqueur manual
("Il Liquorista"). The OCR is noisy and the page has TWO columns (text may interleave). Method
abbreviations: (A)=bitter/amaro, (D)=distillation, (M)=maceration, (O)=essential oils, (E)=extracts,
(Ess.)=essence, (R)=rosolio, (Cr.)=cream, (T)=tincture, (S)=syrup.

Extract every index entry. An entry is an aromatic/liquor NAME followed by page references, often
grouped by method code. Indented sub-lines starting with 'di'/'d''/'al'/'alla' belong to the
preceding headword — join them (e.g. headword 'Acqua' + 'd'oro' -> 'Acqua d'oro'). Correct obvious
OCR errors in NAMES (use your knowledge of Italian liqueur/botanical names). Ignore pure
cross-references ('vedi ...').

Return ONLY JSON: {"entries": [{"name": "<clean Italian name>",
  "refs": [{"method": "<one code above or ''>", "pages": [<integers>]}]}]}"""

def main():
    import anthropic
    client = anthropic.Anthropic(max_retries=4)
    lock = threading.Lock(); all_entries = []
    pages = list(range(716, 735))

    def work(n):
        f = LAYOUT / f"p{n:04d}.txt"
        if not f.exists(): return
        txt = f.read_text(encoding="utf-8", errors="replace")
        if len(txt.strip()) < 40: return
        with client.messages.stream(model="claude-sonnet-5", max_tokens=8000,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": f"Index page {n}:\n{txt}"}]) as s:
            m = s.get_final_message()
        raw = "".join(b.text for b in m.content if getattr(b, "type", None) == "text")
        try:
            blob = re.sub(r",(\s*[}\]])", r"\1", re.search(r"\{.*\}", raw, re.S).group(0))
            ents = json.loads(blob).get("entries", [])
        except Exception:
            ents = []
        with lock:
            all_entries.extend(ents)
            print(f"  p{n}: {len(ents)} entries", flush=True)

    with ThreadPoolExecutor(max_workers=6) as ex:
        for fut in as_completed([ex.submit(work, n) for n in pages]):
            try: fut.result()
            except Exception as e: print(f"  !! {e}")

    # tally recipe instances = total (method,page) pairs
    instances = sum(len(r.get("pages", [1])) or 1 for e in all_entries for r in e.get("refs", []))
    OUT.write_text(json.dumps({"entry_count": len(all_entries), "instance_count": instances,
                               "entries": all_entries}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nparsed {len(all_entries)} index headwords, ~{instances} recipe instances -> {OUT}")

if __name__ == "__main__":
    main()
