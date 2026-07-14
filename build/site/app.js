'use strict';
const $ = (s, r=document) => r.querySelector(s);
const app = $('#app');
let DB = null, TAX = null, BY_ID = {}, CATS = [], scale = 1;

async function boot(){
  const [rec, tax] = await Promise.all([
    fetch('recipes.json').then(r=>r.json()),
    fetch('taxonomy.json').then(r=>r.ok?r.json():null).catch(()=>null),
  ]);
  DB = rec; TAX = tax;
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
  if(h.startsWith('c/')) return renderCategory(h.slice(2));
  if(h.startsWith('search/')) return renderSearch(h.slice(7));
  renderHome();
}

function renderHome(){
  app.innerHTML =
    `<div class="hero"><h1>The Liqueurist</h1>
       <div class="rule"></div>
       <div class="sub">${DB.meta.subtitle} · ${DB.meta.author}</div></div>
     <div class="grid">${CATS.map(c=>
       `<a class="cat" href="#/c/${encodeURIComponent(c.name)}">
          <span class="count">${c.count} recipes</span>
          <h3>${esc(c.name)}</h3>
          ${c.blurb?`<p class="blurb">${esc(c.blurb)}</p>`:''}
        </a>`).join('')}</div>`;
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

function renderRecipe(id){
  const r = BY_ID[id];
  if(!r){ app.innerHTML='<p>Recipe not found. <a href="#/">Home</a></p>'; return; }
  scale = 1;
  const tags=[];
  if(r.method && r.method!=='unknown') tags.push(cap(r.method));
  if(r.alcohol_strength && r.alcohol_strength.degrees) tags.push(`${r.alcohol_strength.degrees}° spirit`);
  if(r.temperature_c) tags.push(`${r.temperature_c} °C`);
  if(r.duration && r.duration.amount) tags.push(`${r.duration.amount} ${r.duration.unit||''}`);
  if(r.yield && r.yield.amount) tags.push(`yields ${r.yield.amount} ${r.yield.unit||''}`);

  app.innerHTML =
    `<div class="crumb"><a href="#/">Home</a> › <a href="#/c/${encodeURIComponent(r.cat)}">${esc(r.cat)}</a></div>
     <article class="recipe">
       <div class="sec">${esc(r.cat)}</div>
       <h1>${esc(r.title_en)}</h1>
       ${r.title_it?`<p class="it">${esc(r.title_it)}</p>`:''}
       ${tags.length?`<div class="meta">${tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div>`:''}
       <div class="scaler">
         <span class="lab">Batch size</span>
         <div class="row" id="presets">
           ${[0.5,1,2,3,5,10].map(m=>`<button data-m="${m}">${m}×</button>`).join('')}
           <span>custom&nbsp;<input id="mult" type="number" min="0.05" step="0.25" value="1">×</span>
         </div>
         <div class="hint">Tap any quantity below to set it to an exact amount — the rest rescale to match.</div>
       </div>
       <table class="ing"><tbody id="ing"></tbody></table>
       ${(r.steps_en&&r.steps_en.length)?`<ol class="steps">${r.steps_en.map(s=>`<li>${esc(s)}</li>`).join('')}</ol>`:''}
       ${r.notes_en?`<p class="notes">${esc(r.notes_en)}</p>`:''}
       <p class="src">Source: page ${r.page}${typeof r.confidence==='number'?` · confidence ${(r.confidence*100|0)}%`:''}</p>
     </article>`;

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
