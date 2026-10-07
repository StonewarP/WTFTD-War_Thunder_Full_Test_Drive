/* WTFTD — pylon loadout editor, laid out like the in-game one:
   rows = presets (first row: your custom loadout), columns = pylons, cells = weapon icons.
   cfg.pylons = { slot: "<official option name>" | { w: "<catalog weapon key>", n: count } } */
'use strict';

const WCATS = ['aam_ir', 'aam_radar', 'agm', 'atgm', 'rockets', 'bombs', 'guided_bombs', 'nuke', 'torpedoes', 'mines', 'fuel', 'pods'];
const NEEDS = { radar: 'need.radar', laser: 'need.laser', saclos: 'need.saclos', tv: 'need.tv' };
const LP = { slot: null, q: '', cat: '', nonStd: false, weapons: null, loading: null };

const ammoIcon = ic => (ic ? `<img class="wicon" src="/img/ammo/${encodeURIComponent(ic)}.png" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'wicon-ph'}))">` : '<span class="wicon-ph"></span>');

async function loadWeapons() {
  if (LP.weapons) return LP.weapons;
  if (!LP.loading) LP.loading = getData('weapons.json').then(w => { LP.weapons = w; return w; }).catch(() => ({}));
  return LP.loading;
}

function slotsSorted(d) { return [...(d.sl || [])].sort((a, b) => (a.t ?? a.i) - (b.t ?? b.i)); }
function slotOption(d, slotIdx, name) { return (d.sl || []).find(s => s.i === slotIdx)?.o.find(o => o.n === name); }

function needWarning(d, g) {
  if (!NEEDS[g]) return '';
  return (d.cap || []).includes(g) ? '' : t(NEEDS[g]);
}

// one cell of the grid for a pylon value (official option name or catalog pick)
function cellHTML(d, slot, val, editable, active) {
  let inner = '', title = t('ammo.empty'), warn = '';
  if (typeof val === 'string' && val) {
    const o = slotOption(d, slot.i, val);
    if (o) { inner = ammoIcon(o.ic); title = o.w.map(([k, n]) => `${n}× ${I18N.weapon(k)}`).join(', '); }
  } else if (val && typeof val === 'object') {
    const w = LP.weapons?.[val.w];
    if (w) {
      inner = ammoIcon(w.ic) + (val.n > 1 ? `<span class="wcount">${val.n}</span>` : '');
      title = `${val.n || 1}× ${I18N.weapon(val.w)}`;
      warn = needWarning(d, w.g);
    }
  }
  const cls = ['lcell', editable ? 'edit' : '', active ? 'active' : '', val && typeof val === 'object' ? 'nonstd' : '', warn ? 'warn' : ''].join(' ');
  return editable
    ? `<button class="${cls}" data-lcell="${slot.i}" title="${esc(title + (warn ? ' — ⚠ ' + warn : ''))}">${inner}${warn ? '<i class="lwarn">!</i>' : ''}</button>`
    : `<span class="${cls}" title="${esc(title)}">${inner}</span>`;
}

function loadoutGridHTML(v, d) {
  if (!LP.weapons) { loadWeapons().then(() => { if (S.sel) renderDrawer(); }); }
  const c = S.cfg;
  const slots = slotsSorted(d);
  const custom = !!c.pylons;
  const head = `<div class="lrow lhead"><span class="llabel"></span>${slots.map(s => `<span class="lcol">${s.i}</span>`).join('')}</div>`;
  const customRow = custom ? `<div class="lrow lcustom active"><span class="llabel">${icon('sliders', 'ic-sm')} ${esc(t('loadout.customRow'))}</span>
      ${slots.map(s => cellHTML(d, s, c.pylons[s.i], true, LP.slot === s.i)).join('')}</div>` : '';
  const presetRows = d.pr.filter(p => p.s || !p.w.length).map(p => {
    const active = !custom && c.preset === p.id;
    return `<div class="lrow${active ? ' active' : ''}" data-lrow="${esc(p.id)}" title="${esc(custom ? t('loadout.copyPreset') : t('loadout.usePreset'))}">
      <span class="llabel">${esc(presetLabel(v, p))}</span>
      ${slots.map(s => cellHTML(d, s, (p.s || {})[s.i], false, false)).join('')}</div>`;
  }).join('');
  const grid = `<div class="lgrid" style="--lcols:${slots.length}">${head}${customRow}${presetRows}</div>`;
  const toggle = cdkOn()
    ? `<label class="switch" style="margin:2px 0 8px"><input type="checkbox" data-bind-cfg="customPylons" ${custom ? 'checked' : ''}><span class="sw"></span><span>${esc(t('loadout.custom'))}</span></label>`
    : `<p class="hint">${esc(t('loadout.note'))}</p>`;
  return toggle + `<div class="lgrid-wrap">${grid}</div>` + (custom && LP.slot != null ? pickerHTML(v, d) : '') + (custom ? summaryHTML(d) : `<p class="hint" style="margin-top:8px">${esc(t('loadout.gridHint'))}</p>`);
}

function summaryHTML(d) {
  const rows = [];
  for (const s of slotsSorted(d)) {
    const val = S.cfg.pylons[s.i];
    if (!val) continue;
    if (typeof val === 'string') {
      const o = slotOption(d, s.i, val);
      if (o) rows.push(`<li><b>${s.i}</b>${ammoIcon(o.ic)}<span>${esc(o.w.map(([k, n]) => `${n}× ${I18N.weapon(k)}`).join(', '))}</span></li>`);
    } else {
      const w = LP.weapons?.[val.w];
      const warn = w ? needWarning(d, w.g) : '';
      rows.push(`<li class="${warn ? 'warn' : ''}"><b>${s.i}</b>${ammoIcon(w?.ic)}<span>${val.n || 1}× ${esc(I18N.weapon(val.w))} <i class="chip dim">${esc(t('loadout.nonStd'))}</i>${warn ? `<em>⚠ ${esc(warn)}</em>` : ''}</span></li>`);
    }
  }
  return rows.length ? `<ul class="lsummary">${rows.join('')}</ul>` : `<p class="hint" style="margin-top:8px">${esc(t('loadout.pickHint'))}</p>`;
}

function pickerHTML(v, d) {
  const slot = (d.sl || []).find(s => s.i === LP.slot);
  if (!slot) return '';
  const cur = S.cfg.pylons[slot.i];
  const cats = WCATS.filter(cat => slot.o.some(o => o.c === cat) || (LP.nonStd && LP.weapons && Object.values(LP.weapons).some(w => w.c === cat)));
  const countBox = cur && typeof cur === 'object'
    ? `<label class="lcount">${esc(t('editor.count'))} <input type="number" min="1" max="8" value="${cur.n || 1}" data-lcount></label>` : '';
  return `<div class="lpicker">
    <div class="lp-head"><b>${esc(t('loadout.pylon', { n: slot.i }))}</b>${countBox}
      <button class="btn btn-ghost btn-sm" data-lempty>${esc(t('ammo.empty'))}</button>
      <button class="icon-btn" data-lclose title="${esc(t('action.close'))}">${icon('x', 'ic-sm')}</button></div>
    <div class="lp-tools">
      <label class="search lp-search">${icon('search')}<input type="search" data-lsearch value="${esc(LP.q)}" placeholder="${esc(t('loadout.searchWeapon'))}" autocomplete="off"></label>
      <label class="switch"><input type="checkbox" data-lnonstd ${LP.nonStd ? 'checked' : ''}><span class="sw"></span><span>${esc(t('loadout.showNonStd'))}</span></label>
    </div>
    <div class="lp-cats"><button class="chipbtn${!LP.cat ? ' active' : ''}" data-lcat="">${esc(t('cat.all'))}</button>
      ${cats.map(cat => `<button class="chipbtn${LP.cat === cat ? ' active' : ''}" data-lcat="${cat}">${esc(t('wcat.' + cat))}</button>`).join('')}</div>
    <div class="lp-list" id="lpList">${pickerListHTML(d, slot)}</div>
  </div>`;
}

function pickerListHTML(d, slot) {
  const q = norm(LP.q);
  const cur = S.cfg.pylons[slot.i];
  const groups = {};
  // standard options of this pylon
  for (const o of slot.o) {
    const cat = o.c || 'other';
    if (LP.cat && cat !== LP.cat) continue;
    const label = o.w.map(([k, n]) => `${n}× ${I18N.weapon(k)}`).join(', ');
    if (q && !norm(label + ' ' + o.n).includes(q)) continue;
    (groups[cat] ||= { std: [], ext: [] }).std.push(`<button class="lp-item${cur === o.n ? ' active' : ''}" data-lpick="${esc(o.n)}">${ammoIcon(o.ic)}<span>${esc(label)}</span><i class="chip info">${esc(t('loadout.standard'))}</i></button>`);
  }
  // any weapon of the game
  if (LP.nonStd && LP.weapons) {
    const counts = {};
    for (const [k, w] of Object.entries(LP.weapons)) {
      if (LP.cat && w.c !== LP.cat) continue;
      const name = I18N.weapon(k);
      if (q && !norm(name + ' ' + k).includes(q)) continue;
      counts[w.c] = (counts[w.c] || 0) + 1;
      if (counts[w.c] > (q || LP.cat ? 80 : 12)) continue;
      const warn = needWarning(d, w.g);
      const sel = cur && typeof cur === 'object' && cur.w === k;
      (groups[w.c] ||= { std: [], ext: [] }).ext.push(`<button class="lp-item${sel ? ' active' : ''}${warn ? ' warn' : ''}" data-lpickw="${esc(k)}" title="${esc(warn)}">
        ${ammoIcon(w.ic)}<span>${esc(name)}</span>${w.g ? `<i class="chip dim">${esc(t('guide.' + w.g))}</i>` : ''}${warn ? '<i class="lwarn">!</i>' : ''}</button>`);
    }
    for (const [cat, n] of Object.entries(counts)) {
      const shown = q || LP.cat ? 80 : 12;
      if (n > shown && groups[cat]) groups[cat].ext.push(`<p class="hint lp-more">${esc(t('loadout.more', { n: n - shown }))}</p>`);
    }
  }
  const order = [...WCATS, 'other'];
  const html = order.filter(cat => groups[cat]).map(cat => `<div class="lp-group"><div class="opt-group-title">${esc(I18N.tOr('wcat.' + cat, cat))}</div>
      ${groups[cat].std.join('')}${groups[cat].ext.join('')}</div>`).join('');
  return html || `<p class="hint">${esc(t('results.empty'))}</p>`;
}

// ------------------------------------------------------------------ events (called from the drawer handlers)
function loadoutClick(b, v, d) {
  const c = S.cfg;
  if (b.dataset.lcell !== undefined) { LP.slot = LP.slot === +b.dataset.lcell ? null : +b.dataset.lcell; LP.q = ''; return true; }
  if (b.dataset.lclose !== undefined) { LP.slot = null; return true; }
  if (b.dataset.lempty !== undefined) { delete c.pylons[LP.slot]; return true; }
  if (b.dataset.lpick) { c.pylons[LP.slot] = b.dataset.lpick; return true; }
  if (b.dataset.lpickw) { c.pylons[LP.slot] = { w: b.dataset.lpickw, n: 1 }; return true; }
  if (b.dataset.lcat !== undefined) { LP.cat = b.dataset.lcat; return true; }
  return false;
}

function loadoutRowClick(row, v, d) {
  const c = S.cfg, p = d.pr.find(x => x.id === row.dataset.lrow);
  if (!p) return;
  if (c.pylons) c.pylons = Object.fromEntries(Object.entries(p.s || {}).map(([k, val]) => [+k, val]));  // copy into custom
  else c.preset = p.id;
}

function loadoutChange(el) {
  const c = S.cfg;
  if (el.dataset.lnonstd !== undefined) { LP.nonStd = el.checked; return true; }
  if (el.dataset.lcount !== undefined) {
    const cur = c.pylons[LP.slot];
    if (cur && typeof cur === 'object') cur.n = Math.max(1, Math.min(8, +el.value || 1));
    return true;
  }
  return false;
}

function loadoutInput(el) {
  if (el.dataset.lsearch === undefined) return false;
  LP.q = el.value;
  const d = S.details.get(S.sel.id);
  const slot = (d.sl || []).find(s => s.i === LP.slot);
  if (slot) $('#lpList').innerHTML = pickerListHTML(d, slot);
  return true;
}
