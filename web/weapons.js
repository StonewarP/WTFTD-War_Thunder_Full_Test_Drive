/* WTFTD — Weapons page: missiles, bombs, rockets and torpedoes of the game, their stats, what they're best at,
   side-by-side comparison and the vehicles that carry them. Data: data/armament.json (wtftd/armament.py). */
'use strict';

const AR = {
  data: null, byId: new Map(), cat: 'aam_ir', q: '', g: '', nat: '', use: '', sort: 'br', dir: 1,
  open: '', cmp: (store.get('wcmp', []) || []).filter(x => typeof x === 'string').slice(0, 5), guide: store.get('wguide', 1) !== 0,
};

// stat columns: unit formatter + which way is better (1 higher, -1 lower, 0 neither)
const AR_COLS = {
  v: { better: 1 }, gl: { better: 1, f: x => `${x} G` }, ob: { better: 1, f: x => `${x}°` }, trk: { better: 1, f: x => `${x}°/s` },
  lk: { better: 1, f: km }, aa: { better: 1, f: km }, rng: { better: 1, f: km }, sr: { better: 1, f: km },
  acc: { better: 1, f: x => `${x} G` }, pen: { better: 1, f: x => `${x} mm` }, tnt: { better: 1, f: kg }, e: { better: 1, f: kg }, m: { better: 0, f: kg },
  cal: { better: 0, f: x => `${x} mm` }, pf: { better: 1, f: x => `${x} m` }, burn: { better: 1, f: x => `${x} s` },
  br: { better: 0, f: fmtBR }, nv: { better: 0, f: x => I18N.num(x) },
};
function km(x) { return x >= 1000 ? `${(x / 1000).toFixed(x >= 10000 ? 0 : 1)} km` : `${x} m`; }
function kg(x) { return `${x >= 100 ? Math.round(x) : x} kg`; }

// per category: table columns and "best for" use cases (weights of normalized stats, booleans count 0/1)
const AR_CATS = {
  aam_ir: { cols: ['v', 'acc', 'gl', 'ob', 'trk', 'lk', 'aa', 'rng', 'tnt', 'pf'],
    uses: { dogfight: { gl: .3, ob: .25, trk: .2, ccm: .15, aa: .1 }, aspect: { aa: .5, v: .2, rng: .15, gl: .15 },
      flares: { ccm: .6, trk: .2, gl: .2 }, range: { rng: .4, v: .3, lk: .3 } } },
  aam_radar: { cols: ['v', 'acc', 'gl', 'rng', 'sr', 'ob', 'tnt', 'pf'],
    uses: { bvr: { rng: .35, v: .25, act: .2, dl: .1, loft: .1 }, ff: { act: .5, sr: .2, rng: .15, gl: .15 },
      close: { gl: .45, ob: .3, acc: .25 } } },
  sam: { cols: ['v', 'gl', 'rng', 'tnt', 'pf', 'ob'],
    uses: { range: { rng: .5, v: .3, gl: .2 }, agile: { gl: .5, v: .3, pf: .2 }, ff: { ff2: .6, rng: .2, v: .2 } } },
  atgm: { cols: ['pen', 'v', 'rng', 'tnt', 'm'],
    uses: { tank: { pen: .6, v: .2, tnt: .2 }, standoff: { rng: .5, v: .3, ff: .2 }, ff: { ff: .5, rng: .25, pen: .25 }, fast: { v: .7, rng: .3 } } },
  agm: { cols: ['v', 'rng', 'pen', 'tnt', 'm'],
    uses: { standoff: { rng: .6, v: .2, ff: .2 }, ff: { ff: .5, rng: .3, tnt: .2 }, heavy: { tnt: .7, rng: .3 }, tank: { pen: .5, tnt: .3, v: .2 } } },
  gbomb: { cols: ['m', 'tnt', 'rng'],
    uses: { heavy: { tnt: 1 }, ff: { ff: .6, tnt: .4 }, standoff: { rng: .7, tnt: .3 } } },
  bomb: { cols: ['m', 'e', 'tnt'], uses: { heavy: { tnt: 1 }, eff: { eff: 1 } } },
  rocket: { cols: ['cal', 'pen', 'v', 'tnt', 'm'], uses: { tank: { pen: .7, v: .3 }, blast: { tnt: .8, v: .2 } } },
  torpedo: { cols: ['v', 'rng', 'tnt', 'm'], uses: { fast: { v: .7, tnt: .3 }, range: { rng: .7, v: .3 }, heavy: { tnt: 1 } } },
};
const AR_FLAGS = ['ccm', 'act', 'ins', 'dl', 'loft', 'ff', 'wire', 'nk'];

const arName = it => I18N.arm(it.id);
const arVal = (it, k) => k === 'eff' ? (it.tnt && it.m ? it.tnt / it.m : null) : k === 'ff2' ? (it.g === 'ir' || it.g === 'arh' ? 1 : 0)
  : AR_FLAGS.includes(k) ? (it[k] ? 1 : 0) : (typeof it[k] === 'number' ? it[k] : null);

function arFmt(k, x, c) {
  if (x == null) return '—';
  if (k === 'v') return c === 'torpedo' ? `${Math.round(x * 1.944)} kn` : ['aam_ir', 'aam_radar', 'sam', 'agm'].includes(c) ? `M${(x / 340).toFixed(1)}` : `${x} m/s`;
  return (AR_COLS[k]?.f || String)(x);
}

async function openWeaponsView() {
  if (!AR.data) {
    $('#arTable').innerHTML = `<p class="hint">${esc(t('arm.loading'))}</p>`;
    try {
      AR.data = await getData('armament.json');
      AR.byId = new Map(AR.data.items.map(it => [it.id, it]));
      AR.max = {};
      for (const it of AR.data.items) {
        const m = AR.max[it.c] ||= {};
        for (const k of [...Object.keys(AR_COLS), 'eff']) { const x = arVal(it, k); if (x != null && x > (m[k] || 0)) m[k] = x; }
      }
    } catch {
      $('#arTable').innerHTML = `<p class="hint">${esc(t('arm.noData'))}</p>`;
      return;
    }
  }
  AR.cmp = AR.cmp.filter(id => AR.byId.has(id));
  renderWeapons();
}

function arScore(it, use) {
  const w = AR_CATS[it.c]?.uses[use];
  if (!w) return 0;
  const m = AR.max[it.c] || {};
  let s = 0;
  for (const [k, wt] of Object.entries(w)) {
    const x = arVal(it, k);
    if (!x) continue;
    s += wt * (AR_FLAGS.includes(k) || k === 'ff2' ? x : x / (m[k] || x));
  }
  return s;
}

function arItems() {
  const q = norm(AR.q);
  let list = AR.data.items.filter(it => it.c === AR.cat && (!AR.g || it.g === AR.g) && (!AR.nat || it.nat?.includes(AR.nat))
    && (!q || norm(arName(it) + ' ' + it.id).includes(q)));
  const sort = AR.use && AR.sort === 'score' ? 'score' : AR.sort;
  const val = sort === 'score' ? (it => arScore(it, AR.use)) : sort === 'name' ? null : (it => arVal(it, sort));
  list.sort((a, b) => {
    if (!val) return arName(a).localeCompare(arName(b)) * AR.dir;
    const x = val(a), y = val(b);
    if (x == null && y == null) return arName(a).localeCompare(arName(b));
    if (x == null) return 1;
    if (y == null) return -1;
    return (x - y) * AR.dir || arName(a).localeCompare(arName(b));
  });
  return list;
}

const arTags = it => `${it.g ? `<span class="ar-tag g">${esc(t('arm.g.' + it.g))}</span>` : ''}${AR_FLAGS.filter(f => it[f] && f !== 'act')
  .map(f => `<span class="ar-tag${f === 'nk' ? ' nk' : ''}" title="${esc(t('arm.fh.' + f))}">${esc(t('arm.f.' + f))}</span>`).join('')}`;
const arFlags = it => (it.nat || []).slice(0, 4).map(n => flagHTML(n)).join('') + (it.nat?.length > 4 ? `<span class="muted">+${it.nat.length - 4}</span>` : '');

function renderWeapons() {
  if (!AR.data) return;
  const cats = Object.keys(AR_CATS);
  const count = c => AR.data.items.filter(it => it.c === c).length;
  $('#arCats').innerHTML = cats.map(c => `<button class="chipbtn${AR.cat === c ? ' active' : ''}" data-arcat="${c}">${esc(t('arm.cat.' + c))}<span class="n">${count(c)}</span></button>`).join('');
  const inCat = AR.data.items.filter(it => it.c === AR.cat);
  const gs = [...new Set(inCat.map(it => it.g).filter(Boolean))];
  if (AR.g && !gs.includes(AR.g)) AR.g = '';
  $('#arGuid').innerHTML = gs.length > 1 ? `<button class="chipbtn${!AR.g ? ' active' : ''}" data-arg="">${esc(t('cat.all'))}</button>`
    + gs.map(g => `<button class="chipbtn${AR.g === g ? ' active' : ''}" data-arg="${g}">${esc(t('arm.g.' + g))}</button>`).join('') : '';
  const nats = NATIONS.filter(n => inCat.some(it => it.nat?.includes(n)));
  $('#arNat').innerHTML = `<option value="">${esc(t('arm.allNations'))}</option>` + nats.map(n => `<option value="${n}"${AR.nat === n ? ' selected' : ''}>${esc(nationName(n))}</option>`).join('');
  const uses = Object.keys(AR_CATS[AR.cat].uses);
  if (AR.use && !uses.includes(AR.use)) { AR.use = ''; if (AR.sort === 'score') AR.sort = 'br'; }
  $('#arUses').innerHTML = `<span class="ar-lbl">${esc(t('arm.bestFor'))}</span>` + uses.map(u => `<button class="chipbtn${AR.use === u ? ' active' : ''}" data-aruse="${u}" title="${esc(t('arm.useh.' + u))}">${esc(t('arm.use.' + u))}</button>`).join('');
  renderWeaponGuide(inCat);
  renderWeaponTable();
  renderWeaponTray();
}

function renderWeaponGuide(inCat) {
  const el = $('#arGuide');
  const tips = t('arm.guide.' + AR.cat).split('\n').filter(Boolean);
  const uses = Object.keys(AR_CATS[AR.cat].uses);
  const top = u => [...inCat].sort((a, b) => arScore(b, u) - arScore(a, u)).slice(0, 3);
  el.innerHTML = `<button class="ar-guide-head" data-arguide>${icon('chev', 'ic-sm')}<b>${esc(t('arm.guideTitle', { cat: t('arm.cat.' + AR.cat) }))}</b></button>
    ${AR.guide ? `<div class="ar-guide-body">
      <ul class="ar-tips">${tips.map(x => `<li>${esc(x)}</li>`).join('')}</ul>
      <div class="ar-picks">${uses.map(u => `<div class="ar-pick"><span class="ar-lbl">${esc(t('arm.use.' + u))}</span>
        ${top(u).map((it, i) => `<button class="ar-pick-it" data-aropen="${esc(it.id)}"><i>${i + 1}</i>${esc(arName(it))}</button>`).join('')}</div>`).join('')}</div>
      <p class="hint">${esc(t('arm.guideHint'))}</p></div>` : ''}`;
  el.classList.toggle('closed', !AR.guide);
}

function renderWeaponTable() {
  const list = arItems();
  const cols = AR_CATS[AR.cat].cols.filter(k => list.some(it => it[k] != null));
  const th = (k, label, title = '') => `<th class="sortable${AR.sort === k ? ' sorted' : ''}" data-arsort="${k}" title="${esc(title)}">${esc(label)}${AR.sort === k ? (AR.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`;
  const max = AR.use ? Math.max(...list.map(it => arScore(it, AR.use)), 0.0001) : 1;
  $('#arCount').textContent = t('arm.count', { n: I18N.num(list.length) });
  $('#arTable').innerHTML = list.length ? `<table class="ar-table"><thead><tr><th></th>${th('name', t('arm.col.name'))}<th>${esc(t('arm.col.type'))}</th>
      ${AR.use ? th('score', t('arm.col.score'), t('arm.useh.' + AR.use)) : ''}
      ${cols.map(k => th(k, t('arm.col.' + k), t('arm.colh.' + k))).join('')}${th('br', t('arm.col.br'), t('arm.colh.br'))}${th('nv', t('arm.col.nv'), t('arm.colh.nv'))}</tr></thead>
    <tbody>${list.map(it => {
      const sc = AR.use ? arScore(it, AR.use) / max : 0;
      return `<tr class="${AR.open === it.id ? 'open' : ''}" data-arrow="${esc(it.id)}">
        <td><input type="checkbox" data-arcmp="${esc(it.id)}"${AR.cmp.includes(it.id) ? ' checked' : ''} title="${esc(t('compare.add'))}"></td>
        <td class="ar-name">${ammoIcon(it.ic)}<span><b>${esc(arName(it))}</b><span class="ar-nat">${arFlags(it)}</span></span></td>
        <td class="ar-tags">${arTags(it)}</td>
        ${AR.use ? `<td class="ar-score"><span class="bar"><i style="width:${Math.round(sc * 100)}%"></i></span><b>${Math.round(sc * 100)}</b></td>` : ''}
        ${cols.map(k => `<td>${esc(arFmt(k, it[k], it.c))}</td>`).join('')}
        <td>${esc(fmtBR(it.br))}</td><td>${esc(I18N.num(it.nv || 0))}</td></tr>
        ${AR.open === it.id ? `<tr class="ar-detail"><td colspan="${5 + cols.length + (AR.use ? 1 : 0)}">${weaponDetailHTML(it)}</td></tr>` : ''}`;
    }).join('')}</tbody></table>` : `<p class="hint">${esc(t('results.empty'))}</p>`;
}

function weaponDetailHTML(it) {
  const keys = Object.keys(AR_COLS).filter(k => it[k] != null && k !== 'nv');
  const note = I18N.tOr('arm.note.' + it.id, '');
  const car = (AR.data.carriers[it.id] || []).map(id => S.byId.get(id)).filter(Boolean)
    .sort((a, b) => (a.br?.[1] || 0) - (b.br?.[1] || 0));
  const shown = car.slice(0, 60);
  const uses = Object.keys(AR_CATS[it.c].uses);
  const m = AR.data.items.filter(x => x.c === it.c);
  const rank = u => 1 + m.filter(x => arScore(x, u) > arScore(it, u)).length;
  return `<div class="ar-det">
    <div class="ar-det-stats">${keys.map(k => `<div class="vstat"><span>${esc(t('arm.col.' + k))}</span><b>${esc(arFmt(k, it[k], it.c))}</b></div>`).join('')}</div>
    <div class="ar-det-uses">${uses.map(u => `<span class="ar-rank" title="${esc(t('arm.useh.' + u))}">${esc(t('arm.use.' + u))} <b>#${rank(u)}</b><small>/${m.length}</small></span>`).join('')}</div>
    ${note ? `<div class="ar-note"><b>${esc(t('arm.community'))}</b> ${esc(note)}<small>${esc(t('arm.notesHint'))}</small></div>` : ''}
    <div class="ar-carriers"><span class="ar-lbl">${esc(t('arm.carriedBy', { n: car.length }))}</span>
      ${shown.map(v => `<button class="ar-veh" data-arveh="${esc(v.id)}" title="${esc(I18N.unitFull(v.id))}">${flagHTML(v.n)}<span>${esc(I18N.unit(v.id))}</span><small>${esc(fmtBR(v.br?.[1]))}</small></button>`).join('')}
      ${car.length > shown.length ? `<span class="muted">+${car.length - shown.length}</span>` : ''}</div>
  </div>`;
}

function renderWeaponTray() {
  const list = AR.cmp.map(id => AR.byId.get(id)).filter(Boolean);
  const el = $('#arTray');
  el.classList.toggle('hidden', !list.length);
  el.innerHTML = list.length ? `<div class="ct-items">${list.map(it => `<span class="ct-item">${ammoIcon(it.ic)}<span class="ct-name">${esc(arName(it))}</span>
      <button data-arcmprm="${esc(it.id)}" title="${esc(t('compare.remove'))}">${icon('x', 'ic-sm')}</button></span>`).join('')}</div>
    <button class="btn btn-ghost btn-sm" data-arcmpact="clear">${esc(t('compare.clear'))}</button>
    <button class="btn btn-primary btn-sm" data-arcmpact="open"${list.length < 2 ? ' disabled' : ''}>${icon('sliders', 'ic-sm')}<span>${esc(t('compare.button', { n: list.length }))}</span></button>` : '';
}

function toggleWeaponCompare(id) {
  if (AR.cmp.includes(id)) AR.cmp = AR.cmp.filter(x => x !== id);
  else if (AR.cmp.length >= 5) { toast({ title: t('compare.max', { n: 5 }), err: true, ms: 3500 }); return false; }
  else AR.cmp = [...AR.cmp, id];
  store.set('wcmp', AR.cmp);
  renderWeaponTray();
  return true;
}

function renderWeaponCompare() {
  const list = AR.cmp.map(id => AR.byId.get(id)).filter(Boolean);
  if (list.length < 2) { $('#dlgWcmp').close(); return; }
  const keys = Object.keys(AR_COLS).filter(k => k !== 'nv' && list.some(it => it[k] != null));
  const row = (label, cells) => `<tr><th>${esc(label)}</th>${cells.join('')}</tr>`;
  const statRow = k => {
    const vals = list.map(it => it[k]).filter(x => x != null);
    const dir = AR_COLS[k].better;
    const b = dir && vals.length > 1 ? (dir > 0 ? Math.max(...vals) : Math.min(...vals)) : null;
    return row(t('arm.col.' + k), list.map(it => `<td class="${b != null && it[k] === b ? 'best' : ''}">${esc(arFmt(k, it[k], it.c))}</td>`));
  };
  const uses = [...new Set(list.flatMap(it => Object.keys(AR_CATS[it.c].uses)))];
  const useRow = u => {
    const sc = list.map(it => AR_CATS[it.c].uses[u] ? arScore(it, u) : null);
    const b = Math.max(...sc.filter(x => x != null));
    return row(t('arm.bestFor') + ' · ' + t('arm.use.' + u), sc.map(x => `<td class="${x != null && x === b && list.length > 1 ? 'best' : ''}">${x == null ? '—' : Math.round(x * 100)}</td>`));
  };
  $('#wcmpTable').innerHTML = `<table class="cmp"><thead><tr><th></th>${list.map(it => `<th><div class="cmp-head">
      <button class="icon-btn cmp-rm" data-arcmprm="${esc(it.id)}" title="${esc(t('compare.remove'))}">${icon('x', 'ic-sm')}</button>
      <div class="ar-cmp-ic">${ammoIcon(it.ic)}</div><div class="cmp-name"><b>${esc(arName(it))}</b></div>
      <div class="muted">${esc(t('arm.cat.' + it.c))}</div><div class="ar-nat">${arFlags(it)}</div></div></th>`).join('')}</tr></thead><tbody>
    ${row(t('arm.col.type'), list.map(it => `<td class="cmp-wrap">${arTags(it)}</td>`))}
    ${keys.map(statRow).join('')}
    ${uses.map(useRow).join('')}
    ${row(t('arm.col.nv'), list.map(it => `<td>${esc(I18N.num(it.nv || 0))}</td>`))}
    ${list.some(it => I18N.tOr('arm.note.' + it.id, '')) ? row(t('arm.community'), list.map(it => `<td class="cmp-wrap ar-cmp-note">${esc(I18N.tOr('arm.note.' + it.id, '—'))}</td>`)) : ''}
  </tbody></table>`;
}

function bindWeapons() {
  const view = $('#view-weapons');
  view.addEventListener('click', e => {
    const cb = e.target.closest('[data-arcmp]');
    if (cb) { if (!toggleWeaponCompare(cb.dataset.arcmp)) cb.checked = false; return; }
    const b = e.target.closest('button, th[data-arsort], tr[data-arrow]');
    if (!b) return;
    const d = b.dataset;
    if (d.arcat) { AR.cat = d.arcat; AR.g = ''; AR.open = ''; AR.use = ''; AR.sort = 'br'; AR.dir = 1; return renderWeapons(); }
    if (d.arg !== undefined) { AR.g = d.arg; return renderWeapons(); }
    if (d.aruse) {
      AR.use = AR.use === d.aruse ? '' : d.aruse;
      AR.sort = AR.use ? 'score' : 'br'; AR.dir = AR.use ? -1 : 1;
      return renderWeapons();
    }
    if (d.arguide !== undefined) { AR.guide = !AR.guide; store.set('wguide', AR.guide ? 1 : 0); return renderWeaponGuide(AR.data.items.filter(it => it.c === AR.cat)); }
    if (d.aropen) { AR.g = ''; AR.q = ''; $('#arSearch').value = ''; AR.open = d.aropen; renderWeapons(); return $(`tr[data-arrow="${CSS.escape(d.aropen)}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
    if (d.arveh) { showView('vehicles'); return openVehicle(d.arveh); }
    if (d.arsort) {
      const k = d.arsort;
      if (AR.sort === k) AR.dir = -AR.dir;
      else { AR.sort = k; AR.dir = k === 'name' || k === 'br' ? 1 : -1; }
      return renderWeaponTable();
    }
    if (d.arrow && !e.target.closest('.ar-detail, button, input')) { AR.open = AR.open === d.arrow ? '' : d.arrow; return renderWeaponTable(); }
  });
  $('#arSearch').addEventListener('input', debounce(e => { AR.q = e.target.value; renderWeaponTable(); }, 120));
  $('#arNat').addEventListener('change', e => { AR.nat = e.target.value; renderWeaponTable(); });
  const trayClick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.arcmprm) {
      toggleWeaponCompare(b.dataset.arcmprm);
      $$(`[data-arcmp="${CSS.escape(b.dataset.arcmprm)}"]`).forEach(c => { c.checked = false; });
      if ($('#dlgWcmp').open) renderWeaponCompare();
    } else if (b.dataset.arcmpact === 'clear') { AR.cmp = []; store.set('wcmp', []); renderWeaponTray(); $$('[data-arcmp]').forEach(c => { c.checked = false; }); }
    else if (b.dataset.arcmpact === 'open') { renderWeaponCompare(); $('#dlgWcmp').showModal(); }
  };
  $('#arTray').addEventListener('click', trayClick);
  $('#dlgWcmp').addEventListener('click', trayClick);
}
