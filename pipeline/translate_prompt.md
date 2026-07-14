You are digitizing and translating a ca.-1900 Italian liquor-making manual (Castoldi,
"Il Liquorista") into English. The text below is ONE page from an OCR layer and contains
systematic OCR noise: broken spacing, hyphenation split across lines
(e.g. "risulte\nrebbe" = "risulterebbe"), corrupted accents ("gramma"="grammo"),
and misreadings ("Araned"="Arance", "Fuaelòl"="Fusel"). Silently correct obvious OCR
errors using your knowledge of Italian and of distilling/liqueur chemistry. Only when a
token is genuinely ambiguous, keep your best guess and list it in ocr_flags.

Return ONE JSON object, nothing else. Choose the shape by page content:

PROSE page → {
  "kind": "prose", "page": {{PAGE}},
  "heading_en": "<section heading in English, or ''>",
  "markdown": "<faithful, natural English translation. Preserve technical meaning and
     any figures/tables (render tables as GitHub Markdown). Readable modern English —
     NOT archaic word-for-word. Keep paragraph structure.>"
}

RECIPE page → {
  "kind": "recipes", "page": {{PAGE}},
  "recipes": [ <one object per recipe, each matching the schema below> ]
}

TABLE / reference page (numeric conversion tables etc.) → {
  "kind": "table", "page": {{PAGE}},
  "heading_en": "<English caption>",
  "markdown": "<translate headers/captions to English; keep numeric data EXACTLY;
     render as a GitHub Markdown table. If OCR makes the grid unreconstructable,
     set this to '' and add \"needs_image\": true>"
}

Recipe object schema (JSON Schema):
{{SCHEMA}}

Recipe rules:
- Resolve implicit units from section context (e.g. essences by weight in grams, or by
  drops); set unit_implicit=true when the unit was inferred, not printed.
- Multiple printed proportion columns → qty = column 1, variants = [columns 2..n].
- Non-numeric quantities (e.g. "q.b." = to taste) → qty=null, note the meaning.
- "alcool di 96°" and similar → fill alcohol_strength {degrees:96}.
- id = kebab-case of title_en. Set a calibrated 0..1 confidence.

PAGE {{PAGE}} SOURCE TEXT:
------------------------------------------------------------
{{TEXT}}
------------------------------------------------------------
Return only the JSON object.
