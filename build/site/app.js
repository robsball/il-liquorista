'use strict';
const $ = (s, r=document) => r.querySelector(s);
const app = $('#app');
let DB = null, TAX = null, TQ = null, BY_ID = {}, RES_BY_ID = {}, VAR_BY_ID = {}, VAR_GROUPS = {}, CATS = [], scale = 1;

async function boot(){
  const [rec, tax, tq, res, vars] = await Promise.all([
    fetch('recipes.json').then(r=>r.json()),
    fetch('taxonomy.json').then(r=>r.ok?r.json():null).catch(()=>null),
    fetch('techniques.json').then(r=>r.ok?r.json():null).catch(()=>null),
    fetch('recipe_resolution.json').then(r=>r.ok?r.json():null).catch(()=>null),
    fetch('variants.json').then(r=>r.ok?r.json():null).catch(()=>null),
  ]);
  DB = rec; TAX = tax; TQ = tq;
  // Inherited-knowledge feed (Il-Liquorista pipeline): grade-classified sweetening,
  // dilution, and finishing each recipe assumes but omits. Keyed by recipe id.
  (res && res.resolutions || []).forEach(x=>{ RES_BY_ID[x.id] = x; });
  // Variants feed: which recipes are alternate preparations of the same liqueur.
  // by_id[id] -> {group, canonical_id, variant_kind, sibling_ids}; groups[key] is
  // the full member list (title/kind/method/page) for a browsable "N ways" view.
  if(vars){ VAR_BY_ID = vars.by_id || {}; (vars.groups || []).forEach(g=>{ VAR_GROUPS[g.key] = g; }); }
  const map = (tax && tax.mapping) || {};
  const blurbs = {}; (tax && tax.categories || []).forEach(c=>blurbs[c.name]=c.blurb);
  // assign canonical category to each recipe
  DB.recipes.forEach(r=>{ r.cat = map[r.section_en] || r.section_en || 'Miscellaneous'; BY_ID[r.id]=r; });
  const counts = {};
  DB.recipes.forEach(r=>counts[r.cat]=(counts[r.cat]||0)+1);
  CATS = Object.keys(counts).map(name=>({name,count:counts[name],blurb:blurbs[name]||''}))
              .sort((a,b)=>b.count-a.count);
  $('#footmeta').textContent = `${DB.meta.recipe_count.toLocaleString()} recipes`;
  $('#search').addEventListener('input', e=>{
    const q=e.target.value.trim(); location.hash = q ? '#/search/'+encodeURIComponent(q) : '#/';
  });
  window.addEventListener('hashchange', route); route();
}

function route(){
  const h = decodeURIComponent(location.hash.slice(2)); // strip "#/"
  window.scrollTo(0,0);
  if(h.startsWith('r/')) return renderRecipe(h.slice(2));
  if(h.startsWith('g/')) return renderVariantGroup(h.slice(2));
  if(h.startsWith('c/')) return renderCategory(h.slice(2));
  if(h.startsWith('search/')) return renderSearch(h.slice(7));
  if(h.startsWith('t/')) return renderTechnique(h.slice(2));
  if(h==='techniques') return renderTechniques();
  if(h==='about') return renderAbout();
  renderHome();
}

function renderHome(){
  // Hero: hand-colored botanical engravings (the book's pantry — anise, wormwood,
  // juniper, citrus, chamomile, thistle, the alembics) flank the title. A 3-column
  // grid so art and text can never overlap; the art scales with the viewport and
  // is hidden on small screens (see styles.css). Paths are case-sensitive in prod.
  app.innerHTML =
    `<div class="hero">
       <div class="hero-art hero-art-l" aria-hidden="true"><img src="/assets/IL-left.png" alt=""></div>
       <div class="hero-text">
         <h1>The Liqueurist</h1>
         <div class="rule"></div>
         <div class="sub">${DB.meta.subtitle}<br>${DB.meta.author}</div>
         <a class="aboutlink" href="#/about">About this project</a>
       </div>
       <div class="hero-art hero-art-r" aria-hidden="true"><img src="/assets/IL-Right.png" alt=""></div>
     </div>
     ${TQ?`<div class="tband">
       <div class="tband-head">
         <span class="tband-title">The Techniques</span>
         <span class="tband-sub">the general rules every recipe assumes</span>
         <a class="tband-all" href="#/techniques">Browse all →</a>
       </div>
       <div class="tband-chips">${TQ.topics.map(t=>
         `<a class="tchip" href="#/t/${t.slug}">${esc(t.title)}</a>`).join('')}</div>
     </div>`:''}
     <div class="grid">${CATS.map((c,i)=>
       `<a class="cat" style="--i:${Math.min(i,16)}" href="#/c/${encodeURIComponent(c.name)}">
          <span class="count">${c.count} recipes</span>
          <h3>${esc(c.name)}</h3>
          ${c.blurb?`<p class="blurb">${esc(c.blurb)}</p>`:''}
        </a>`).join('')}</div>`;
}

// ── Techniques: the book's general rules, extracted into techniques.json ────
const SWEET_RX = /sugar|syrup|zucchero|sciroppo|honey|miele/i;
function hasSweetIngredient(r){
  return (r.ingredients||[]).some(i=>SWEET_RX.test((i.name_en||'')+' '+(i.name_it||'')));
}
function fmtSugar(g){ return g>=1000 ? (Math.round(g/50)*50/1000)+' kg' : Math.round(g)+' g'; }

// ── Inherited-knowledge panel (recipe_resolution.json) ─────────────────────
// The grade-classified successor to sweetPanel: what a recipe inherits from the
// book's general method (sweetening, dilution, finishing) but never states.
// Honesty rules, since this is public: confidence is always shown and a grade
// below 0.5 reads "estimated" not asserted; if the recipe sweetens itself we
// never add sugar on top; if it's unclassifiable we show a plain note, no guess.
const FIN_ALIAS = { infusion: 'maceration' }; // finishing slug with no topic page of its own
function prettySlug(s){ return s.replace(/[-_]/g, ' ').replace(/^\w/, (c) => c.toUpperCase()); }
function techTopic(slug){
  const s = FIN_ALIAS[slug] || slug;
  const t = TQ && (TQ.topics || []).find((x) => x.slug === s);
  return t ? { slug: s, title: t.title } : { slug: null, title: prettySlug(slug) };
}
function confChip(conf, forceEst){
  const known = typeof conf === 'number';
  if(!known && !forceEst) return '';
  const low = forceEst || conf < 0.5;
  const title = known ? `confidence ${conf.toFixed(2)}` : 'estimated — no confidence score';
  return `<span class="conf ${low ? 'conf-est' : 'conf-inf'}" title="${title}">${low ? 'estimated' : 'inferred'}</span>`;
}

// Techniques the method draws on, as chips (sweetening/dilution get their own rows).
function finishingChips(inh){
  const seen = new Set(['sweetening', 'dilution']);
  return (inh.finishing || []).map((s) => {
    const key = FIN_ALIAS[s] || s;
    if(seen.has(key)) return null;
    seen.add(key);
    const t = techTopic(s);
    return t.slug
      ? `<a class="inh-chip" href="#/t/${t.slug}">${esc(t.title)}</a>`
      : `<span class="inh-chip">${esc(t.title)}</span>`;
  }).filter(Boolean);
}

// Roles that get the inherited-sweetening panel. Everything else is a base or
// ingredient (colorant, syrup, punch, aromatized wine...) whose grade/sweetening
// are null on purpose — those get usagePanel() instead.
const SWEETENED_ROLES = new Set(['finished_liqueur', 'spirit']);
const ROLE_LABEL = {
  flavoring_base: 'Flavoring base',
  colorant: 'Colorant',
  syrup: 'Syrup',
  aromatic_water: 'Aromatic water',
  wine_aromatized: 'Aromatized wine',
  punch: 'Punch',
  other: 'Preparation',
};

// Base/ingredient panel: a role badge and a "how it's used" line — never sugar.
function usagePanel(res){
  const inh = res.inherited || {};
  const label = ROLE_LABEL[res.recipe_role] || 'Preparation';
  const rows = [];
  if(res.usage_note){
    rows.push(`<div class="inh-row"><div class="inh-k">How this is used</div><div class="inh-v">${esc(res.usage_note)}</div></div>`);
  }
  const chips = finishingChips(inh);
  if(chips.length){
    rows.push(`<div class="inh-row"><div class="inh-k">The method draws on</div><div class="inh-chips">${chips.join('')}</div></div>`);
  }
  return `<aside class="inh inh-base">
    <div class="inh-head"><span class="role-badge">${esc(label)}</span> a base preparation — no inherited liqueur sweetening</div>
    ${rows.join('')}
    ${res.rationale ? `<div class="inh-why">Why: ${esc(res.rationale)}</div>` : ''}
  </aside>`;
}

function resolutionPanel(r, res){
  // Bases, colorants, syrups, punches, aromatized wines aren't finished liqueurs —
  // show what they're for, not a sugar dose the book never intends for them.
  if(!SWEETENED_ROLES.has(res.recipe_role)) return usagePanel(res);

  const inh = res.inherited || {};
  const sw = inh.sweetening;
  const rows = [];

  // Sweetening — three honest branches.
  if(sw && !res.already_sweetened){
    const [lo, hi] = sw.g_per_l;
    const src = sw.source || {};
    const page = src.page_en;
    const rawCls = src.class || res.grade || 'this class';
    // The pipeline widens low-agreement grades and tags the class "(estimated)";
    // grade_estimated is the explicit flag. Either means: label it, don't assert it.
    const estimated = !!res.grade_estimated || /estimated/i.test(rawCls);
    const gradeName = rawCls.replace(/\s*\(estimated\)\s*/i, '').trim();
    rows.push(`
      <div class="inh-row">
        <div class="inh-k">Sugar <span class="inh-tag">inherited</span> ${confChip(sw.confidence)}</div>
        <div class="inh-v">
          <b>${lo}–${hi} g/L</b> — <span class="grade">${esc(gradeName)}</span>${estimated ? ` <span class="grade-tag est" title="grade estimated; the range is widened to avoid false precision">estimated</span>` : ''}.
          ${estimated ? '' : ` <span class="inh-adj">Adjust to taste.</span>`}
        </div>
        ${sw.note ? `<div class="inh-note">${esc(sw.note)}</div>` : (estimated ? `<div class="inh-note">the manual leaves the exact amount to taste</div>` : '')}
        <div class="inh-src">From the book's <a href="#/t/sweetening">dosage table</a>${page ? ` (p. ${esc(String(page))})` : ''} · dissolve as the <a href="#/t/sweetening">standard syrup</a>.</div>
      </div>`);
  } else if(sw && res.already_sweetened){
    rows.push(`
      <div class="inh-row">
        <div class="inh-k">Sugar <span class="inh-tag ok">in the recipe</span></div>
        <div class="inh-v">This recipe lists its own sugar, so the book's default dosage isn't added on top.</div>
      </div>`);
  } else {
    // A finished liqueur the pipeline couldn't grade — don't guess a dose.
    rows.push(`<div class="inh-row"><div class="inh-v">The grade couldn't be pinned down here — use the book's general <a href="#/t/sweetening">sweetening table</a> for the style you're after.</div></div>`);
  }

  // Dilution — only when a concrete target strength was resolved.
  const dil = inh.dilution;
  if(dil && dil.to_degrees != null){
    rows.push(`
      <div class="inh-row">
        <div class="inh-k">Strength ${confChip(dil.confidence)}</div>
        <div class="inh-v">Reduce the spirit to <b>${esc(String(dil.to_degrees))}°</b> — see <a href="#/t/dilution">diluting the spirit</a>.</div>
      </div>`);
  }

  // Finishing — techniques the method draws on (sweetening/dilution have their own rows above).
  const chips = finishingChips(inh);
  if(chips.length){
    rows.push(`<div class="inh-row"><div class="inh-k">The method also draws on</div><div class="inh-chips">${chips.join('')}</div></div>`);
  }

  return `<aside class="inh">
    <div class="inh-head">Inherited from the book's method</div>
    ${rows.join('')}
    ${res.rationale ? `<div class="inh-why">Why: ${esc(res.rationale)}</div>` : ''}
  </aside>`;
}

// The original per-yield sugar panel — still the fallback for recipes without a
// resolution. Most recipes state no sugar because the dosage lived in the general
// rules (p. 220), stated once and assumed everywhere.
function sweetPanel(r){
  if(!TQ) return '';
  const ings = r.ingredients||[];
  if(hasSweetIngredient(r)){
    // Recipes that call for "syrup" without saying what syrup IS get the standard formula.
    const syrupOnly = ings.some(i=>/syrup|sciroppo/i.test((i.name_en||'')+' '+(i.name_it||'')))
                   && !ings.some(i=>/sugar|zucchero|honey|miele/i.test((i.name_en||'')+' '+(i.name_it||'')));
    if(!syrupOnly) return '';
    return `<aside class="fix">
      <div class="fix-head">“Syrup” here means the standard syrup</div>
      <p>${esc(TQ.syrup.formula)} <span class="fix-ref">(${esc(TQ.syrup.refs)})</span></p>
      <p class="fix-links"><a href="#/t/sweetening">Sugar &amp; sweetening</a> · <a href="#/t/simple-liqueur">The simple liqueur</a></p>
    </aside>`;
  }
  const litres = (r.yield && r.yield.amount>0 && /^lit/i.test(r.yield.unit||'')) ? r.yield.amount : null;
  const bitter = /bitter|amar[oi]|stomach|digestif|absinthe/i.test((r.cat||'')+' '+(r.title_en||''));
  const rows = TQ.sweetening_table.rows.map(row=>{
    const [lo,hi]=row.g_l;
    const dose = lo===hi ? `~${lo} g/L` : `${lo}–${hi} g/L`;
    const scaled = litres ? (lo===hi ? fmtSugar(lo*litres) : `${fmtSugar(lo*litres)}–${fmtSugar(hi*litres)}`) : '';
    return `<tr title="${esc(row.note)}"><td>${esc(row.cls)}</td><td class="q">${dose}</td>${litres?`<td class="q">${scaled}</td>`:''}</tr>`;
  }).join('');
  return `<aside class="fix">
    <div class="fix-head">Where's the sugar?</div>
    <p>Like most recipes in the manual, this one leaves sweetening to the book's general
       rules — stated once and assumed everywhere${bitter?' (bitters were sweetened sparingly, or not at all — p.&nbsp;10)':''}.
       Choose the grade you're making <span class="fix-ref">(${esc(TQ.sweetening_table.refs)})</span>:</p>
    <div class="tq-tablewrap"><table class="tq-table"><thead><tr><th>Type</th><th>Sugar</th>${litres?`<th>for ${litres} L</th>`:''}</tr></thead><tbody>${rows}</tbody></table></div>
    <p>Dissolve it as the standard syrup: ${esc(TQ.syrup.formula)}</p>
    <p class="fix-links"><a href="#/t/sweetening">Sugar &amp; sweetening</a> · <a href="#/t/quality-classes">The four qualities</a> · <a href="#/t/simple-liqueur">The simple liqueur</a></p>
  </aside>`;
}

// Content blocks in techniques.json are curated by us (not user input), so
// inline <b>/<i> markup inside them is rendered as written.
function tqBlock(b){
  if(b.t==='p') return `<p>${b.x}</p>`;
  if(b.t==='h') return `<h2 class="tq-h">${b.x}</h2>`;
  if(b.t==='note') return `<p class="tq-note">${b.x}</p>`;
  if(b.t==='list') return `<ul class="tq-list">${b.items.map(i=>`<li>${i}</li>`).join('')}</ul>`;
  if(b.t==='table') return `<div class="tq-tablewrap"><table class="tq-table"><thead><tr>${b.cols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${b.rows.map(row=>`<tr>${row.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  return '';
}

function renderTechniques(){
  if(!TQ){ app.innerHTML='<p>Techniques unavailable. <a href="#/">Home</a></p>'; return; }
  const groups = TQ.groups.map(g=>{
    const topics = TQ.topics.filter(t=>t.group===g.id);
    if(!topics.length) return '';
    return `<h2 class="tq-group">${esc(g.title)}</h2>
      <div class="grid">${topics.map(t=>
        `<a class="cat" href="#/t/${t.slug}">
           <span class="count">${esc(t.pages)}</span>
           <h3>${esc(t.title)}</h3>
           <p class="blurb">${esc(t.tagline)}</p>
         </a>`).join('')}</div>`;
  }).join('');
  app.innerHTML =
    `<div class="crumb"><a href="#/">Home</a> › Techniques</div>
     <div class="hero hero-plain">
       <h1>The Techniques</h1>
       <div class="rule"></div>
       <div class="sub">${esc(TQ.meta.subtitle)}</div>
     </div>
     ${groups}
     <p class="tq-src">${esc(TQ.meta.source)}</p>`;
}

function renderTechnique(slug){
  const t = TQ && (TQ.topics||[]).find(x=>x.slug===slug);
  if(!t){ app.innerHTML='<p>Technique not found. <a href="#/techniques">All techniques</a></p>'; return; }
  const i = TQ.topics.indexOf(t);
  const prev = TQ.topics[i-1], next = TQ.topics[i+1];
  const group = (TQ.groups.find(g=>g.id===t.group)||{}).title || 'Technique';
  app.innerHTML =
    `<div class="crumb"><a href="#/">Home</a> › <a href="#/techniques">Techniques</a> › ${esc(t.title)}</div>
     <article class="about tq">
       <div class="sec">${esc(group)} · ${esc(t.pages)}</div>
       <h1>${esc(t.title)}</h1>
       <p class="it">${esc(t.tagline)}</p>
       <div class="rule"></div>
       ${t.blocks.map(tqBlock).join('')}
       <p class="src">From the general chapters of <em>Il Liquorista</em> (${esc(t.pages)} of this edition) ·
         <a href="book.pdf" target="_blank" rel="noopener">check the original</a></p>
     </article>
     <div class="tq-nav">
       ${prev?`<a href="#/t/${prev.slug}">← ${esc(prev.title)}</a>`:'<span></span>'}
       ${next?`<a href="#/t/${next.slug}">${esc(next.title)} →</a>`:''}
     </div>`;
}

function renderAbout(){
  const n = (DB && DB.meta && DB.meta.recipe_count) ? DB.meta.recipe_count.toLocaleString() : 'over 1,400';
  app.innerHTML =
    `<div class="crumb"><a href="#/">Home</a> › About</div>
     <article class="about">
       <div class="sec">About this project</div>
       <h1>Il Liquorista</h1>
       <p class="it">Duemila ricette e procedimenti pratici per la composizione e fabbricazione dei liquori</p>
       <div class="rule"></div>
       <p>For the better part of a century, <em>Il Liquorista</em> was the Italian liqueur-maker's
          bible. It began as Antonio Rossi's <em>Manuale del liquorista</em> (Hoepli, Milan, 1899);
          Dott. Arturo Castoldi then rebuilt it into the encyclopedic manual reproduced here —
          "two thousand recipes and practical procedures for the composition and manufacture of
          liqueurs" — published by Ulrico Hoepli in the famous <em>Manuali Hoepli</em> series,
          with new editions appearing for decades, through at least a seventh in 1950.</p>
       <p>Our copy is the 1921 edition: some seven hundred pages of essences, infusions,
          distillates, ratafias, vermouths and cordials, written for working
          <em>liquoristi</em>. In all that time, it was available only in Italian.</p>
       <p>This site is an experiment in giving the old manual a second life. Using modern AI,
          we translated the text into English and parsed it into the structured, searchable
          database you're browsing — ${n} recipes so far, each linked to its page in the
          original, with quantities that rescale to any batch size. The book's general
          chapters — the rules its recipes silently assume, from sugar dosages to still
          technique — are distilled into <a href="#/techniques">The Techniques</a>.</p>
       <p>It is very much an ongoing project. The translation and the recipe extraction were
          made to the best of our ability (and the machine's — each recipe carries a confidence
          score where we're less sure), and both keep improving. When in doubt, the source of
          truth is a click away: <a href="book.pdf" target="_blank" rel="noopener">the full
          scanned book (PDF)</a>.</p>
       <p class="src">A Kestrel project · original text in the public domain</p>
     </article>`;
}

function recipeList(items){
  return `<div class="rlist">${items.map(r=>
    `<a href="#/r/${r.id}">${esc(r.title_en)}${r.title_it?` <span class="it">${esc(r.title_it)}</span>`:''}</a>`
  ).join('')}</div>`;
}

function renderCategory(name){
  const items = DB.recipes.filter(r=>r.cat===name);
  const c = CATS.find(x=>x.name===name);
  app.innerHTML =
    `<div class="crumb"><a href="#/">Home</a> › ${esc(name)}</div>
     <h1 style="font-variant:small-caps">${esc(name)}</h1>
     ${c&&c.blurb?`<p class="sub" style="color:var(--muted);font-style:italic">${esc(c.blurb)}</p>`:''}
     <p style="color:var(--muted)">${items.length} recipes</p>
     ${recipeList(items)}`;
}

function renderSearch(q){
  const t=q.toLowerCase();
  const items = DB.recipes.filter(r=>
    (r.title_en||'').toLowerCase().includes(t) ||
    (r.title_it||'').toLowerCase().includes(t) ||
    (r.ingredients||[]).some(i=>(i.name_en||'').toLowerCase().includes(t)));
  app.innerHTML =
    `<div class="crumb"><a href="#/">Home</a> › Search</div>
     <h1 style="font-variant:small-caps">“${esc(q)}”</h1>
     <p style="color:var(--muted)">${items.length} matches</p>
     ${items.length?recipeList(items.slice(0,300)):'<p>No recipes found.</p>'}`;
}

function fmt(n){
  if(n>=100) return Math.round(n).toString();
  if(n>=10)  return (Math.round(n*10)/10).toString();
  return (Math.round(n*100)/100).toString();
}

// Which technique page explains each extraction method.
const METHOD_TOPIC = {
  maceration:'maceration', infusion:'maceration', digestion:'maceration',
  decoction:'maceration', distillation:'distillation', essence:'essences',
  cold_mix:'simple-liqueur'
};

// ── Variants (variants.json): alternate preparations of the same liqueur ────
function prettyKind(k){ return (k || '').replace(/_/g, ' ').trim(); }

// "Other ways to make this" — the sibling preparations of one recipe.
function variantsSection(id){
  const v = VAR_BY_ID[id];
  if(!v) return '';
  const g = VAR_GROUPS[v.group];
  if(!g || !g.members) return '';
  const others = g.members.filter(m => m.id !== id);
  if(!others.length) return '';
  const rows = others.map(m => {
    const title = (BY_ID[m.id] && BY_ID[m.id].title_en) || m.title_en || m.id;
    const kind = m.variant_kind ? `<span class="vk">${esc(prettyKind(m.variant_kind))}</span>` : '';
    return `<a class="vrow" href="#/r/${m.id}"><span class="vt">${esc(title)}</span>${kind}</a>`;
  }).join('');
  const total = g.members.length;
  return `<aside class="variants">
    <div class="variants-head">Other ways to make this
      <a class="variants-all" href="#/g/${encodeURIComponent(v.group)}">all ${total} ways →</a>
    </div>
    <div class="vlist">${rows}</div>
  </aside>`;
}

// Browsable "N ways to make X" — the full variant group.
function renderVariantGroup(key){
  const g = VAR_GROUPS[key];
  if(!g || !g.members){ app.innerHTML = '<p>Variant group not found. <a href="#/">Home</a></p>'; return; }
  const title = (BY_ID[g.canonical_id] && BY_ID[g.canonical_id].title_en) || g.members[0].title_en || cap(key);
  const n = g.members.length;
  const rows = g.members.map(m => {
    const t = (BY_ID[m.id] && BY_ID[m.id].title_en) || m.title_en || m.id;
    const kind = m.variant_kind ? `<span class="vk">${esc(prettyKind(m.variant_kind))}</span>` : '';
    const page = m.page ? `<span class="vp">p.&nbsp;${esc(String(m.page))}</span>` : '';
    return `<a class="vrow" href="#/r/${m.id}"><span class="vt">${esc(t)}</span>${kind}${page}</a>`;
  }).join('');
  app.innerHTML =
    `<div class="crumb"><a href="#/">Home</a> › Ways to make ${esc(title)}</div>
     <h1 style="font-variant:small-caps">${n} ways to make ${esc(title)}</h1>
     <p style="color:var(--muted)">The manual gives ${n} preparations under this name — by different methods, or as successive editions refined the formula.</p>
     <div class="vlist vlist-page">${rows}</div>`;
}

function renderRecipe(id){
  const r = BY_ID[id];
  if(!r){ app.innerHTML='<p>Recipe not found. <a href="#/">Home</a></p>'; return; }
  scale = 1;
  const tags=[];
  if(r.method && r.method!=='unknown'){
    const slug = METHOD_TOPIC[r.method];
    const label = cap(r.method).replace('_',' ');
    tags.push(slug&&TQ ? `<a class="tag tag-link" href="#/t/${slug}" title="How ${esc(label.toLowerCase())} works — from the book's general chapters">${esc(label)} ›</a>`
                       : `<span class="tag">${esc(label)}</span>`);
  }
  if(r.alcohol_strength && r.alcohol_strength.degrees) tags.push(`<span class="tag">${esc(String(r.alcohol_strength.degrees))}° spirit</span>`);
  if(r.temperature_c) tags.push(`<span class="tag">${esc(String(r.temperature_c))} °C</span>`);
  if(r.duration && r.duration.amount) tags.push(`<span class="tag">${esc(String(r.duration.amount))} ${esc(r.duration.unit||'')}</span>`);
  if(r.yield && r.yield.amount) tags.push(`<span class="tag">yields ${esc(String(r.yield.amount))} ${esc(r.yield.unit||'')}</span>`);

  app.innerHTML =
    `<div class="crumb"><a href="#/">Home</a> › <a href="#/c/${encodeURIComponent(r.cat)}">${esc(r.cat)}</a></div>
     <article class="recipe">
       <div class="sec">${esc(r.cat)}</div>
       <h1>${esc(r.title_en)}</h1>
       ${r.title_it?`<p class="it">${esc(r.title_it)}</p>`:''}
       ${tags.length?`<div class="meta">${tags.join('')}</div>`:''}
       <div class="scaler">
         <span class="lab">Batch size</span>
         <div class="row" id="presets">
           ${[0.5,1,2,3,5,10].map(m=>`<button data-m="${m}">${m}×</button>`).join('')}
           <span>custom&nbsp;<input id="mult" type="number" min="0.05" step="0.25" value="1">×</span>
         </div>
         <div class="hint">Tap any quantity below to set it to an exact amount — the rest rescale to match.</div>
       </div>
       <table class="ing"><tbody id="ing"></tbody></table>
       ${RES_BY_ID[r.id] ? resolutionPanel(r, RES_BY_ID[r.id]) : sweetPanel(r)}
       ${(r.steps_en&&r.steps_en.length)?`<ol class="steps">${r.steps_en.map(s=>`<li>${esc(s)}</li>`).join('')}</ol>`:''}
       ${r.notes_en?`<p class="notes">${esc(r.notes_en)}</p>`:''}
       <p class="src">Source: page ${r.page}${typeof r.confidence==='number'?` · confidence ${(r.confidence*100|0)}%`:''}</p>
     </article>
     ${variantsSection(r.id)}`;

  const ingBody=$('#ing');
  function drawIng(){
    ingBody.innerHTML = (r.ingredients||[]).map((i,idx)=>{
      let q='';
      if(i.qty==null) q = esc(i.note||'q.b.');
      else {
        q = `<b class="editq" data-i="${idx}">${fmt(i.qty*scale)}</b> ${esc(i.unit||'')}`;
        if(i.variants&&i.variants.length) q += ` <span class="var">(${i.variants.map(v=>fmt(v*scale)).join(' / ')})</span>`;
      }
      return `<tr><td>${esc(i.name_en||i.name_it||'—')}</td><td class="q">${q}</td></tr>`;
    }).join('');
    ingBody.querySelectorAll('.editq').forEach(el=>el.addEventListener('click',()=>{
      const i=r.ingredients[+el.dataset.i]; if(i.qty==null||!i.qty) return;
      const cur=fmt(i.qty*scale);
      const v=prompt(`Set “${i.name_en}” to how many ${i.unit||'units'}?`, cur);
      const num=parseFloat(v); if(num>0){ scale=num/i.qty; setActivePreset(); drawIng(); $('#mult').value=fmt(scale); }
    }));
  }
  function setActivePreset(){
    document.querySelectorAll('#presets button').forEach(b=>
      b.classList.toggle('on', Math.abs(+b.dataset.m-scale)<1e-9));
  }
  $('#presets').addEventListener('click',e=>{
    if(e.target.dataset.m){ scale=+e.target.dataset.m; $('#mult').value=scale; setActivePreset(); drawIng(); }
  });
  $('#mult').addEventListener('input',e=>{ const v=parseFloat(e.target.value); if(v>0){scale=v;setActivePreset();drawIng();} });
  setActivePreset(); drawIng();
}

const cap=s=>s.charAt(0).toUpperCase()+s.slice(1);
function esc(s){return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
boot();
