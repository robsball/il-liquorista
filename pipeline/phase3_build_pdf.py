#!/usr/bin/env python3
"""
Phase 3 — Generate the reset English PDF from translated data (100% local, no tokens).

Reads:  data/prose/p####.md   (translated prose/tables, in page order)
        data/recipes/p####.json (structured recipes, in page order)
Writes: build/pdf/book.typ  -> compile with `typst compile build/pdf/book.typ`

Runs against whatever pages are done so far (resumable-friendly preview).
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROSE = ROOT / "data" / "prose"
RECIPES = ROOT / "data" / "recipes"
OUT = ROOT / "build" / "pdf" / "book.typ"
OUT.parent.mkdir(parents=True, exist_ok=True)

# ---- Typst preamble: vintage liqueur-manual styling -------------------------
PREAMBLE = r"""
#set document(title: "The Liqueurist", author: "A. Castoldi")
#set page(paper: "a5", margin: (x: 2.0cm, y: 2.2cm),
  header: context {
    if counter(page).get().first() > 2 [
      #set text(9pt, style: "italic", fill: luma(40%))
      #align(center)[The Liqueurist]
    ]
  },
  footer: context [
    #set align(center); #set text(9pt, fill: luma(40%))
    #counter(page).display("1")
  ])
#set text(font: ("Libertinus Serif", "New Computer Modern"), size: 11pt, lang: "en")
#set par(justify: true, leading: 0.62em, first-line-indent: 1.2em)
#show heading.where(level: 1): it => {
  v(1.2cm)
  set text(20pt, weight: "regular")
  set par(first-line-indent: 0pt)
  align(center)[#smallcaps(it.body)]
  v(0.2cm); align(center)[#box(width: 30%, line(length: 100%, stroke: 0.4pt))]
  v(0.6cm)
}
#show heading.where(level: 2): it => {
  set text(13pt, weight: "regular"); set par(first-line-indent: 0pt)
  v(0.5cm); smallcaps(it.body); v(0.15cm)
}

// Recipe renderer: title, section tag, ingredient table, steps, notes.
#let recipe(section: none, title: "", subtitle: none, meta: none, ingredients: (), steps: (), notes: none) = block(breakable: true, width: 100%, inset: (y: 4pt))[
  #set par(first-line-indent: 0pt)
  #if section != none [ #text(8.5pt, tracking: 1pt, fill: luma(45%))[#upper(section)] #linebreak() ]
  #text(13pt, weight: "medium")[#title]
  #if subtitle != none [ #h(0.4em) #text(10pt, style: "italic", fill: luma(40%))[#subtitle] ]
  #if meta != none [ #linebreak() #text(9pt, style: "italic", fill: luma(45%))[#meta] ]
  #v(3pt)
  #if ingredients.len() > 0 {
    set text(10pt)
    table(columns: (1fr, auto), stroke: none, inset: (x: 0pt, y: 2.2pt), align: (left, right),
      ..ingredients.map(r => (
        [#r.at(0)#box(width: 1fr, repeat[#h(3pt).#h(3pt)])],
        [#r.at(1)]
      )).flatten()
    )
  }
  #if steps.len() > 0 [
    #v(3pt); #set text(10.5pt)
    #for (i, s) in steps.enumerate() [ #text(fill: luma(40%))[#(i+1).] #s #parbreak() ]
  ]
  #if notes != none [ #v(2pt); #text(9.5pt, style: "italic", fill: luma(35%))[#notes] ]
]
"""

TITLE_PAGE = r"""
#align(center + horizon)[
  #text(9pt, tracking: 3pt, fill: luma(45%))[TRANSLATED FROM THE ITALIAN]
  #v(1.4cm)
  #text(34pt, weight: "regular")[#smallcaps[The Liqueurist]]
  #v(0.3cm)
  #box(width: 40%, line(length: 100%, stroke: 0.5pt))
  #v(0.5cm)
  #text(12pt, style: "italic")[Two Thousand Recipes and Practical Procedures]
  #v(2.2cm)
  #text(13pt)[Dott. A. Castoldi]
  #v(0.2cm)
  #text(9pt, fill: luma(45%))[Manuali Hoepli · English digital edition]
]
#pagebreak()
"""

def typ_escape(s: str) -> str:
    s = s.replace("\\", "\\\\").replace("#", "\\#").replace("$", "\\$") \
         .replace("@", "\\@").replace("*", "\\*").replace("_", "\\_") \
         .replace("<", "\\<").replace(">", "\\>").replace("`", "\\`") \
         .replace("=", "\\=")
    # neutralize line-leading list/heading markers that Typst would parse as markup
    return re.sub(r"(?m)^(\s*)([-+/])", r"\1\\\2", s)

# Real chapter boundaries (from the Phase 0 structure map). Only these force a page break;
# everything else flows continuously so prose isn't fragmented one-page-per-source-page.
CHAPTERS = {
    12: "Introduction",
    22: "Part One — Materials & the Laboratory",
    28: "Raw Materials",
    84: "Drugs & Botanicals",
    119: "Essential Oils",
    156: "Manipulations",
    199: "Weights & Measures",
    214: "Preparations",
    716: "Alphabetical Index",
}

def load_corrections():
    p = ROOT / "polish" / "corrections.json"
    try: return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception: return {}
CORR = load_corrections()

def load_figures():
    p = ROOT / "data" / "figures.json"
    try: return {f["page"]: f for f in json.loads(p.read_text(encoding="utf-8"))} if p.exists() else {}
    except Exception: return {}
FIGURES = load_figures()

def render_figure(f):
    """Place a preserved engraving (from phase_figures) with its English caption."""
    label = f.get("fig_label") or "Fig."
    cap = f.get("caption_en", "")
    w = "92%" if f.get("width_frac", 0) > f.get("height_frac", 0) else "66%"   # wider box for landscape figures
    capstr = f"[*{typ_escape(label)}* — {typ_escape(cap)}]" if cap else f"[*{typ_escape(label)}*]"
    # numbering: none -> keep only the book's authentic 'Fig. N' label (no Typst 'Figure k:' counter)
    return (f'#figure(image("../figures/p{f["page"]:04d}.png", width: {w}), caption: {capstr}, '
            f'numbering: none)\n#v(0.3cm)\n')

def clean_prose(text: str, page: int = None) -> str:
    """Systematic spacing/OCR polish applied to all prose (fixes 'odd spaces here and there')."""
    # strip original running-headers OCR captured into the text flow (standalone OR inline,
    # with optional surrounding markdown emphasis). 'Il Liquorista — N' is unambiguous.
    text = re.sub(r"[*_]{0,2}\s*Il Liquorista\s*[—–-]\s*\d+\.?\s*[*_]{0,2}", " ", text)
    text = re.sub(r"(?m)^\s*Manuale del [Ll]iquorista\.?\s*$", "", text)
    text = re.sub(r"[ \t]+([,;:.!?])", r"\1", text)     # space before punctuation
    text = re.sub(r"(\d)\s+°", r"\1°", text)            # 85 ° -> 85°
    text = re.sub(r"(\d)\s+%", r"\1%", text)            # 5 % -> 5%
    text = re.sub(r"([A-Za-z])\s+'\s*([A-Za-z])", r"\1'\2", text)  # l ' amido -> l'amido
    text = re.sub(r"[ \t]{2,}", " ", text)              # collapse space runs
    for fx in CORR.get("text_fixes", []):
        scope = fx.get("scope", "all")
        if scope != "all" and scope != (f"page:{page}" if page is not None else None): continue
        text = re.sub(fx["find"], fx["replace"], text) if fx.get("regex") else text.replace(fx["find"], fx["replace"])
    return text

def _is_num(s):
    s = s.strip()
    return s in ("»", "—", "-", "") or bool(re.match(r"^[-–—]?\s*[\d.,]+\s*°?\s*$", s))

def render_table(rows, override=None):
    """Book-quality table: repeating header, per-column numeric alignment, horizontal hairlines.
    Header repeats across page breaks. `override` (from polish/corrections.json) can set
    landscape / font_pt for a specific hand-fixed table."""
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    aligns = []
    for c in range(ncol):
        col = [body[r][c] for r in range(len(body))]
        aligns.append("right" if col and sum(_is_num(x) for x in col) >= len(col) * 0.6 else "left")
    def cell(x): return "[" + md_inline(x) + "]"
    def hcell(x):
        x = typ_escape(x)
        return f"[*{x}*]" if x.strip() else "[]"
    hdr = "table.header(" + ", ".join(hcell(x) for x in header) + ")"
    bdy = ", ".join(cell(x) for r in body for x in r)
    # scale font + inset by width so wide tables fit A5 portrait (keeps caption attached; header repeats)
    fs, inx = (9, 4) if ncol <= 6 else ((7.5, 3) if ncol <= 10 else (6.5, 2))
    override = override or {}
    fs = override.get("font_pt", fs)
    tbl = (f"table(columns: {ncol}, align: ({', '.join(aligns)}), inset: (x: {inx}pt, y: 2.5pt), "
           f"stroke: (x: none, y: 0.3pt), {hdr}" + (", " + bdy if bdy else "") + ")")
    if override.get("landscape"):     # opt-in per-table hand-fix for very wide tables
        return f"#page(flipped: true)[#set text({fs}pt); #align(center + horizon)[#{tbl}]]\n"
    return f"#block(breakable: true)[#set text({fs}pt); #{tbl}]\n"

def split_leading_heading(md: str):
    """Return (body_without_leading_H1, heading_text_or_None). The model tends to emit a
    running section title as the first line; we treat it as a (deduped) subhead, not a chapter."""
    lines = md.splitlines()
    for idx, ln in enumerate(lines):
        if not ln.strip() or ln.startswith("<!--"):
            continue
        if ln.startswith("# "):
            return "\n".join(lines[idx+1:]), ln[2:].strip()
        break
    return md, None

def md_inline(s: str) -> str:
    """Render markdown emphasis as real Typst emphasis (italic Latin names, bold terms) instead of
    escaping the markers to literal asterisks. Non-emphasis text is escaped normally."""
    out, i = [], 0
    for m in re.finditer(r"\*\*(.+?)\*\*|\*(.+?)\*|(?<![A-Za-z0-9])_(.+?)_(?![A-Za-z0-9])", s):
        out.append(typ_escape(s[i:m.start()]))
        b, it1, it2 = m.group(1), m.group(2), m.group(3)
        if b is not None:      out.append("*" + typ_escape(b) + "*")     # Typst bold
        else:                  out.append("_" + typ_escape(it1 or it2) + "_")  # Typst italic
        i = m.end()
    out.append(typ_escape(s[i:]))
    return "".join(out)

def md_to_typ(md: str, page: int = None) -> str:
    """Minimal converter for our controlled prose markdown. In-body headings are demoted to
    level 2/3 (no page break); chapter breaks are inserted separately from CHAPTERS.
    `page` lets polish/corrections.json table_overrides target a specific table."""
    out, i, lines, tidx = [], 0, md.splitlines(), 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if ln.startswith("<!--") or not ln.strip():
            i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)   # any markdown heading -> demoted (never a chapter break)
        if m:
            lvl = min(len(m.group(1)) + 1, 3)     # md H1/H2 -> typst L2, H3+ -> L3
            out.append("=" * lvl + f" {md_inline(m.group(2))}\n"); i += 1; continue
        if ln.lstrip().startswith("|") and "|" in ln:      # pipe table block
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not re.match(r"^[-:\s|]+$", lines[i].strip().strip("|")):  # skip --- sep
                    rows.append(cells)
                i += 1
            if rows:
                ov = None
                if page is not None:
                    to = CORR.get("table_overrides", {})
                    ov = to.get(f"p{page:04d}:{tidx}") or to.get(f"p{page:04d}")
                out.append(render_table(rows, ov)); tidx += 1
            continue
        out.append(md_inline(ln) + "\n"); i += 1
    return "\n".join(out)

def fmt_qty(ing: dict) -> str:
    q = ing.get("qty"); u = ing.get("unit", "") or ""
    if q is None: return ing.get("note", "q.b.")
    base = f"{q:g} {u}".strip()
    if ing.get("variants"):
        vs = " / ".join(f"{v:g}" for v in ing["variants"] if v is not None)
        base += f" ({vs})"
    return base

def render_recipe(r: dict) -> str:
    section = r.get("section_en")
    ings = [(typ_escape(ing.get("name_en", ing.get("name_it", "?"))), typ_escape(fmt_qty(ing)))
            for ing in r.get("ingredients", [])]
    meta_bits = []
    if r.get("alcohol_strength", {}) and r["alcohol_strength"].get("degrees"):
        meta_bits.append(f"{r['alcohol_strength']['degrees']:g}° spirit")
    if r.get("temperature_c"): meta_bits.append(f"{r['temperature_c']:g} °C")
    if r.get("duration", {}) and r["duration"].get("amount"):
        meta_bits.append(f"{r['duration']['amount']:g} {r['duration'].get('unit','')}")
    meta = ", ".join(meta_bits) or None
    def arg(name, val): return f'{name}: [{val}]' if val else None
    parts = [f'section: {("[" + typ_escape(section) + "]") if section else "none"}',
             f'title: [{typ_escape(r.get("title_en","(untitled)"))}]']
    if r.get("title_it"): parts.append(f'subtitle: [{typ_escape(r["title_it"])}]')
    if meta: parts.append(f'meta: [{meta}]')
    ing_arr = "(" + ", ".join(f'([{n}], [{q}])' for n, q in ings) + ("," if len(ings)==1 else "") + ")"
    parts.append(f'ingredients: {ing_arr}')
    steps = r.get("steps_en") or []
    if steps:
        parts.append("steps: (" + ", ".join(f'[{typ_escape(s)}]' for s in steps) + ("," if len(steps)==1 else "") + ")")
    if r.get("notes_en"): parts.append(f'notes: [{typ_escape(r["notes_en"])}]')
    return "#recipe(" + ", ".join(parts) + ")\n"

def page_num(p: Path) -> int:
    m = re.search(r"(\d+)", p.stem); return int(m.group(1)) if m else 0

def main():
    doc = [PREAMBLE, TITLE_PAGE]
    prose = {page_num(p): p for p in PROSE.glob("p*.md")}
    recs = {page_num(p): p for p in RECIPES.glob("p*.json")}
    all_pages = sorted(set(prose) | set(recs))
    n_recipes, last_sub = 0, None
    for pg in all_pages:
        if pg in CHAPTERS:
            # explicit top-level pagebreak (illegal inside the heading show-rule / containers)
            doc.append(f"#pagebreak(weak: true)\n= {CHAPTERS[pg]}\n"); last_sub = None
        if pg in FIGURES:
            doc.append(render_figure(FIGURES[pg]))
        if pg in prose:
            body, sub = split_leading_heading(prose[pg].read_text(encoding="utf-8"))
            # pages split mid-sentence; the model marks both halves with '...'. Trim the
            # dangling continuation markers so the seam reads cleanly when concatenated.
            body = re.sub(r"^\s*[.…]{2,}\s*", "", body)
            body = re.sub(r"\s*[.…]{2,}\s*$", " ", body)
            body = clean_prose(body, pg)
            if sub and sub != last_sub and pg not in CHAPTERS:
                doc.append(f"== {typ_escape(sub)}\n")
            if sub:
                last_sub = sub
            doc.append(md_to_typ(body, pg))
        if pg in recs:
            try:
                for r in json.loads(recs[pg].read_text(encoding="utf-8")):
                    doc.append(render_recipe(r)); n_recipes += 1
            except Exception as e:
                doc.append(f"// parse error p{pg}: {e}\n")
    OUT.write_text("\n".join(doc), encoding="utf-8")
    print(f"Wrote {OUT}  ({len(all_pages)} pages, {n_recipes} recipes)")

if __name__ == "__main__":
    main()
