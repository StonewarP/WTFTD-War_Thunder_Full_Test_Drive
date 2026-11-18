/* WTFTD - Best vehicles: the vehicles of a type ranked for a play style at a BR by the duels they win against everything they
   can meet there (web/duel.js), and for one of them every opponent with the stats that decide each duel. */
'use strict';

const BV_PAGE = 100;  // rows added at a time
const BV = { f: { type: 'air', style: '', mode: 1, br: null, ranks: [], nations: [], owned: false, removed: false, only: true, sort: 'score', dir: -1,
                  ...store.get('bv', {}) }, shown: BV_PAGE, open: '', ranked: null };
const BV_VERDICTS = ['adv', 'even', 'dis', 'na'];
const BV_ARMOR = ['front', 'side'];  // the duel terms read from the stat card's nominal armor

// the style picked, set right when a saved choice no longer fits (naval has no Simulator battles)
function bvStyle() {
  const f = BV.f;
  if (!Object.hasOwn(BV_STYLES, f.type)) f.type = 'air';
  const st = bvStyleOf(f.type, f.style) || BV_STYLES[f.type][0];
  f.style = st.id;
  if (!st.modes.includes(MODES[f.mode])) f.mode = 1;
  return st;
}

const bvCtx = () => ({ vehicles: S.vehicles, type: BV.f.type, style: BV.f.style, mode: BV.f.mode, br: BV.f.br, stock: !S.upg, onlyStyle: BV.f.only });

// the ranking, kept while only the filters change: they hide rows, they never change a score
function bvRanked() {
  const ctx = bvCtx(), key = JSON.stringify({ ...ctx, vehicles: S.vehicles.length });
  if (BV.ranked?.key !== key) {
    BV.ranked = { key, rows: bvRank(ctx) };
    BV.shown = BV_PAGE;  // a new order: each row shown runs its duels again for its strongest and weakest stats
  }
  return BV.ranked.rows;
}

function bvRows(st, ranked) {
  const f = BV.f, br = r => bvBr(r.v, f.mode, st.brField) ?? 99, name = r => I18N.unit(r.v.id);
  const none = r => !(r.w + r.e + r.l) && r.mission == null;  // no verdict and no mission part: no score, after every scored row
  const rows = ranked.filter(({ v }) => (!f.ranks.length || f.ranks.includes(v.r)) && (!f.nations.length || f.nations.includes(v.n))
    && (!f.owned || HG.owned.has(v.id)) && (f.removed || v.ra !== 5)).sort((a, b) => none(a) - none(b));
  rows.forEach((r, i) => { r.pos = i + 1; });  // its place by score among the rows shown, whatever the sort
  const by = { score: (a, b) => b.pos - a.pos, pos: (a, b) => a.pos - b.pos, br: (a, b) => br(a) - br(b), rank: (a, b) => (a.v.r || 0) - (b.v.r || 0),
    name: (a, b) => name(a).localeCompare(name(b), I18N.code, { numeric: true }) }[f.sort] || (() => 0);
  return rows.sort((a, b) => (f.sort === 'score' && none(a) - none(b)) || by(a, b) * f.dir || a.pos - b.pos);
}

// a row's strongest and weakest duel stats against its window: the largest sums of weight x term over its duels
function bvTraits(r) {
  if (!r.traits) {
    const sum = {};
    for (const { res } of bvMatchups(r, bvCtx())) if (res.v !== 'na') for (const x of res.terms) sum[x.k] = (sum[x.k] || 0) + x.w * x.t;
    const ks = Object.keys(sum).sort((a, b) => sum[b] - sum[a]);
    r.traits = [sum[ks[0]] > 0 ? ks[0] : '', sum[ks.at(-1)] < 0 ? ks.at(-1) : ''];
  }
  return r.traits;
}

// a duel term's name and values: a stat's own, else the duel's (penetration at a range, reach, armor); pwr is the
// aircraft's own ratio, power for propellers and thrust for jets
const bvStat = (k, v) => (k === 'pwr' && v ? (bvJet(v) ? 'tw' : 'pw') : k);
const bvLabel = (k, c) => (STATS[k] ? statLabel(k, c) : t('bv.k.' + k));
const bvFmt = (k, x) => (STATS[k] ? fmtStat(k, x) : k === 'front' ? `×${I18N.num(+x.toFixed(2))}` : `${I18N.num(Math.round(x))} ${k === 'reach' ? 'm' : 'mm'}`);

// a duel stat as a chip (better: info, worse: warn), its title saying which in words (what: a key); an armor one ends
// with an asterisk, and its title adds the armor note
function bvChipHTML(cls, k, text, what) {
  const armor = BV_ARMOR.includes(k);
  return `<span class="chip ${cls}" title="${esc(t(what) + (armor ? '\n' + t('bv.armor') : ''))}">${esc(text)}${armor ? '*' : ''}</span>`;
}

// a duel's reasons: its three heaviest terms, and the gate that changed it
function bvReasonsHTML(v, res) {
  return res.terms.filter(x => x.t).slice(0, 3).map(x => {
    const k = bvStat(x.k, v), text = `${bvLabel(k, v.c)} ${t('bv.vs', { a: bvFmt(k, x.a), b: bvFmt(k, x.b) })}`;
    return x.t > 0 ? bvChipHTML('info', k, text, 'bv.better') : bvChipHTML('warn', k, text, 'bv.worse');
  }).join('') + (res.gate ? `<span class="chip warn">${esc(t('bv.gate.' + res.gate))}</span>` : '');
}

// a row's opponents by verdict, the hardest first among its losses; the vehicle's actions, and a comparison with each
function bvMatchupsHTML(st, r) {
  const v = r.v, ctx = bvCtx(), ms = bvMatchups(r, ctx), by = Object.fromEntries(BV_VERDICTS.map(x => [x, []]));
  for (const m of ms) by[m.res.v].push(m);
  by.dis.reverse();
  const at = o => fmtBR(bvBr(o, ctx.mode, st.foes.find(x => x.is(o))?.brField));
  const foe = ({ o, res }) => `<div class="bv-foe"><span class="bv-foe-name">${flagHTML(o.n)}<b>${esc(I18N.unit(o.id))}</b><small class="muted">${esc(at(o))}</small></span>
    <span class="bv-why">${bvReasonsHTML(v, res)}</span><button class="icon-btn" data-bvcmp="${esc(o.id)}" title="${esc(t('bv.compare'))}">${icon('sliders', 'ic-sm')}</button></div>`;
  const groups = BV_VERDICTS.filter(x => x !== 'na' || by.na.length)
    .map(x => `<h4 class="ar-lbl">${esc(t('bv.v.' + x))} · ${I18N.num(by[x].length)}</h4><div class="bv-foes">${by[x].map(foe).join('')}</div>`).join('');
  return `<div class="bv-det"><div class="bv-acts"><button class="btn btn-sm" data-bvopen="${esc(v.id)}">${esc(t('fl.open'))}</button>
      <button class="btn btn-sm btn-primary" data-bvtest="${esc(v.id)}">${icon('play', 'ic-sm')}<span>${esc(t('hg.test'))}</span></button></div>
    ${ms.length ? groups : `<p class="hint">${esc(t(r.off ? 'bv.noStyle' : 'bv.noFoes'))}</p>`}</div>`;
}

function bvRowHTML(st, r) {
  const v = r.v, open = BV.open === v.id, k = r.w + r.e + r.l, scored = k || r.mission != null, score = Math.round((r.score + 1) * 50);
  const why = k ? (r.mission != null ? t('bv.split', { d: Math.round((r.net + 1) * 50), m: Math.round((r.mission + 1) * 50) }) : '') : t(r.off ? 'bv.noStyle' : r.na ? 'bv.v.na' : 'bv.noFoes');
  const [best, worst] = bvTraits(r), trait = (x, cls, what) => (x ? bvChipHTML(cls, x, bvLabel(bvStat(x, v), v.c), what) : '');
  return `<tr data-bvrow="${esc(v.id)}"${open ? ' class="open"' : ''}><td class="num">${scored ? r.pos : ''}</td>
    <td class="bv-name"><button class="mb-link" data-bvrow="${esc(v.id)}" aria-expanded="${open}">${flagHTML(v.n)}${unitImgTag(v.id)}<span><b>${esc(I18N.unit(v.id))}</b>
      <small class="muted">${esc(className(v.k))}</small></span></button>${rarityTag(v)}</td>
    <td class="num">${ROMAN[v.r] || v.r || ''}</td><td class="num">${esc(fmtBR(bvBr(v, BV.f.mode, st.brField)))}</td>
    <td class="ar-score" title="${esc(why)}">${scored ? `<span class="bar"><i style="width:${score}%"></i></span><b>${score}</b>` : ''}</td>
    <td class="num"${r.na ? ` title="${esc(`${t('bv.v.na')}: ${I18N.num(r.na)}`)}"` : ''}>${r.w} / ${r.e} / ${r.l}</td>
    <td class="bv-traits">${trait(best, 'info', 'bv.best')}${trait(worst, 'warn', 'bv.worst')}</td></tr>
    ${open ? `<tr class="ar-detail"><td colspan="7">${bvMatchupsHTML(st, r)}</td></tr>` : ''}`;
}

function bvTableHTML(st, rows) {
  const f = BV.f, shown = rows.slice(0, BV.shown);
  const th = (k, label, cls = '') => {
    const on = f.sort === k, up = f.dir > 0;
    return `<th class="sortable${on ? ' sorted' : ''}${cls}"${on ? ` aria-sort="${up ? 'ascending' : 'descending'}"` : ''}><button type="button" data-bvsort="${k}">${esc(label)}${
      on ? `<span aria-hidden="true">&nbsp;${up ? '▲' : '▼'}</span>` : ''}</button></th>`;
  };
  return `<div class="ar-scroll"><table class="ar-table bv-table"><thead><tr>${th('pos', '#', ' num')}${th('name', t('mb.vehicle'))}${th('rank', t('filters.rank'), ' num')}
      ${th('br', 'BR', ' num')}${th('score', t('arm.col.score'))}<th class="num">${esc(t('bv.col.wel'))}</th><th>${esc(t('bv.col.traits'))}</th></tr></thead>
    <tbody>${shown.map(r => bvRowHTML(st, r)).join('')}</tbody></table></div>
    ${rows.length > shown.length ? `<button class="btn btn-sm ch-more" data-bvmore>${esc(t('ch.more', { n: I18N.num(Math.min(rows.length - shown.length, BV_PAGE)) }))}</button>` : ''}`;
}

// where they apply: armor on ground styles, Arcade for aircraft in ground battles, Simulator's rotating brackets
function bvNotesHTML(st) {
  const keys = [...st.notes.filter(n => n !== 'abApprox' || BV.f.mode === 0).map(n => 'bv.' + n), BV.f.mode === 2 && 'bv.sb'];
  return keys.filter(Boolean).map(k => `<p class="ar-note bv-note">${esc(t(k))}</p>`).join('');
}

// what the style weighs, as the duel counts it in this mode (Arcade changes a few weights)
function bvWeightsHTML(st) {
  const cat = BV_TYPES[BV.f.type][0], ab = (BV.f.mode === 0 && BV_AB[cat]) || {};
  const list = ws => Object.entries(ws).map(([k, w]) => `${esc(bvLabel(k, cat))} <b>${I18N.num(+(w * (ab[k] ?? 1)).toFixed(2))}</b>`).join(' · ');
  const who = i => t(st.foes.length > 1 ? `bv.foe.${st.id}.${i}` : 'bv.duel');  // close air support meets SPAA and fighters
  return `<p class="hint bv-weights">${st.foes.map((x, i) => `${esc(who(i))}: ${list(x.terms)}`).join('<br>')}
    ${st.mission ? `<br>${esc(t('bv.mission', { n: Math.round(st.m * 100) }))}: ${list(st.mission)}` : ''}</p>`;
}

function bvBarHTML(st, brs, ranks, nations) {
  const f = BV.f;
  const sw = (k, key) => `<label class="switch"><input type="checkbox" data-bvsw="${k}"${f[k] ? ' checked' : ''}><span class="sw"></span><span>${esc(t(key))}</span></label>`;
  const pick = (on, cls = '') => `class="${cls}${on ? ' active' : ''}" aria-pressed="${on}"`;
  return `<div class="fl-bar">
      <div class="seg">${Object.keys(BV_TYPES).map(x => `<button ${pick(x === f.type)} data-bvtype="${x}">${esc(t(x === 'naval' ? 'bv.naval' : 'cat.' + x))}</button>`).join('')}</div>
      <div class="seg">${MODES.map((m, i) => `<button ${pick(i === f.mode)} data-bvmode="${i}"${st.modes.includes(m) ? '' : ' disabled'}>${esc(t('filters.mode.' + m))}</button>`).join('')}</div>
      <select id="bvBr" title="${esc(t('filters.br'))}"><option value="">${esc(t('bv.everyBr'))}</option>${brs.map(b => `<option value="${b}"${b === f.br ? ' selected' : ''}>${esc(fmtBR(b))}</option>`).join('')}</select>
      ${upgSwitchHTML(AIR.includes(BV_TYPES[f.type][0]))}</div>
    <div class="ar-cats">${BV_STYLES[f.type].map(s => `<button ${pick(s === st, 'chipbtn')} data-bvstyle="${s.id}">${esc(t('bv.style.' + s.id))}</button>`).join('')}</div>
    <p class="hint">${esc(t('bv.styleh.' + st.id))}</p>${bvWeightsHTML(st)}
    <div class="fl-bar"><div class="ar-chips">${ranks.map(r => `<button ${pick(f.ranks.includes(r), 'chipbtn')} data-bvrank="${r}" title="${esc(t('rank', { r: ROMAN[r] || r }))}">${ROMAN[r] || r}</button>`).join('')}</div>
      <div class="ar-chips">${nations.map(n => `<button ${pick(f.nations.includes(n), 'chipbtn bv-nat')} data-bvnation="${n}" title="${esc(nationName(n))}">${flagHTML(n)}</button>`).join('')}</div>
      ${sw('owned', 'filters.owned')}${sw('removed', 'bv.removed')}${sw('only', 'bv.only')}</div>`;
}

function bvBody(st = bvStyle()) {
  const ranked = bvRanked(), rows = bvRows(st, ranked);
  const empty = !ranked.length ? 'bv.noCand' : BV.f.owned && !HG.owned.size ? 'hg.emptyGrid' : 'results.empty';  // nothing marked yet: the Vehicles page's words
  $('#bvBody').innerHTML = `${bvNotesHTML(st)}${rows.length ? bvTableHTML(st, rows) : `<div class="empty"><p>${esc(t(empty))}</p></div>`}
    <p class="hint mb-note">${esc(t('bv.statsOnly'))}</p>`;
  return rows;
}

function bvRender() {
  const st = bvStyle(), f = BV.f, pool = bvPool(S.vehicles).filter(v => BV_TYPES[f.type].includes(v.c));
  // the BRs that have rows: the style's candidates when only those are ranked, removed vehicles when shown
  const brs = [...new Set(pool.filter(v => (!f.only || st.cand(v, !S.upg)) && (f.removed || v.ra !== 5)).map(v => bvBr(v, f.mode, st.brField)))]
    .filter(b => b != null).sort((a, b) => a - b);
  const ranks = [...new Set(pool.map(v => v.r))].filter(Boolean).sort((a, b) => a - b), nations = NATIONS.filter(n => pool.some(v => v.n === n));
  // a choice these switches, type, mode or style don't have: the nearest BR with rows, and no rank or nation left that would hide every row unseen
  if (f.br != null && !brs.includes(f.br)) f.br = brs.reduce((x, b) => (Math.abs(b - f.br) < Math.abs(x - f.br) ? b : x), brs[0] ?? null);
  f.ranks = f.ranks.filter(r => ranks.includes(r));
  f.nations = f.nations.filter(n => nations.includes(n));
  $('#bvBar').innerHTML = bvBarHTML(st, brs, ranks, nations);
  bvBody(st);
}

// the Stock / upgraded switch and My hangar's marks change what the page shows; the bar's switch drawn again keeps the
// keyboard (a press in the drawer or the compare dialog keeps its own)
function bvRefresh() {
  if ($('#view-best').classList.contains('hidden')) return;
  const el = document.activeElement, up = $('#bvBar').contains(el) && el.dataset.upgset;
  bvRender();
  if (up) $(`#bvBar [data-upgset="${up}"]`)?.focus();
}

async function openBestView() {
  await HG.loading;  // the vehicles marked as owned
  bvRender();
}

const bvToggle = (list, x) => (list.includes(x) ? list.filter(y => y !== x) : [...list, x]);

// a control drawn again keeps the keyboard: found again by its id or its data-bv attribute
function bvFocus(el) {
  const k = Object.keys(el.dataset).find(x => x.startsWith('bv'));
  $(el.id ? `#${el.id}` : `[data-${k}="${CSS.escape(el.dataset[k])}"]`)?.focus();
}

function bvChanged(el) {
  BV.shown = BV_PAGE;
  BV.open = '';
  store.set('bv', BV.f);
  bvRender();
  bvFocus(el);
}

function bvClick(e) {
  const b = e.target.closest('button, [data-bvsort], [data-bvrow]');
  if (!b || b.disabled) return;
  const d = b.dataset, f = BV.f;
  if (d.bvrow) {
    BV.open = BV.open === d.bvrow ? '' : d.bvrow;
    bvBody();
    return $(`button[data-bvrow="${CSS.escape(d.bvrow)}"]`)?.focus();  // drawn again: the keyboard stays on the row
  }
  if (d.bvsort) {
    [f.sort, f.dir] = f.sort === d.bvsort ? [f.sort, -f.dir] : [d.bvsort, d.bvsort === 'score' ? -1 : 1];
    store.set('bv', f);
    bvBody();
    return bvFocus(b);
  }
  if ('bvmore' in d) {
    BV.shown += BV_PAGE;
    return $(`button[data-bvrow="${CSS.escape(bvBody()[BV.shown - BV_PAGE]?.v.id)}"]`)?.focus();  // on the first row added
  }
  if (d.bvopen) { showView('vehicles'); return openVehicle(d.bvopen); }
  if (d.bvtest) return hgTestDrive(d.bvtest);
  if (d.bvcmp) return openCompare([BV.open, d.bvcmp]);  // a list of its own: the user's compare tray stays as it was
  if (d.bvtype) Object.assign(f, { type: d.bvtype, style: d.bvtype === f.type ? f.style : '' });  // another type: its first style
  else if (d.bvmode) f.mode = +d.bvmode;
  else if (d.bvstyle) f.style = d.bvstyle;
  else if (d.bvrank) f.ranks = bvToggle(f.ranks, +d.bvrank);
  else if (d.bvnation) f.nations = bvToggle(f.nations, d.bvnation);
  else return;
  bvChanged(b);
}

function bvChange(e) {
  const el = e.target;
  if (el.id === 'bvBr') BV.f.br = el.value === '' ? null : +el.value;
  else if (el.dataset.bvsw) BV.f[el.dataset.bvsw] = el.checked;
  else return;
  bvChanged(el);
}

function bindBest() {
  $('#view-best').addEventListener('click', bvClick);
  $('#view-best').addEventListener('change', bvChange);
}
