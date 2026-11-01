/* WTFTD — Challenges: scored missions for the picked vehicle (wtftd/challenges.py makes them, mission.apply_challenge writes their
   rules). A goal, a timer, a real end; the score is the time. The list comes from the server, the words from the locales: what
   the mission shows in the game goes with the request, in the app's language. */
'use strict';

const CG = { list: [], results: [], diff: store.get('cgDiff', 'normal'), maps: store.get('cgMaps', {}) };
const CG_GROUPS = ['ground', 'air', 'heli', 'ship'];

const cgMapOf = c => (c.levels.includes(CG.maps[c.id]) ? CG.maps[c.id] : c.levels[0]);
const cgRule = (c, diff) => { const p = c.diffs[diff]; return t(`cg.${c.id}.rule`, { ...p, time: flTime(p.limit || 0) }); };
const cgSid = (c, level, v) => `free_${level}_${c.cats.includes(v?.c) ? v.c : c.cats[0]}`;

function cgTexts(c, diff, level, vid) {
  const rule = cgRule(c, diff), vehicle = I18N.unit(vid);
  return {
    title: t('cg.missionTitle', { name: t('cg.' + c.id), diff: t('cg.diff.' + diff), vehicle, map: mbMapName(level) }),
    description: t('cg.desc', { rule }),
    texts: { goal: t('cg.goal', { vehicle, rule }), start: t('cg.start', { rule }), gate: t('cg.gate'), wave: t('editor.waveText') },
  };
}

// best time and tries of a challenge, on one vehicle and difficulty
function cgScore(id, diff, vehicle) {
  const tries = CG.results.filter(x => x.id === id && x.diff === diff && x.vehicle === vehicle), wins = tries.filter(x => x.result === 'win');
  return { tries: tries.length, wins: wins.length, best: wins.length ? Math.min(...wins.map(x => x.time)) : null, level: tries.at(-1)?.level };
}

const cgDone = (c, s) => (c.id === 'evasion' ? t('cg.done') : flTime(s.best));  // surviving takes the whole time: nothing to beat

function cgRow(c, v) {
  const fits = c.cats.includes(v?.c), level = cgMapOf(c), s = v ? cgScore(c.id, CG.diff, v.id) : { wins: 0 };
  const why = fits ? '' : t(v ? 'cg.needs' : 'pick.chooseVehicle', { kinds: c.cats.map(k => t('cat.' + k)).join(', ') });
  return `<div class="list-item cg-row" data-cg="${esc(c.id)}"><div class="list-thumb">${icon(c.cats[0], 'ic-xl')}</div>
    <div class="list-main"><div class="list-title"><span>${esc(t('cg.' + c.id))}</span>
      <span class="chip ${s.wins ? 'info' : 'dim'}">${esc(s.wins ? (c.id === 'evasion' ? t('cg.done') : t('cg.best', { time: flTime(s.best) })) : t('cg.noResult'))}</span></div>
      <div class="list-sub" title="${esc(cgRule(c, CG.diff))}">${esc(cgRule(c, CG.diff))}</div></div>
    <div class="list-actions"><select class="cg-map" data-cgmap title="${esc(t('mb.map'))}">${c.levels.map(l => `<option value="${esc(l)}"${l === level ? ' selected' : ''}>${esc(mbMapName(l))}</option>`).join('')}</select>
      <button class="btn btn-sm btn-primary" data-cggo ${fits ? '' : `disabled title="${esc(why)}"`}>${icon('play', 'ic-sm')}<span>${esc(t('action.generate'))}</span></button>
      <button class="icon-btn" data-cgshare ${fits ? '' : 'disabled'} title="${esc(t('share.button'))}">${icon('share')}</button></div></div>`;
}

function cgResults() {
  const seen = new Map();
  for (const x of CG.results) seen.set(`${x.id}|${x.diff}|${x.vehicle}`, x);
  const rows = [...seen.values()].reverse().map(x => ({ x, s: cgScore(x.id, x.diff, x.vehicle), c: CG.list.find(c => c.id === x.id) })).filter(r => r.c);
  const heads = ['cg.challenge', 'cg.level', 'mb.vehicle', 'mb.map'];
  return `<h3 class="list-head">${esc(t('cg.results'))}</h3>${rows.length ? `<div class="ar-scroll"><table class="ar-table mb-table">
    <thead><tr>${heads.map(k => `<th>${esc(t(k))}</th>`).join('')}<th class="num">${esc(t('cg.bestTime'))}</th><th class="num">${esc(t('mb.win'))}</th><th class="num">${esc(t('cg.tries'))}</th><th></th></tr></thead>
    <tbody>${rows.map(({ x, s, c }) => `<tr><td>${esc(t('cg.' + x.id))}</td><td>${esc(t('cg.diff.' + x.diff))}</td><td>${mbVehicle(x.vehicle)}</td><td>${mbMap(s.level)}</td>
      <td class="num">${s.wins ? esc(cgDone(c, s)) : '—'}</td><td class="num">${I18N.num(s.wins)}</td><td class="num">${I18N.num(s.tries)}</td>
      <td><button class="btn btn-sm" data-cgagain="${esc(`${x.id}|${x.diff}|${x.vehicle}|${s.level}`)}">${icon('play', 'ic-sm')}<span>${esc(t('cg.again'))}</span></button></td></tr>`).join('')}</tbody>
    </table></div>` : `<p class="muted">${esc(t('cg.noResults'))}</p>`}<p class="hint mb-note">${esc(t('cg.how'))}</p>`;
}

function cgRender() {
  const v = pickedVehicle();
  $('#cgVehicle').innerHTML = `<span class="pk-thumb">${v ? unitImgTag(v.id) : icon('all')}</span>
    <span class="pk-txt"><small>${esc(t('pick.vehicle'))}</small><b>${esc(v ? I18N.unit(v.id) : t('pick.chooseVehicle'))}</b>${v ? `<span>${esc(className(v.k))}</span>` : ''}</span>`;
  $('#cgVehicle').classList.toggle('empty', !v);
  $$('#cgDiff button').forEach(b => b.classList.toggle('active', b.dataset.diff === CG.diff));
  const fit = g => (g === v?.c || (g === 'ship' && v?.c === 'boat') ? 0 : 1);  // the picked vehicle's own first
  const groups = [...CG_GROUPS].sort((a, b) => fit(a) - fit(b));
  $('#cgBody').innerHTML = `${groups.map(g => `<h3 class="list-head">${esc(t('cat.' + g))}</h3>
    <div class="list">${CG.list.filter(c => c.cats[0] === g).map(c => cgRow(c, v)).join('')}</div>`).join('')}${cgResults()}`;
}

async function cgLoad() {
  Object.assign(CG, await api('challenges'));
  if (!$('#view-challenges').classList.contains('hidden')) cgRender();
}

function openChallengesView() {
  if (CG.list.length) cgRender();
  cgLoad().catch(toastErr);
}

async function cgCreate(btn, c, diff, level, vid) {
  const v = S.byId.get(vid), cfg = v && await pickedCfg(v);
  if (!cfg) return;
  const { texts, ...mission } = cgTexts(c, diff, level, vid), open = S.cfg;
  S.cfg = cfg;  // as the bar's Create: the mission is this vehicle's setup
  try { await generate(btn, { ...mission, challenge: { id: c.id, diff, level, texts } }); } finally { S.cfg = open || cfg; }
}

async function cgShare(c, v) {
  const cfg = await pickedCfg(v), level = cgMapOf(c), name = `${t('cg.' + c.id)} · ${I18N.unit(v.id)}`;
  if (cfg) openShareObj({ app: 'WTFTD', v: 2, kind: 'challenge', name, vehicle: v.id, cfg: vehicleOnly(cfg), sid: cgSid(c, level, v), challenge: { id: c.id, diff: CG.diff, level } }, name);
}

// a shared challenge: its vehicle setup, map and difficulty, ready to create
async function cgImport(data) {
  const v = S.byId.get(data.vehicle), d = await vehicleDetails(data.vehicle), { id, diff, level } = data.challenge || {};
  if (d) S.cfgs.set(v.id, normalizeCfg(v, d, vehicleOnly(data.cfg)));
  selectVehicle(v.id);
  cgChoose(id, diff, level);
  showView('challenges');
}

function cgChoose(id, diff, level) {
  if (['easy', 'normal', 'hard'].includes(diff)) store.set('cgDiff', CG.diff = diff);
  if (level) { CG.maps[id] = level; store.set('cgMaps', CG.maps); }
}

function bindChallenges() {
  $('#cgVehicle').addEventListener('click', () => { showView('vehicles'); if (S.pick.vehicle) openVehicle(S.pick.vehicle); else $('#search').focus(); });
  $('#cgVehicle').addEventListener('keydown', e => { if (e.key === 'Enter') e.target.click(); });
  $('#cgDiff').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { cgChoose('', b.dataset.diff); cgRender(); } });
  $('#cgBody').addEventListener('change', e => {
    const id = e.target.closest('[data-cgmap]') && e.target.closest('[data-cg]').dataset.cg;
    if (id) cgChoose(id, '', e.target.value);
  });
  $('#cgBody').addEventListener('click', e => {
    mbFollow(e);
    const b = e.target.closest('button');
    if (!b || b.disabled) return;
    const c = CG.list.find(x => x.id === b.closest('[data-cg]')?.dataset.cg), v = pickedVehicle();
    if ('cggo' in b.dataset) cgCreate(b, c, CG.diff, cgMapOf(c), v.id);
    else if ('cgshare' in b.dataset) cgShare(c, v);
    else if (b.dataset.cgagain) {
      const [id, diff, vid, level] = b.dataset.cgagain.split('|');
      cgCreate(b, CG.list.find(x => x.id === id), diff, level, vid);
    }
  });
  addEventListener('focus', () => { if (!$('#view-challenges').classList.contains('hidden')) cgLoad().catch(() => {}); });  // back from the game
}
