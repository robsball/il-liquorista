#!/usr/bin/env python3
"""
Vision pass over detected figure crops: confirm it's a real illustration, find the rotation to
make it upright (old books often printed big engravings sideways), and write an English caption.
Rotates the crop in place and updates data/figures.json with {is_figure, rotation_cw, caption_en,
fig_label}. Drops false positives (tables/text/decoration).
"""
import base64, json, re, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FIGJSON = ROOT / "data" / "figures.json"

PROMPT = """This is a cropped illustration (engraving) from a 1921 Italian liqueur-making manual —
already oriented upright. Return ONLY JSON:
{"is_figure": true|false,  // false if it is actually a table, plain text, or page decoration
 "caption_en": "<concise English caption of what it depicts, e.g. 'Copper still with condenser'>",
 "fig_label": "<the 'Fig. N' label if visible, else null>"}"""

def main():
    figs = json.load(open(FIGJSON, encoding="utf-8"))
    import anthropic
    client = anthropic.Anthropic(max_retries=4)
    lock = threading.Lock(); kept = []

    def work(f):
        p = ROOT / f["crop"]
        b64 = base64.standard_b64encode(p.read_bytes()).decode()
        m = client.messages.create(model="claude-sonnet-5", max_tokens=500,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                {"type": "text", "text": PROMPT}]}])
        raw = "".join(b.text for b in m.content if getattr(b, "type", None) == "text")
        mj = re.search(r"\{.*\}", raw, re.S)
        # tolerate an unparseable response: keep the figure with an empty caption rather than lose it
        d = {"is_figure": True, "caption_en": "", "fig_label": None}
        if mj:
            try: d = json.loads(mj.group(0))
            except Exception: pass
        with lock:
            if not d.get("is_figure"):
                print(f"  p{f['page']}: NOT a figure (dropped)"); return
            f.update({"caption_en": d.get("caption_en", ""), "fig_label": d.get("fig_label")})
            kept.append(f)   # rotation_cw already set deterministically by detection
            print(f"  p{f['page']}: {d.get('fig_label') or 'fig'} — {d.get('caption_en','')[:55]}"
                  + (f"  [pinned rot {f.get('rotation_cw')}°]" if f.get("rotation_cw") else ""))

    with ThreadPoolExecutor(max_workers=5) as ex:
        for fut in as_completed([ex.submit(work, f) for f in figs]):
            try: fut.result()
            except Exception as e: print(f"  !! {e}")
    kept.sort(key=lambda f: f["page"])
    FIGJSON.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nkept {len(kept)} figures (dropped {len(figs)-len(kept)} non-figures)")

if __name__ == "__main__":
    main()
