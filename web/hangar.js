/* WTFTD — My hangar: what the player owns, their lineups, what to research next (wtftd/hangar.py keeps them in user/hangar.json). The game
   doesn't tell the app what the player owns: only the player marks a vehicle, the battles they played are only offered. */
'use strict';

const HG = { loaded: false, owned: new Set(), ignored: new Set(), lineups: [], goals: [], tab: store.get('hangarTab', 'owned'), cat: 'all', every: false,
             line: '', planning: false, allPlayed: false };
const HG_TABS = ['owned', 'lineups', 'plan'], HG_PLAYED = 12;  // suggestions shown before "all"

// ------------------------------------------------------------------ matchmaking
// The official wiki's Matchmaking page (mechanics/matchmaking): a lineup meets lineups within 1.0 of its rating. One step is one economic
// rank: 3 make 1.0, the game's own warning for a squad member far below the top (getBRDataByMrankDiff, scripts/battleRating.nut).
const hgSteps = (a, b) => Math.round((a - b) * 3);
const hgFar = 3;

function hgRoundUp(x) {  // to the game's next step: .0, .3, .7
  const whole = Math.floor(x + 1e-9);
  return Math.round((whole + [0, .3, .7, 1].find(s => s >= x - whole - 1e-9)) * 10) / 10;
}

// Air Arcade: the three highest aircraft, A/2 + B/4 + C/4 (A/2 + B/2 for two), a lower one counting as 0.6 below the top
function hgAverage(brs) {
  const [a, b, c] = [...brs].sort((x, y) => y - x), near = x => Math.max(x, a - .6);
  return hgRoundUp(c != null ? a / 2 + near(b) / 4 + near(c) / 4 : b != null ? a / 2 + near(b) / 2 : a);
}

// list: the lineup's vehicles; mode: 0 AB, 1 RB, 2 SB; top: the game's highest rating. -> {rule, br, low, high, far: ids, out: ids}, null if it can't play.
// rules: top (ground), avg (Air AB), each (Air RB: the aircraft selected), naval, sb (rating ranges or lists that rotate, no ±1.0)
function lineupRating(list, mode, top) {
  const at = v => v.br?.[mode] ?? null, known = list.filter(v => at(v) != null);
  if (!known.length) return null;
  const flying = v => v.c === 'air' || v.c === 'heli', ships = known.filter(v => v.c === 'boat' || v.c === 'ship');
  const allFly = known.every(flying), brs = known.map(at);
  let br = Math.max(...brs), rule = 'top', out = [];
  if (mode === 2) rule = 'sb';
  else if (ships.length) {
    const roof = Math.max(...ships.map(at));
    rule = 'naval';
    out = known.filter(v => flying(v) && hgSteps(at(v), roof) > 1).map(v => v.id);
    br = Math.max(...known.filter(v => !out.includes(v.id)).map(at));
  } else if (allFly && mode === 0) { rule = 'avg'; br = hgAverage(brs); } else if (allFly) rule = 'each';
  const range = rule !== 'sb', highest = Math.max(...known.filter(v => !out.includes(v.id)).map(at));
  const far = rule === 'each' || rule === 'sb' ? [] : known.filter(v => !out.includes(v.id) && hgSteps(highest, at(v)) >= hgFar).map(v => v.id);
  return { rule, br, low: range ? Math.max(1, Math.round((br - 1) * 10) / 10) : null, high: range ? Math.min(top, Math.round((br + 1) * 10) / 10) : null, far, out };
}

// ------------------------------------------------------------------ saved marks
const hgFlush = debounce(() => api('hangar', { owned: [...HG.owned], ignored: [...HG.ignored], goals: HG.goals, lineups: HG.lineups }).catch(toastErr), 300);
function hgSave() { if (HG.loaded) hgFlush(); }  // a hangar that couldn't be read isn't written over

function hgMarks() {
  $('#hangarCount').textContent = HG.owned.size ? I18N.num(HG.owned.size) : '';
  $$('[data-own]').forEach(el => {
    const on = HG.owned.has(el.dataset.own);
    el.classList.toggle('on', on);
    el.title = t(on ? 'hg.unmark' : 'hg.mark');
    el.closest('.tcard')?.classList.toggle('owned', on);
  });
}

function hgSet(ids, on) {
  for (const id of ids) on ? HG.owned.add(id) : HG.owned.delete(id);
  hgSave();
  hgMarks();
  if (S.f.owned) applyFilters();
  if (!$('#view-hangar').classList.contains('hidden')) hgRender();
  if (S.sel) renderDrawer();
}

const hgToggle = id => hgSet([id], !HG.owned.has(id));

// a whole rank or nation: all owned already, the click takes them off
function hgMarkMany(ids) {
  const on = ids.some(id => !HG.owned.has(id)), changed = ids.filter(id => HG.owned.has(id) !== on);
  hgSet(changed, on);
  HG.toast?.remove();  // rank after rank, one at a time: a pile would cover the table
  toast({ title: t(on ? 'hg.marked' : 'hg.removed', { n: I18N.num(changed.length) }), ms: 4000, actions: [{ label: t('hg.undo'), run: () => hgSet(changed, !on) }] });
  HG.toast = $('#toasts').lastElementChild;
}

function hgAddGoal(id) {
  if (!HG.goals.includes(id)) HG.goals.push(id);
  hgSave();
  toast({ title: t('hg.goalAdded', { v: I18N.unit(id) }), ms: 3000, actions: [{ label: t('hg.tab.plan'), run: () => { HG.tab = 'plan'; showView('hangar'); } }] });
}

// ------------------------------------------------------------------ owned
// a reserve vehicle is every player's, and the only one the game repairs for free
const hgReserve = v => !!v.s?.rep?.every(x => !x);
const hgOwns = v => HG.owned.has(v.id) || hgReserve(v);
const hgCanOwn = v => !v.h && v.ra !== 6 && (HG.cat === 'all' || v.c === HG.cat) && (HG.every || (!v.ra && !v.p && (!v.g || hgReserve(v))));
const hgNumber = n => (n == null ? '—' : I18N.num(n));

// what My battles shows was played, and isn't marked yet: a rented or trial vehicle plays too, so the player decides
function hgPlayed() {
  const by = new Map();
  for (const r of MB.rows || []) if (!r.offline) for (const id of r.vehicles) if (S.byId.has(id) && !HG.owned.has(id) && !HG.ignored.has(id)) by.set(id, (by.get(id) || 0) + 1);
  return [...by].sort((a, b) => b[1] - a[1] || I18N.unit(a[0]).localeCompare(I18N.unit(b[0])));
}

function hgPlayedHTML() {
  const list = hgPlayed();
  if (!list.length) return '';
  const shown = HG.allPlayed ? list : list.slice(0, HG_PLAYED);
  return `<h3 class="list-head">${esc(t('hg.played'))}</h3><div class="hg-row"><p class="hint">${esc(t('hg.playedHint'))}</p>
      <button class="btn btn-sm btn-primary" data-hgplayed>${esc(t('hg.markAll', { n: I18N.num(list.length) }))}</button></div>
    <div class="ar-scroll"><table class="ar-table hg-table"><thead><tr><th>${esc(t('mb.vehicle'))}</th><th class="num">${esc(t('mb.battles'))}</th><th></th></tr></thead>
    <tbody>${shown.map(([id, n]) => `<tr><td>${mbVehicle(id, flagHTML(S.byId.get(id).n) + unitImgTag(id))}</td><td class="num">${I18N.num(n)}</td>
      <td class="hg-actions"><button class="btn btn-sm" data-hgyes="${esc(id)}">${esc(t('hg.mark'))}</button><button class="btn btn-sm btn-ghost" data-hgno="${esc(id)}">${esc(t('hg.notMine'))}</button></td></tr>`).join('')}</tbody></table></div>
    ${list.length > shown.length ? `<button class="btn btn-sm ch-more" data-hgmore>${esc(t('ch.more', { n: I18N.num(list.length - shown.length) }))}</button>` : ''}`;
}

function hgOwnedHTML() {
  const pool = S.vehicles.filter(hgCanOwn), ranks = [...new Set(pool.map(v => v.r))].filter(Boolean).sort((a, b) => a - b);
  const counts = new Map(), add = (key, v) => { const c = counts.get(key) || [0, 0]; c[0] += HG.owned.has(v.id); c[1]++; counts.set(key, c); };
  for (const v of pool) for (const key of [`${v.n}|${v.r}`, `${v.n}|`, `|${v.r}`, '|']) add(key, v);
  const cell = key => {
    const [n, all] = counts.get(key) || [0, 0];
    return `<td class="num"><button class="hg-cell${all && n === all ? ' full' : n ? ' part' : ''}" data-hgcell="${esc(key)}"${all ? '' : ' disabled'}>${all ? `${I18N.num(n)} / ${I18N.num(all)}` : '—'}</button></td>`;
  };
  const row = (n, label) => `<tr><th>${label}</th>${ranks.map(r => cell(`${n}|${r}`)).join('')}${cell(`${n}|`)}</tr>`;
  return `<div class="fl-bar"><div class="seg" id="hgCats">${CATS.map(c => `<button class="${HG.cat === c ? 'active' : ''}" data-hgcat="${c}">${esc(t('cat.' + c))}</button>`).join('')}</div>
      <label class="switch"><input type="checkbox" id="hgEvery"${HG.every ? ' checked' : ''}><span class="sw"></span><span>${esc(t('hg.every'))}</span></label>
      <span class="muted">${esc(t('hg.count', { n: I18N.num(HG.owned.size) }))}</span>
      <button class="btn btn-sm hg-see" data-hgsee${HG.owned.size ? '' : ' disabled'}>${esc(t('hg.see'))}</button></div>
    <p class="hint mb-note">${esc(t('hg.tableHint'))}</p>
    <div class="ar-scroll"><table class="ar-table hg-table hg-grid"><thead><tr><th>${esc(t('hg.nation'))}</th>${ranks.map(r => `<th class="num">${ROMAN[r] || r}</th>`).join('')}<th class="num">${esc(t('hg.total'))}</th></tr></thead>
      <tbody>${NATIONS.map(n => row(n, `<span class="hg-nation">${flagHTML(n)}<span>${esc(nationName(n))}</span></span>`)).join('')}${row('', esc(t('arm.allNations')))}</tbody></table></div>
    ${hgPlayedHTML()}`;
}

// ------------------------------------------------------------------ lineups
const hgTopBR = mode => Math.max(...S.vehicles.filter(v => !v.h).map(v => v.br?.[mode] ?? 0));
const hgRange = (list, fmt) => { const a = Math.min(...list), b = Math.max(...list); return !list.length ? '—' : a === b ? fmt(a) : `${fmt(a)} – ${fmt(b)}`; };
const hgPercent = x => fmtStat('rpm', x);
const hgSum = (list, f) => list.reduce((n, v) => n + (f(v) || 0), 0);

function hgLineupBar(line) {
  return `<div class="ov-profiles">
      <label for="hgLine">${esc(t('hg.lineup'))}</label>
      <select id="hgLine">${HG.lineups.map(x => `<option value="${esc(x.id)}"${x === line ? ' selected' : ''}>${esc(x.name)} · ${esc(nationName(x.nation))} · ${esc(t('filters.mode.' + x.mode))}</option>`).join('')}</select>
      ${line ? `<button class="icon-btn btn-danger" data-hgdel title="${esc(t('action.delete'))}">${icon('trash')}</button>` : ''}
      <input id="hgNewName" type="text" spellcheck="false" maxlength="60" placeholder="${esc(t('hg.newName'))}">
      <select id="hgNewNation">${NATIONS.map(n => `<option value="${n}"${n === (line?.nation || S.f.nations[0]) ? ' selected' : ''}>${esc(nationName(n))}</option>`).join('')}</select>
      <button class="btn btn-sm" data-hgnew>${esc(t('hg.create'))}</button></div>`;
}

function hgPicker(line, mode) {
  const taken = new Set(line.vehicles), at = v => v.br?.[mode] ?? 0;
  const list = S.vehicles.filter(v => v.n === line.nation && !v.h && !taken.has(v.id) && (HG.planning || HG.owned.has(v.id))).sort((a, b) => at(b) - at(a) || I18N.unit(a.id).localeCompare(I18N.unit(b.id)));
  return `<select id="hgPick"${list.length ? '' : ' disabled'}><option value="">${esc(t(list.length ? 'hg.addVehicle' : 'hg.noneToAdd'))}</option>
    ${list.map(v => `<option value="${esc(v.id)}">${esc(fmtBR(v.br?.[mode]))} · ${esc(I18N.unit(v.id))}</option>`).join('')}</select>`;
}

function hgLineupsHTML() {
  const line = HG.lineups.find(x => x.id === HG.line) || HG.lineups[0];
  HG.line = line?.id || '';
  if (!line) return `${hgLineupBar(null)}<div class="empty">${icon('tree', 'ic-xl')}<p>${esc(t('hg.noLineup'))}</p><p>${esc(t('hg.noLineupHint'))}</p></div>`;
  const mode = MODES.indexOf(line.mode), at = v => v.br?.[mode] ?? null;
  const list = line.vehicles.map(id => S.byId.get(id)).filter(Boolean).sort((a, b) => (at(b) ?? 0) - (at(a) ?? 0));
  const r = lineupRating(list, mode, hgTopBR(mode));
  const rep = v => v.s?.rep?.[mode], stock = v => v.su?.rep?.[mode] ?? rep(v);
  const slm = list.map(v => v.s?.slm?.[mode]).filter(x => x != null), rpm = list.map(v => v.s?.rpm).filter(x => x != null);
  const tiles = [['hg.plays', r ? fmtBR(r.br) : '—', ''], ['hg.meets', r?.low != null ? `${fmtBR(r.low)} – ${fmtBR(r.high)}` : '—', ''],
    ['stat.rep', fmtStat('rep', hgSum(list, rep)), t('hg.stockSum', { v: fmtStat('rep', hgSum(list, stock)) })],
    ['stat.slm', hgRange(slm, hgPercent), ''], ['stat.rpm', hgRange(rpm, hgPercent), '']];
  const chips = v => [r?.far.includes(v.id) && `<span class="chip warn" title="${esc(t('hg.farHint'))}">${esc(t('hg.far', { br: fmtBR(Math.max(...list.map(x => at(x) ?? 0)) - at(v)) }))}</span>`,
    r?.out.includes(v.id) && `<span class="chip warn" title="${esc(t('hg.rule.naval'))}">${esc(t('hg.out'))}</span>`,
    !HG.owned.has(v.id) && `<span class="chip dim">${esc(t('hg.notOwned'))}</span>`].filter(Boolean).join('');
  return `${hgLineupBar(line)}
    <div class="fl-bar hg-bar"><div class="seg" id="hgMode">${MODES.map(m => `<button class="${m === line.mode ? 'active' : ''}" data-hgmode="${m}">${esc(t('filters.mode.' + m))}</button>`).join('')}</div>
      ${hgPicker(line, mode)}
      <label class="switch"><input type="checkbox" id="hgPlanning"${HG.planning ? ' checked' : ''}><span class="sw"></span><span>${esc(t('hg.planning'))}</span></label></div>
    <div class="vstats mb-totals ch-totals">${tiles.map(([k, x, sub]) => `<div class="vstat"><span>${esc(t(k))}</span><b>${esc(x)}</b><small class="muted">${esc(sub)}</small></div>`).join('')}</div>
    ${r ? `<p class="hint mb-note">${esc(t('hg.rule.' + r.rule))} ${esc(t('hg.source'))}</p>` : ''}
    ${list.length ? `<div class="ar-scroll hg-lineup"><table class="ar-table hg-table"><thead><tr><th>${esc(t('mb.vehicle'))}</th><th class="num">BR</th><th class="num">${esc(t('stat.rep'))}</th>
        <th class="num">${esc(t('hg.colSl'))}</th><th class="num">${esc(t('hg.colRp'))}</th><th></th></tr></thead>
      <tbody>${list.map(v => `<tr><td><span class="hg-vehicle">${mbVehicle(v.id, flagHTML(v.n) + unitImgTag(v.id))}${chips(v)}</span></td><td class="num">${esc(fmtBR(at(v)))}</td>
        <td class="num">${esc(fmtStat('rep', rep(v)))}</td><td class="num">${esc(fmtStat('slm', v.s?.slm?.[mode]))}</td><td class="num">${esc(fmtStat('rpm', v.s?.rpm))}</td>
        <td class="hg-actions"><button class="btn btn-sm btn-primary" data-hgtest="${esc(v.id)}">${icon('play', 'ic-sm')}<span>${esc(t('hg.test'))}</span></button>
          <button class="icon-btn" data-hgrm="${esc(v.id)}" title="${esc(t('compare.remove'))}">${icon('x', 'ic-sm')}</button></td></tr>`).join('')}</tbody></table></div>`
    : `<div class="empty"><p>${esc(t('hg.noVehicle'))}</p></div>`}`;
}

// picks the vehicle and its map, then creates the mission, as the bar's button does
async function hgTestDrive(id) {
  showView('vehicles');
  await openVehicle(id);
  selectVehicle(id);
  if (!pickedScenario()) {
    S.pick.scenario = (scenariosFor(S.byId.get(id), false)[0] || S.scenarios[0])?.id || '';
    savePick();
    renderPickbar();
  }
  await createFromPick($('[data-pk-go]'));
}

// ------------------------------------------------------------------ research plan
function hgPlanHTML() {
  const done = new Set(HG.owned);  // what an earlier goal researches is paid once
  const goals = HG.goals.map(id => S.byId.get(id)).filter(Boolean).map(v => {
    const skip = new Set(done), left = researchPath(v).filter(x => !skip.has(x.id));
    left.forEach(x => done.add(x.id));
    return { v, skip, left };
  });
  const sum = (list, k) => hgSum(list, x => x.s?.[k]), all = goals.flatMap(g => g.left);
  const tiles = [['hg.leftVehicles', I18N.num(all.length)], ['hg.leftRp', fmtStat('rp', sum(all, 'rp'))], ['hg.leftSl', fmtStat('sl', sum(all, 'sl'))]];
  const form = `<div class="hg-row"><label class="search ar-search hg-goal">${icon('search')}<input id="hgGoal" type="search" list="hgGoals" autocomplete="off" spellcheck="false" placeholder="${esc(t('hg.goalAdd'))}"></label>
    <datalist id="hgGoals">${S.vehicles.filter(v => !v.h && v.ra !== 6).map(v => `<option value="${esc(hgGoalName(v))}"></option>`).join('')}</datalist></div>`;
  if (!goals.length) return `${form}<div class="empty">${icon('target', 'ic-xl')}<p>${esc(t('hg.noGoal'))}</p><p>${esc(t('hg.noGoalHint'))}</p></div>`;
  return `${form}<div class="vstats mb-totals ch-totals">${tiles.map(([k, x]) => `<div class="vstat"><span>${esc(t(k))}</span><b>${esc(x)}</b></div>`).join('')}</div>
    <p class="hint mb-note">${esc(t('hg.planHint'))}</p>
    <div class="list hg-goals">${goals.map(({ v, skip, left }, i) => `<div class="list-item">${listThumb(v.id)}
      <div class="list-main"><div class="list-title">${flagHTML(v.n)}${mbVehicle(v.id)}${HG.owned.has(v.id) ? `<span class="chip info">${esc(t('hg.done'))}</span>` : ''}</div>
        <div class="list-sub">${esc(left.length ? `${t('hg.left', { n: left.length })} · ${fmtStat('rp', sum(left, 'rp'))} · ${fmtStat('sl', sum(left, 'sl'))}` : t('hg.nothingLeft'))}</div>
        ${researchPathHTML(v, skip)}</div>
      <div class="list-actions"><div class="ov-move"><button class="icon-btn" data-hgmove="-1" data-i="${i}"${i ? '' : ' disabled'} title="${esc(t('ov.up'))}">▲</button><button class="icon-btn" data-hgmove="1" data-i="${i}"${i < goals.length - 1 ? '' : ' disabled'} title="${esc(t('ov.down'))}">▼</button></div>
        <button class="icon-btn btn-danger" data-hggoalrm="${esc(v.id)}" title="${esc(t('action.delete'))}">${icon('trash')}</button></div></div>`).join('')}</div>`;
}

const hgGoalName = v => `${I18N.unit(v.id)} (${nationName(v.n)}, ${ROMAN[v.r] || v.r}, ${t('cat.' + v.c)})`;

// ------------------------------------------------------------------ page
function hgRender() {
  $$('#hgTabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === HG.tab));
  $('#hgBody').innerHTML = { owned: hgOwnedHTML, lineups: hgLineupsHTML, plan: hgPlanHTML }[HG.tab]();
}

async function openHangarView() {
  try {
    await HG.loading;
    if (!MB.rows) await mbLoad();
  } catch { /* no game, no battles to offer */ }
  hgRender();
}

async function hgLoad() {
  const h = await api('hangar');
  Object.assign(HG, h, { owned: new Set(h.owned), ignored: new Set(h.ignored), loaded: true });
  if (h.damaged) toast({ title: t('hg.damaged'), err: true, ms: 0 });
  hgMarks();
  applyFilters();
}

function onHangarClick(e) {
  const b = e.target.closest('button');
  if (!b) return void mbFollow(e);
  const d = b.dataset, line = HG.lineups.find(x => x.id === HG.line);
  if (d.hgcell !== undefined) {
    const [n, r] = d.hgcell.split('|');
    return hgMarkMany(S.vehicles.filter(v => hgCanOwn(v) && (!n || v.n === n) && (!r || v.r === +r)).map(v => v.id));
  }
  if (d.hgcat) { HG.cat = d.hgcat; return hgRender(); }
  if (d.hgsee !== undefined) { showView('vehicles'); return setFilter({ owned: true, cat: 'all', nations: [], ranks: [] }); }
  if (d.hgplayed !== undefined) return hgMarkMany(hgPlayed().map(([id]) => id));
  if (d.hgyes) return hgSet([d.hgyes], true);
  if (d.hgno) { HG.ignored.add(d.hgno); hgSave(); return hgRender(); }
  if (d.hgmore !== undefined) { HG.allPlayed = true; return hgRender(); }
  if (d.hgnew !== undefined) {
    const name = $('#hgNewName').value.trim() || `${nationName($('#hgNewNation').value)} ${HG.lineups.length + 1}`;
    HG.lineups.push({ id: newId(), name, nation: $('#hgNewNation').value, mode: MODES[S.f.brMode], vehicles: [] });
    HG.line = HG.lineups.at(-1).id;
  } else if (d.hgdel !== undefined) HG.lineups = HG.lineups.filter(x => x !== line);
  else if (d.hgmode) line.mode = d.hgmode;
  else if (d.hgrm) line.vehicles = line.vehicles.filter(id => id !== d.hgrm);
  else if (d.hgtest) return hgTestDrive(d.hgtest);
  else if (d.hggoalrm) HG.goals = HG.goals.filter(id => id !== d.hggoalrm);
  else if (d.hgmove) {
    const i = +d.i, j = i + +d.hgmove;
    [HG.goals[i], HG.goals[j]] = [HG.goals[j], HG.goals[i]];
  } else return void mbFollow(e);
  hgSave();
  hgRender();
}

function onHangarChange(e) {
  const el = e.target, line = HG.lineups.find(x => x.id === HG.line);
  if (el.id === 'hgEvery') HG.every = el.checked;
  else if (el.id === 'hgPlanning') HG.planning = el.checked;
  else if (el.id === 'hgLine') HG.line = el.value;
  else if (el.id === 'hgPick' && el.value) { line.vehicles.push(el.value); hgSave(); }
  else if (el.id === 'hgGoal') {
    const v = S.vehicles.find(x => hgGoalName(x) === el.value);
    if (!v) return;
    if (!HG.goals.includes(v.id)) HG.goals.push(v.id);
    hgSave();
  } else return;
  hgRender();
}

function bindHangar() {
  HG.loading = hgLoad().catch(toastErr);
  $('#hgTabs').addEventListener('click', e => {
    if (!e.target.dataset.tab) return;
    HG.tab = e.target.dataset.tab;
    store.set('hangarTab', HG.tab);
    hgRender();
  });
  $('#hgBody').addEventListener('click', onHangarClick);
  $('#hgBody').addEventListener('change', onHangarChange);
  $('#gridHangar').addEventListener('click', () => showView('hangar'));
}
