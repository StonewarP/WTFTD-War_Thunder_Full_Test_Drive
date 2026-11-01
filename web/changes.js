/* WTFTD — What changed: everything that moved between two game versions (wtftd/patches.py, which also holds the table of what's
   compared: labels, units and colours come from it). One patch at a time, its groups closed: a group's rows are made when it opens. */
'use strict';

const CH_PAGE = 200;  // rows added at a time: a patch can move every battle rating of the game
const CH = { groups: [], fields: {}, patches: [], rows: null, id: '', cache: {}, by: {}, open: new Set(), more: {}, touched: new Map(),
             q: '', nat: '', cat: '', mode: '', mine: false, seen: store.get('changesSeen', ''), hidden: '', loading: null };

// a value that's a name, or a list of them: what the table's unit says
const CH_NAMES = { weapon: k => I18N.weapon(k), bullet: k => I18N.bullet(k), sensor: k => I18N.sensor(k), avionics: k => t('mods.av.' + k),
                   flag: k => t('arm.f.' + k), guidance: k => (k ? t('arm.g.' + k) : '—') };

const chShell = sid => {
  const [gun, belt, ...bullets] = sid.split('|');
  return bullets.length ? bullets.map(b => I18N.bullet(b)).join(', ') : `${I18N.weapon(gun)} · ${belt ? I18N.mod(belt) || belt.replace(/_/g, ' ') : t('ammo.default')}`;
};

// what a row is about, whatever the current data still has of it
function chName(r) {
  const k = r[1], f = CH.fields[k];
  if (f.of === 's') return chShell(r[0]);
  if (f.group === 'weapon') return AR.byId.get(r[0]) ? arName(AR.byId.get(r[0])) : r[2] && k === 'w.gone' ? r[2] : I18N.arm(r[0]);
  if (f.group === 'map') return k === 'm.gone' ? r[2] : mbMapName(r[0]);
  return S.byId.has(r[0]) ? I18N.unit(r[0]) : k === 'gone' ? r[2] : k === 'new' ? r[3] : I18N.unit(r[0]);
}

// the vehicles a row concerns: itself, those firing that shell, those carrying that weapon; a map, none
function chVehicles(r) {
  const k = r[1], f = CH.fields[k];
  if (k === 'gone') return [{ id: r[0], n: r[4][0], c: r[4][1] }];
  const ids = f.of === 's' ? r[4] : f.group === 'weapon' ? AR.data?.carriers[r[0]] || [] : f.group === 'map' ? [] : [r[0]];
  return ids.map(id => S.byId.get(id)).filter(Boolean);
}

const chFound = r => (r.text ??= norm([r.name, ...chVehicles(r).map(v => v._s || v.id)].join(' ')));

function chShown() {
  const q = norm(CH.q), mine = new Set([...S.favs, ...S.setups.map(s => s.vehicle)]), any = CH.nat || CH.cat || CH.mine;
  return CH.rows.filter(r => !(CH.mode && /^br[ars]b$/.test(r[1]) && r[1] !== 'br' + CH.mode) && (!q || chFound(r).includes(q))
    && (!any || chVehicles(r).some(v => (!CH.nat || v.n === CH.nat) && (!CH.cat || v.c === CH.cat) && (!CH.mine || mine.has(v.id)))));
}

function chValue(r, f, x) {
  if (x == null) return '—';
  if (CH_NAMES[f.unit]) return [...new Set([x].flat().map(CH_NAMES[f.unit]))].join(', ') || '—';
  if (f.of === 'w') return arFmt(r[1].slice(2), x, AR.byId.get(r[0])?.c);
  const n = new Intl.NumberFormat(I18N.code, { minimumFractionDigits: f.digits < 2 ? f.digits : 0, maximumFractionDigits: f.digits });  // 11.0 like a BR
  return [x].flat().map(y => n.format(y)).join(' / ') + (f.unit ? ` ${f.unit}` : '');
}

// 1 better, -1 worse, 0 not known: several numbers must all go the same way
function chDir(f, a, b) {
  if (!f.better || a == null || b == null) return 0;
  const was = [a].flat(), up = was.some((x, i) => [b].flat()[i] > x), down = was.some((x, i) => [b].flat()[i] < x);
  return up === down ? 0 : (up ? 1 : -1) * f.better;
}

function chSubject(r) {
  const k = r[1], f = CH.fields[k], v = S.byId.get(r[0]);
  if (f.of === 's') {
    const list = r[4].map(id => S.byId.get(id)).filter(Boolean), shown = list.slice(0, 3);
    return `<span class="ch-sub"><b>${esc(r.name)}</b><small>${shown.map(x => mbVehicle(x.id)).join(', ')}${list.length > 3 ? ` <span class="muted">+${I18N.num(list.length - 3)}</span>` : ''}</small></span>`;
  }
  if (f.group === 'weapon') {
    const it = AR.byId.get(r[0]);
    return it ? `<button class="mb-link" data-chweapon="${esc(it.id)}">${ammoIcon(it.ic)}<span>${esc(r.name)}</span></button>` : esc(r.name);
  }
  if (f.group === 'map') return k === 'm.gone' ? esc(r.name) : mbMap(r[0]);
  return v ? `${mbVehicle(r[0], flagHTML(v.n) + unitImgTag(r[0]))}${v.h || v.ra === 6 ? rarityTag(v) : ''}` : esc(r.name);
}

// the value column of what's new or removed: it has no before and after
function chWhat(r) {
  const v = S.byId.get(r[0]), it = AR.byId.get(r[0]);
  if (v) return `${className(v.k)}${v.r ? ` · ${t('rank', { r: ROMAN[v.r] || v.r })}` : ''}`;
  return it ? t('arm.cat.' + it.c) : '—';
}

function chRow(r, same) {
  const k = r[1], f = CH.fields[k], v = S.byId.get(r[0]);
  if (f.of === '') {
    const after = k === 'new' && v ? esc(`BR ${fmtBR(brOf(v))}`) : `<span class="chip ${k.endsWith('new') ? 'info' : 'dim'}">${esc(t(f.label))}</span>`;
    return `<tr><td>${chSubject(r)}</td><td>${esc(chWhat(r))}</td><td>—</td><td>${after}</td></tr>`;
  }
  const dir = chDir(f, r[2], r[3]), mark = dir ? `chip ${dir > 0 ? 'info' : 'warn'}` : '', title = dir ? ` title="${esc(t(dir > 0 ? 'ch.better' : 'ch.worse'))}"` : '';
  return `<tr><td>${same ? '' : chSubject(r)}</td><td>${esc(t(f.label))}</td><td class="muted">${esc(chValue(r, f, r[2]))}</td>
    <td>${mark ? `<span class="${mark}"${title}>${esc(chValue(r, f, r[3]))}</span>` : esc(chValue(r, f, r[3]))}</td></tr>`;
}

function chTable(g) {
  const rows = CH.by[g] || [], n = CH.more[g] || CH_PAGE;
  const left = rows.length - n;
  return `<div class="ar-scroll"><table class="ar-table ch-table"><thead><tr><th>${esc(t('ch.about'))}</th><th>${esc(t('ch.value'))}</th><th>${esc(t('ch.before'))}</th><th>${esc(t('ch.after'))}</th></tr></thead>
    <tbody>${rows.slice(0, n).map((r, i) => chRow(r, r[0] === rows[i - 1]?.[0])).join('')}</tbody></table></div>
    ${left > 0 ? `<button class="btn btn-sm ch-more" data-chmore="${g}">${esc(t('ch.more', { n: I18N.num(Math.min(left, CH_PAGE)) }))}</button>` : ''}`;
}

function chRender() {
  const body = $('#chBody');
  $('#chBar').classList.toggle('hidden', !CH.patches.length);
  if (!CH.patches.length) {
    body.innerHTML = `<div class="empty">${icon('refresh', 'ic-xl')}<p>${esc(t('ch.empty'))}</p><p>${esc(t('ch.emptyHint'))}</p></div>`;
    return;
  }
  if (!CH.rows) { body.innerHTML = `<div class="empty"><p>${esc(t('arm.loading'))}</p></div>`; return; }
  const p = CH.patches.find(x => x.id === CH.id);
  CH.by = {};
  for (const r of chShown()) (CH.by[CH.fields[r[1]].group] ||= []).push(r);
  const present = CH.groups.filter(g => CH.by[g]);
  const notes = [p.back && t('ch.back', { from: p.from, to: p.to }), p.schema && t('ch.schema')].filter(Boolean);
  body.innerHTML = `${notes.map(x => `<p class="hint ch-note">${icon('target', 'ic-sm')}<span>${esc(x)}</span></p>`).join('')}
    ${present.length ? `<div class="vstats mb-totals ch-totals">${present.map(g => `<button class="vstat" data-chgroup="${g}"><span>${esc(t('ch.group.' + g))}</span><b>${I18N.num(CH.by[g].length)}</b></button>`).join('')}</div>` : `<div class="empty"><p>${esc(t('ch.none'))}</p></div>`}
    ${present.map(g => `<details class="ch-group" data-g="${g}"${CH.open.has(g) ? ' open' : ''}><summary><span>${esc(t('ch.group.' + g))}</span><span class="tab-count">${I18N.num(CH.by[g].length)}</span></summary>
      <div class="ch-rows">${CH.open.has(g) ? chTable(g) : ''}</div></details>`).join('')}`;
}

// a patch's rows, sorted once: by name, a vehicle's values together
async function chPick(id) {
  CH.id = id;
  CH.rows = null;
  chRender();
  const rows = CH.cache[id] ||= await api('changes/' + id);
  if (CH.id !== id) return;
  if (!rows[0]?.name) {
    for (const r of rows) r.name = chName(r);
    rows.sort((a, b) => CH.groups.indexOf(CH.fields[a[1]].group) - CH.groups.indexOf(CH.fields[b[1]].group) || a.name.localeCompare(b.name, I18N.code, { numeric: true }));
  }
  CH.rows = rows;
  CH.more = {};
  chRender();
}

function chFilters() {
  CH.more = {};
  chRender();
}

function chUnseen() {
  const at = CH.patches.findIndex(p => p.id === CH.seen);
  const list = CH.patches.slice(0, at < 0 ? undefined : at).filter(p => !p.back);
  const n = list.reduce((sum, p) => sum + Object.values(p.counts).reduce((a, b) => a + b, 0), 0);
  $('#changeCount').textContent = n ? I18N.num(n) : '';
}

// the update banner's link: until the page has been opened, or the banner closed
const chBannerDue = st => !!st.patch && st.patch !== CH.seen && st.patch !== CH.hidden;

async function chLoad() {
  Object.assign(CH, await api('changes'));
  chUnseen();
  const last = CH.patches[0];
  if (!last || last.back) return;  // gone back: what the latest patch moved isn't what the panel shows
  const rows = CH.cache[last.id] ||= await api('changes/' + last.id);
  for (const r of rows) {
    const f = CH.fields[r[1]];
    for (const id of f.of === 's' ? r[4] : f.of === 'v' ? [r[0]] : []) CH.touched.set(id, (CH.touched.get(id) || 0) + 1);
  }
  if (S.sel && $('#drawer .hero')) renderDrawer();
}

// the vehicle panel's quiet line
function chPanelLine(v) {
  const n = CH.touched.get(v.id);
  return n ? `<button class="mb-link ch-line" data-act="changes">${esc(t('ch.vehicleLine', { v: CH.patches[0].to, n: I18N.num(n) }))}</button>` : '';
}

function chShowVehicle(v) {
  Object.assign(CH, { q: I18N.unit(v.id), nat: '', cat: '', mode: '', mine: false, id: '' });
  $('#chSearch').value = CH.q;
  $('#chNation').value = $('#chCat').value = '';
  $('#chMine').checked = false;
  $$('#chMode button').forEach(x => x.classList.toggle('active', !x.dataset.m));
  showView('changes');
}

async function openChangesView() {
  try {
    await CH.loading;
    CH.seen = CH.patches[0]?.id || CH.seen;
    store.set('changesSeen', CH.seen);
    chUnseen();
    $('#updateBanner.done')?.classList.add('hidden');
    $('#chPatch').innerHTML = CH.patches.map(p => `<option value="${esc(p.id)}">${esc(`${p.from} → ${p.to} · ${new Date(p.at * 1000).toLocaleDateString(I18N.code)}${p.back ? ` · ${t('ch.backShort')}` : ''}`)}</option>`).join('');
    if (!CH.patches.length) return chRender();
    if (!AR.data) await openWeaponsView();  // names, carriers and links of the weapons
    if (!CH.patches.some(p => p.id === CH.id)) await chPick(CH.patches[0].id);
    else chRender();
    $('#chPatch').value = CH.id;
  } catch (e) { toastErr(e); }
}

function bindChanges() {
  CH.loading = chLoad().catch(() => {});
  $('#chNation').innerHTML = `<option value="">${esc(t('arm.allNations'))}</option>${NATIONS.map(n => `<option value="${n}">${esc(nationName(n))}</option>`).join('')}`;
  $('#chCat').innerHTML = `<option value="">${esc(t('ch.allTypes'))}</option>${CATS.slice(1).map(c => `<option value="${c}">${esc(t('cat.' + c))}</option>`).join('')}`;
  $('#chPatch').addEventListener('change', e => chPick(e.target.value).catch(toastErr));
  $('#chSearch').addEventListener('input', debounce(e => { CH.q = e.target.value; chFilters(); }, 120));
  $('#chNation').addEventListener('change', e => { CH.nat = e.target.value; chFilters(); });
  $('#chCat').addEventListener('change', e => { CH.cat = e.target.value; chFilters(); });
  $('#chMine').addEventListener('change', e => { CH.mine = e.target.checked; chFilters(); });
  $('#chMode').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    CH.mode = b.dataset.m;
    $$('#chMode button').forEach(x => x.classList.toggle('active', x === b));
    chFilters();
  });
  const body = $('#chBody');
  body.addEventListener('toggle', e => {  // it doesn't bubble: seen on the way down
    const box = e.target, g = box.dataset?.g;
    if (!g) return;
    if (box.open) { CH.open.add(g); box.querySelector('.ch-rows').innerHTML = chTable(g); }
    else { CH.open.delete(g); box.querySelector('.ch-rows').innerHTML = ''; }
  }, true);
  body.addEventListener('click', e => {
    const b = e.target.closest('[data-chgroup], [data-chmore], [data-chweapon]');
    if (b?.dataset.chgroup) {
      const box = $(`details[data-g="${b.dataset.chgroup}"]`);
      box.open = true;
      box.scrollIntoView({ block: 'start', behavior: 'smooth' });
    } else if (b?.dataset.chmore) {
      const g = b.dataset.chmore;
      CH.more[g] = (CH.more[g] || CH_PAGE) + CH_PAGE;
      $(`details[data-g="${g}"] .ch-rows`).innerHTML = chTable(g);
    } else if (b?.dataset.chweapon) openWeapon(b.dataset.chweapon);
    else mbFollow(e);
  });
}
