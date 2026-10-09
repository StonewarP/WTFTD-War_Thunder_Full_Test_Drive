/* WTFTD — My weapons: modified copies of the game's pylon weapons (more explosive, thrust, G, a nuclear charge…).
   Made from the Weapons tab (Modify), kept in user/weapons.json, put on pylons from the loadout picker:
   cfg.pylons[slot] = { w: "<catalog key>", n, cw: "<my weapon id>", nm, mod } (the server uses the weapon's current mod).
   A modified weapon = a file of its own written with the custom aircraft (cdk._custom_weapon).
   Editor: Simple (a few values in friendly units) and Advanced (every value of the weapon file, mod.adv). */
'use strict';

const MW = { list: [], edit: null };

// Simple fields: the weapon's value (server weapon_base, datamine units) shown in a friendlier unit
const WE_FIELDS = [
  { k: 'e', unit: 'kg', min: 0, max: 1e6 },
  { k: 'kt', unit: 'kt', min: 0, max: 1e5, kinds: ['bomb', 'rocket'] },  // shown even when the weapon has none
  { k: 'force', unit: 'kN', scale: 1000, min: 0, max: 1e4 },
  { k: 'burn', unit: 's', min: 0, max: 600 },
  { k: 'mach', unit: 'Mach', min: 0.1, max: 50 },
  { k: 'g', unit: 'G', min: 1, max: 1000 },
  { k: 'range', unit: 'km', scale: 1000, min: 0, max: 1000 },
  { k: 'mass', unit: 'kg', min: 0.1, max: 1e6 },
];
const ADV_TEXT = /^[A-Za-z0-9_\-./ ]{0,120}$/;  // as cdk.ADV_TEXT
const weShown = (f, base) => (f.kinds ? f.kinds.includes(base.kind) : base[f.k] != null) && (f.k !== 'g' || base.guided);
const weRound = x => Math.round(x * 1000) / 1000;
const weOrig = (f, base) => (base[f.k] ?? 0) / (f.scale || 1);  // in the field's unit

async function loadMyWeapons() {
  try { MW.list = await api('myweapons'); } catch { MW.list = []; }
  if (!Array.isArray(MW.list)) MW.list = [];
  $('#myWeaponCount').textContent = MW.list.length || '';
}
async function persistMyWeapons() {
  $('#myWeaponCount').textContent = MW.list.length || '';
  try { await api('myweapons', { weapons: MW.list }); } catch (e) { toastErr(e); }
}

const myWeaponName = cw => cw.name || I18N.weapon(cw.w);

// "Explosive 3.58 → 500 kg" for each change, from the values saved with the weapon
function myWeaponChanges(cw) {
  const adv = Object.keys(cw.mod?.adv || {}).length;
  return WE_FIELDS.filter(f => cw.mod?.[f.k] != null).map(f => {
    const now = weRound(cw.mod[f.k] / (f.scale || 1));
    const was = cw.base?.[f.k] != null ? weRound(cw.base[f.k] / (f.scale || 1)) : null;
    return `<span class="chip dim">${esc(t('myw.f.' + f.k))} ${was != null ? `${esc(I18N.num(was))} → ` : ''}<b>${esc(I18N.num(now))}</b> ${esc(f.unit)}</span>`;
  }).join('') + (adv ? `<span class="chip dim">${esc(t('myw.advChanges', { n: adv }))}</span>` : '');
}

function renderMyWeapons() {
  const el = $('#myWeaponList');
  if (!MW.list.length) { el.innerHTML = `<div class="empty">${icon('ammo', 'ic-xl')}<p>${esc(t('myw.empty'))}</p></div>`; return; }
  el.innerHTML = MW.list.map(cw => `<div class="list-item">
      <div class="list-thumb mw-thumb">${ammoIcon(cw.ic)}</div>
      <div class="list-main"><div class="list-title">${cw.mod?.kt ? '☢ ' : ''}${esc(myWeaponName(cw))}</div>
        <div class="list-sub">${esc(t('myw.basedOn', { name: I18N.weapon(cw.w) }))}</div>
        <div class="mw-changes">${myWeaponChanges(cw)}</div></div>
      <div class="list-actions">
        <button class="btn btn-sm" data-mwedit="${esc(cw.id)}">${icon('sliders', 'ic-sm')}<span>${esc(t('myw.edit'))}</span></button>
        <button class="icon-btn btn-danger" data-mwdel="${esc(cw.id)}" title="${esc(t('action.delete'))}">${icon('trash')}</button></div></div>`).join('');
}

// ------------------------------------------------------------------ editor
// from the Weapons tab: { key, item } (catalog key + armament item); from My weapons: { cw }
async function openWeaponEditor({ key, item = null, cw = null }) {
  key = cw?.w || key;
  let base;
  try { base = await api('weapon-base/' + encodeURIComponent(key)); } catch { toast({ title: t('myw.noBase'), err: true }); return; }
  const vals = {};
  for (const f of WE_FIELDS.filter(f => weShown(f, base))) {
    const saved = cw?.mod?.[f.k];
    vals[f.k] = weRound(saved != null ? saved / (f.scale || 1) : weOrig(f, base));
  }
  const tree = (base.tree || []).map(([path, type, value]) => ({ path, type, value }));
  const known = new Set(tree.map(x => x.path));
  const adv = Object.fromEntries(Object.entries(cw?.mod?.adv || {}).filter(([p]) => known.has(p)).map(([p, tv]) => [p, tv.v]));
  const wname = item ? arName(item) : I18N.weapon(key);
  MW.edit = { key, base, cw, vals, tree, adv, tab: 'simple', q: '', changedOnly: false,
    ic: cw?.ic || item?.ic || LP.weapons?.[key]?.ic || '', c: cw?.c || LP.weapons?.[key]?.c || '',
    name: cw?.name || t('myw.defaultName', { name: wname }) };
  $('#weTitle').textContent = t('myw.editTitle', { name: wname });
  renderWeaponEditor();
  $('#dlgWeaponEdit').showModal();
}

function renderWeaponEditor() {
  const ed = MW.edit;
  const nAdv = Object.keys(ed.adv).length;
  $('#weBody').innerHTML = `
    <label class="we-name"><span>${esc(t('myw.name'))}</span><input type="text" id="weName" value="${esc(ed.name)}" maxlength="80" spellcheck="false"></label>
    <div class="we-tabs" role="tablist">
      <button type="button" class="we-tab${ed.tab === 'simple' ? ' active' : ''}" data-wetab="simple">${esc(t('myw.simple'))}</button>
      <button type="button" class="we-tab${ed.tab === 'adv' ? ' active' : ''}" data-wetab="adv">${esc(t('myw.advanced', { n: ed.tree.length }))}<span class="tab-count" id="weAdvCount">${nAdv || ''}</span></button>
    </div>
    ${ed.tab === 'simple' ? simpleEditorHTML() : advEditorHTML()}`;
}

function simpleEditorHTML() {
  const { base, vals } = MW.edit;
  const fields = WE_FIELDS.filter(f => weShown(f, base));
  const presets = ['x2', 'x10', 'absurd', ...(fields.some(f => f.k === 'kt') ? ['nuke'] : []), 'reset'];
  return `<div class="we-presets"><span class="ar-lbl">${esc(t('myw.presets'))}</span>
      ${presets.map(p => `<button type="button" class="chipbtn" data-wepreset="${p}">${esc(t('myw.p.' + p))}</button>`).join('')}</div>
    <div class="we-rows">${fields.map(f => {
      const orig = weRound(weOrig(f, base));
      const changed = Math.abs((vals[f.k] ?? 0) - orig) > 1e-9;
      const hint = I18N.tOr('myw.h.' + f.k, '');
      return `<div class="we-row${changed ? ' changed' : ''}" title="${esc(hint)}">
        <div class="we-lbl"><b>${esc(t('myw.f.' + f.k))}</b><small>${esc(hint)}</small></div>
        <span class="we-orig">${esc(t('myw.original', { value: f.k === 'kt' && !orig ? t('myw.none') : `${I18N.num(orig)} ${f.unit}` }))}</span>
        <label class="we-in"><input type="number" step="any" min="${f.min}" max="${f.max}" value="${vals[f.k]}" data-wefield="${f.k}"><i>${esc(f.unit)}</i></label>
        <span class="we-quick">${f.k === 'kt' ? [5, 30, 1600].map(x => `<button type="button" class="chipbtn" data-weset="${f.k}" data-v="${x}">${x}</button>`).join('')
          : [2, 5, 10].map(x => `<button type="button" class="chipbtn" data-wemul="${f.k}" data-v="${x}">×${x}</button>`).join('')}
          <button type="button" class="icon-btn" data-wereset="${f.k}" title="${esc(t('myw.p.reset'))}">${icon('refresh', 'ic-sm')}</button></span></div>`;
    }).join('')}</div>
    <p class="hint">${esc(t('myw.editHint'))}</p>`;
}

// ------------------------------------------------------------------ advanced: every value of the weapon file
const advFmt = (type, v) => type === 'b' ? (v ? 'yes' : 'no') : Array.isArray(v) ? v.map(x => weRound(x)).join(', ') : type === 't' ? v : String(weRound(v));
const advSame = (type, a, b) => Array.isArray(a) ? Array.isArray(b) && a.length === b.length && a.every((x, i) => Math.abs(x - b[i]) < 1e-9)
  : type === 'r' || type === 'i' ? Math.abs(a - b) < 1e-9 : a === b;
const advName = path => path.split('/').pop();
const advHelp = x => I18N.tOr('mywk.' + advName(x.path), '') || t('myw.advUnknown', { path: x.path, value: advFmt(x.type, x.value) });
const advBlock = path => {  // "rocket/guidance/opticalSeeker" -> "Missile / rocket › Guidance › IR / optical seeker"
  if (!path) return '—';
  return path.split('/').map(b => I18N.tOr('mywb.' + b, b)).join(' › ');
};

function advEditorHTML() {
  const ed = MW.edit;
  return `<p class="hint we-advhint">${esc(t('myw.advHint'))}</p>
    <div class="we-advtools">
      <label class="search">${icon('search')}<input type="search" id="weAdvSearch" value="${esc(ed.q)}" placeholder="${esc(t('myw.advSearch'))}" autocomplete="off" spellcheck="false"></label>
      <label class="switch"><input type="checkbox" id="weAdvChanged"${ed.changedOnly ? ' checked' : ''}><span class="sw"></span><span>${esc(t('myw.advChangedOnly'))}</span></label>
    </div>
    <div class="we-advlist" id="weAdvList">${advListHTML()}</div>`;
}

function advListHTML() {
  const ed = MW.edit;
  const q = norm(ed.q);
  const groups = new Map();
  for (const x of ed.tree) {
    if (ed.changedOnly && !(x.path in ed.adv)) continue;
    const block = x.path.includes('/') ? x.path.slice(0, x.path.lastIndexOf('/')) : '';
    if (q && !norm(x.path + ' ' + I18N.tOr('mywk.' + advName(x.path), '') + ' ' + advBlock(block)).includes(q)) continue;
    if (!groups.has(block)) groups.set(block, []);
    groups.get(block).push(x);
  }
  if (!groups.size) return `<p class="hint">${esc(t('results.empty'))}</p>`;
  return [...groups].map(([block, rows]) => `<div class="we-advgroup"><div class="opt-group-title" title="${esc(block)}">${esc(advBlock(block))}</div>
    ${rows.map(advRowHTML).join('')}</div>`).join('');
}

function advRowHTML(x) {
  const ed = MW.edit;
  const changed = x.path in ed.adv;
  const v = changed ? ed.adv[x.path] : x.value;
  const help = advHelp(x);
  const attrs = `data-weadv="${esc(x.path)}" data-t="${x.type}"`;
  const input = x.type === 'b' ? `<label class="switch"><input type="checkbox" ${attrs}${v ? ' checked' : ''}><span class="sw"></span></label>`
    : x.type === 'r' || x.type === 'i' ? `<input type="number" step="${x.type === 'i' ? 1 : 'any'}" value="${v}" ${attrs}>`
      : `<input type="text" value="${esc(advFmt(x.type, v))}" ${attrs} spellcheck="false">`;
  return `<div class="we-arow${changed ? ' changed' : ''}" title="${esc(help)}">
    <div class="we-alb"><code>${esc(advName(x.path))}</code><small>${esc(I18N.tOr('mywk.' + advName(x.path), ''))}</small></div>
    <span class="we-orig">${esc(t('myw.original', { value: advFmt(x.type, x.value) }))}</span>
    <span class="we-ain">${input}</span>
    <button type="button" class="icon-btn" data-weadvreset="${esc(x.path)}" title="${esc(t('myw.p.reset'))}"${changed ? '' : ' disabled'}>${icon('refresh', 'ic-sm')}</button></div>`;
}

// an input's value in the file's type, undefined when not valid
function advParse(el) {
  const type = el.dataset.t;
  if (type === 'b') return el.checked;
  if (type === 'r' || type === 'i') {
    if (el.value === '') return undefined;
    const x = type === 'i' ? Math.round(+el.value) : +el.value;
    return Number.isFinite(x) ? x : undefined;
  }
  if (type === 't') return ADV_TEXT.test(el.value) ? el.value : undefined;
  const parts = el.value.split(/[,;\s]+/).filter(Boolean).map(Number);
  return parts.length === +type.slice(1) && parts.every(Number.isFinite) ? parts : undefined;
}

function advInput(el) {
  const ed = MW.edit, path = el.dataset.weadv;
  const x = ed.tree.find(r => r.path === path);
  if (!x) return;
  const v = advParse(el);
  el.classList.toggle('bad', v === undefined);
  if (v === undefined) return;
  if (advSame(x.type, v, x.value)) delete ed.adv[path]; else ed.adv[path] = v;
  const row = el.closest('.we-arow');
  row.classList.toggle('changed', path in ed.adv);
  row.querySelector('[data-weadvreset]').disabled = !(path in ed.adv);
  $('#weAdvCount').textContent = Object.keys(ed.adv).length || '';
}

// ------------------------------------------------------------------ simple: presets, saving
function weClamp(f, x) { return weRound(Math.min(f.max, Math.max(f.min, +x || 0))); }

function wePreset(p) {
  const { base, vals } = MW.edit;
  const fields = WE_FIELDS.filter(f => weShown(f, base));
  for (const f of fields) {
    const orig = weOrig(f, base);
    if (p === 'reset') vals[f.k] = weRound(orig);
    else if (p === 'nuke') { if (f.k === 'kt') vals.kt = 20; }
    else if (f.k === 'kt' || f.k === 'mass') continue;  // never by a multiplier: the weight makes it slower
    else if (p === 'x2' || p === 'x10') vals[f.k] = weClamp(f, orig * (p === 'x2' ? 2 : 10));
    else if (p === 'absurd') {  // what r11 showed in game: very fast, 100 G turns, huge blast
      const target = { e: orig * 100, force: orig * 5, burn: orig * 2, mach: Math.max(orig, 6), g: Math.max(orig, 100), range: orig * 3 }[f.k];
      if (target != null) vals[f.k] = weClamp(f, target);
    }
  }
}

// the changes to save, in the weapon file's units; G also raises the autopilot and the fins (the turn needs all three)
function weMod() {
  const { base, vals, adv, tree } = MW.edit;
  const mod = {};
  for (const f of WE_FIELDS.filter(f => weShown(f, base))) {
    const v = weClamp(f, vals[f.k]);
    if (f.k === 'kt') { if (v > 0 && Math.abs(v - (base.kt || 0)) > 1e-9) mod.kt = v; continue; }
    if (Math.abs(v - weRound(weOrig(f, base))) > 1e-9) mod[f.k] = weRound(v * (f.scale || 1));
  }
  if (mod.g != null) {
    if (base.gReq != null) mod.gReq = mod.g;
    if (base.fins != null && base.g) mod.fins = weRound(Math.min(1000, base.fins * mod.g / base.g));
  }
  const types = new Map(tree.map(x => [x.path, x.type]));
  const a = Object.fromEntries(Object.entries(adv).filter(([p]) => types.has(p)).map(([p, v]) => [p, { t: types.get(p), v }]));
  if (Object.keys(a).length) mod.adv = a;
  return mod;
}

async function saveWeaponEditor() {
  const ed = MW.edit;
  const mod = weMod();
  if (!Object.keys(mod).length) { toast({ title: t('myw.noChange'), err: true, ms: 3500 }); return false; }
  const name = ($('#weName').value || '').trim().slice(0, 80) || ed.name;
  const snapshot = Object.fromEntries(WE_FIELDS.filter(f => ed.base[f.k] != null).map(f => [f.k, ed.base[f.k]]));
  const cw = ed.cw || { id: newId(), w: ed.key, created: Date.now() };
  Object.assign(cw, { name, ic: ed.ic, c: ed.c, mod, base: snapshot, at: Date.now() });
  if (!ed.cw) MW.list.unshift(cw);
  await persistMyWeapons();
  renderMyWeapons();
  if (S.sel) renderDrawer();  // its pylons may hold it
  toast({ title: t('myw.saved', { name }), ms: 5000,
    actions: $('#view-myweapons').classList.contains('hidden') ? [{ label: t('myw.open'), primary: true, run: () => showView('myweapons') }] : [] });
  return true;
}

function bindMyWeapons() {
  loadMyWeapons();
  $('#myWeaponList').addEventListener('click', async e => {
    const b = e.target.closest('button');
    if (!b) return;
    const cw = MW.list.find(x => x.id === (b.dataset.mwedit || b.dataset.mwdel));
    if (!cw) return;
    if (b.dataset.mwedit) openWeaponEditor({ cw });
    else {
      MW.list = MW.list.filter(x => x !== cw);
      await persistMyWeapons();
      renderMyWeapons();
      toast({ title: t('myw.deleted', { name: myWeaponName(cw) }), ms: 3000 });
    }
  });
  const dlg = $('#dlgWeaponEdit');
  dlg.addEventListener('click', e => {
    const b = e.target.closest('button[type=button]');
    if (!b || !MW.edit) return;
    const ed = MW.edit;
    ed.name = $('#weName').value;
    if (b.dataset.wetab) { ed.tab = b.dataset.wetab; return renderWeaponEditor(); }
    if (b.dataset.weadvreset) { delete ed.adv[b.dataset.weadvreset]; $('#weAdvList').innerHTML = advListHTML(); $('#weAdvCount').textContent = Object.keys(ed.adv).length || ''; return; }
    const f = WE_FIELDS.find(x => x.k === (b.dataset.wemul || b.dataset.weset || b.dataset.wereset));
    if (b.dataset.wepreset) wePreset(b.dataset.wepreset);
    else if (f && b.dataset.wemul) ed.vals[f.k] = weClamp(f, weOrig(f, ed.base) * +b.dataset.v);
    else if (f && b.dataset.weset) ed.vals[f.k] = weClamp(f, +b.dataset.v);
    else if (f && b.dataset.wereset !== undefined) ed.vals[f.k] = weRound(weOrig(f, ed.base));
    else return;
    renderWeaponEditor();
  });
  dlg.addEventListener('input', e => {
    const el = e.target, ed = MW.edit;
    if (!ed) return;
    if (el.id === 'weName') { ed.name = el.value; return; }
    if (el.id === 'weAdvSearch') { ed.q = el.value; $('#weAdvList').innerHTML = advListHTML(); return; }
    if (el.dataset.weadv && el.type !== 'checkbox') return advInput(el);
    const k = el.dataset.wefield;
    if (!k) return;
    ed.vals[k] = el.value === '' ? 0 : +el.value;
    const f = WE_FIELDS.find(x => x.k === k);
    el.closest('.we-row').classList.toggle('changed', Math.abs(ed.vals[k] - weRound(weOrig(f, ed.base))) > 1e-9);
  });
  dlg.addEventListener('change', e => {
    const el = e.target, ed = MW.edit;
    if (!ed) return;
    if (el.id === 'weAdvChanged') { ed.changedOnly = el.checked; $('#weAdvList').innerHTML = advListHTML(); return; }
    if (el.dataset.weadv && el.type === 'checkbox') advInput(el);
  });
  $('#weForm').addEventListener('submit', async e => {
    if (e.submitter?.value !== 'ok') return;
    e.preventDefault();
    if (await saveWeaponEditor()) dlg.close();
  });
}
