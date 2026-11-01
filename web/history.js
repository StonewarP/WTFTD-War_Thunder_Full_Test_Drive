/* WTFTD — My battles: the player's own results, from the replays the game saves (wtftd/replays.py). The list comes once
   when the page opens, and the filters run here. */
'use strict';

const MB = { rows: null, skipped: 0, teamkills: [], game: true, mode: '', vehicle: '', map: '', from: '', to: '', result: '', offline: false };

const mbMode = r => (r.offline ? t('mb.test') : [r.kind && t('kind.' + r.kind), r.diff && t('filters.mode.' + r.diff)].filter(Boolean).join(' ') || '—');
const mbMapName = level => mapName(level, S.scenarios.filter(s => s.map === level));
const mbMap = level => (S.scenarios.some(s => s.map === level)
  ? `<button class="mb-link" data-mbmap="${esc(level)}">${esc(mbMapName(level))}</button>` : esc(mbMapName(level)));
const mbVehicle = (id, picture = '') => (S.byId.has(id)
  ? `<button class="mb-link" data-mbvehicle="${esc(id)}">${picture}<span>${esc(I18N.unit(id))}</span></button>` : esc(I18N.unit(id)));
const mbDate = s => new Date(s * 1000).toLocaleString(I18N.code, { dateStyle: 'short', timeStyle: 'short' });
const mbDuration = s => `${Math.floor(s / 3600)} h ${String(Math.floor(s / 60) % 60).padStart(2, '0')} min`;

function mbShown() {
  const from = MB.from && new Date(`${MB.from}T00:00:00`) / 1000, to = MB.to && new Date(`${MB.to}T23:59:59`) / 1000;
  return MB.rows.filter(r => (MB.offline || !r.offline) && (!MB.mode || mbMode(r) === MB.mode) && (!MB.vehicle || r.vehicles.includes(MB.vehicle))
    && (!MB.map || r.level === MB.map) && (!MB.result || r.result === MB.result) && (!from || r.start >= from) && (!to || r.start <= to));
}

function mbTotals(rows) {
  const sum = k => rows.reduce((n, r) => n + r[k], 0), count = x => rows.filter(r => r.result === x).length;
  const won = count('win'), lost = count('loss'), kills = sum('kills'), deaths = sum('deaths'), played = sum('played');
  const tiles = [
    ['mb.battles', I18N.num(rows.length), t('mb.split', { won, lost, left: count('left') })],
    ['mb.winRate', won + lost ? `${Math.round(won / (won + lost) * 100)} %` : '—', t('mb.rateOf', { n: won + lost })],
    ['mb.kd', flNum(kills / Math.max(deaths, 1)), t('mb.kdOf', { kills, deaths })],
    ['mb.time', mbDuration(played), t('mb.average', { time: flTime(rows.length ? played / rows.length : 0) })],
  ];
  return `<div class="vstats mb-totals">${tiles.map(([k, v, sub]) => `<div class="vstat"><span>${esc(t(k))}</span><b>${esc(v)}</b><small class="muted">${esc(sub)}</small></div>`).join('')}</div>`;
}

function mbByVehicle(rows) {
  const by = new Map();
  for (const r of rows) {
    for (const id of r.vehicles) {
      if (!by.has(id)) by.set(id, { id, battles: 0, wins: 0, kills: 0, deaths: 0 });
      const v = by.get(id);
      v.battles++;
      v.wins += r.result === 'win';
      v.kills += r.kills;
      v.deaths += r.deaths;
    }
  }
  const list = [...by.values()].sort((a, b) => b.battles - a.battles || I18N.unit(a.id).localeCompare(I18N.unit(b.id)));
  if (!list.length) return '';
  return `<h3 class="list-head">${esc(t('mb.byVehicle'))}</h3><div class="ar-scroll mb-vehicles"><table class="ar-table mb-table">
    <thead><tr><th>${esc(t('mb.vehicle'))}</th>${['mb.battles', 'mb.win', 'mb.kills', 'mb.deaths'].map(k => `<th class="num">${esc(t(k))}</th>`).join('')}</tr></thead>
    <tbody>${list.map(v => `<tr><td>${mbVehicle(v.id, unitImgTag(v.id))}</td>${[v.battles, v.wins, v.kills, v.deaths].map(n => `<td class="num">${I18N.num(n)}</td>`).join('')}</tr>`).join('')}</tbody>
    </table></div><p class="hint mb-note">${esc(t('mb.several'))}</p>`;
}

// who shot the player down from their own team: other players choose their names, everything goes through esc()
function mbTeamkills() {
  const by = new Map();
  for (const x of MB.teamkills) by.set(x.name, { ...x, times: (by.get(x.name)?.times || 0) + 1 });  // oldest first: the last one stays
  const list = [...by.values()].sort((a, b) => b.times - a.times || b.at - a.at);
  return `<h3 class="list-head">${esc(t('mb.tkTitle'))}</h3>${list.length ? `<div class="ar-scroll mb-vehicles"><table class="ar-table mb-table">
    <thead><tr><th>${esc(t('mb.tkPlayer'))}</th><th class="num">${esc(t('mb.tkTimes'))}</th><th>${esc(t('mb.tkLast'))}</th><th>${esc(t('mb.map'))}</th></tr></thead>
    <tbody>${list.map(x => `<tr><td>${esc([x.clan, x.name].filter(Boolean).join(' '))}</td><td class="num">${I18N.num(x.times)}</td><td>${esc(mbDate(x.at))}</td><td>${mbMap(x.level)}</td></tr>`).join('')}</tbody>
    </table></div>` : `<p class="muted">${esc(t('mb.tkNone'))}</p>`}<p class="hint mb-note">${esc(t('mb.tkHint'))}</p>`;
}

function mbRow(r) {
  const nums = [flTime(r.played), r.kills, r.deaths, r.assists, r.score, r.damage];
  const ai = r.ai ? ` <small class="muted" title="${esc(t('mb.ai'))}">+${r.ai}</small>` : '';
  return `<tr><td>${esc(mbDate(r.start))}</td>
    <td>${mbMap(r.level)}</td><td title="${esc(r.title)}">${esc(mbMode(r))}</td>
    <td>${r.vehicles.map(id => mbVehicle(id)).join(', ') || '—'}</td>
    <td><span class="chip ${{ win: 'info', loss: 'warn', left: 'dim' }[r.result]}">${esc(t('mb.' + r.result))}</span></td>
    ${nums.map((n, i) => `<td class="num">${esc(typeof n === 'number' ? I18N.num(n) : n)}${i === 1 ? ai : ''}</td>`).join('')}</tr>`;
}

function mbSelect(el, key, all, options) {
  const list = [...new Map(options)].sort((a, b) => a[1].localeCompare(b[1]));
  if (!list.some(([v]) => v === MB[key])) MB[key] = '';  // gone with the test drives
  $(el).innerHTML = `<option value="">${esc(t(all))}</option>${list.map(([v, x]) => `<option value="${esc(v)}"${v === MB[key] ? ' selected' : ''}>${esc(x)}</option>`).join('')}`;
}

function mbRender() {
  const body = $('#mbBody'), bar = $('#mbBar'), empty = (...lines) => `<div class="empty">${icon('folder', 'ic-xl')}${lines.map(x => `<p>${esc(x)}</p>`).join('')}</div>`;
  bar.classList.toggle('hidden', !MB.rows?.length);
  if (!MB.rows) return void (body.innerHTML = empty(t('mb.loading')));
  if (!MB.rows.length) {
    body.innerHTML = MB.game ? empty(t('mb.noReplays'), t('mb.autosave')) : empty(t('mb.noGame'));
    return;
  }
  const pool = MB.rows.filter(r => MB.offline || !r.offline);
  mbSelect('#mbMode', 'mode', 'mb.allModes', pool.map(r => [mbMode(r), mbMode(r)]));
  mbSelect('#mbVehicle', 'vehicle', 'mb.allVehicles', pool.flatMap(r => r.vehicles.map(id => [id, I18N.unit(id)])));
  mbSelect('#mbMap', 'map', 'mb.allMaps', pool.map(r => [r.level, mbMapName(r.level)]));
  const rows = mbShown();
  const heads = ['mb.date', 'mb.map', 'mb.mode', 'mb.vehicle', 'mb.result'], nums = ['mb.time', 'mb.kills', 'mb.deaths', 'mb.assists', 'mb.score', 'mb.damage'];
  body.innerHTML = `${mbTotals(rows)}<p class="hint mb-note">${esc(t('mb.limits'))}</p>${mbByVehicle(rows)}${mbTeamkills()}
    <h3 class="list-head">${esc(t('mb.battles'))}</h3>
    ${rows.length ? `<div class="ar-scroll"><table class="ar-table mb-table"><thead><tr>${heads.map(k => `<th>${esc(t(k))}</th>`).join('')}${nums.map(k => `<th class="num">${esc(t(k))}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(mbRow).join('')}</tbody></table></div>` : `<p class="muted">${esc(t('mb.none'))}</p>`}
    ${MB.skipped ? `<p class="hint mb-note">${esc(t('mb.skipped', { n: MB.skipped }))}</p>` : ''}`;
}

// the replays also give the player's name: it stands in the top bar like an account's
async function mbLoad() {
  Object.assign(MB, await api('battles'));
  $('#accountName').textContent = [MB.rows[0]?.clan, MB.rows[0]?.me].filter(Boolean).join(' ');
  $('#btnAccount').classList.toggle('hidden', !MB.rows.length);
}

async function openHistoryView() {
  mbRender();
  try {
    await mbLoad();
    mbRender();
  } catch (e) { toastErr(e); }
}

// a link of mbMap / mbVehicle, here and in What changed
function mbFollow(e) {
  const b = e.target.closest('[data-mbmap], [data-mbvehicle]');
  if (!b) return;
  if (b.dataset.mbmap) { showView('maps'); openMapDialog(b.dataset.mbmap); }
  else { showView('vehicles'); openVehicle(b.dataset.mbvehicle); }
}

function bindHistory() {
  mbLoad().catch(() => {});  // no game, no name: no button
  $('#btnAccount').addEventListener('click', () => showView('history'));
  for (const [el, key] of [['#mbMode', 'mode'], ['#mbVehicle', 'vehicle'], ['#mbMap', 'map'], ['#mbFrom', 'from'], ['#mbTo', 'to']]) {
    $(el).addEventListener('change', e => { MB[key] = e.target.value; mbRender(); });
  }
  $('#mbResult').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    MB.result = b.dataset.r;
    $$('#mbResult button').forEach(x => x.classList.toggle('active', x === b));
    mbRender();
  });
  $('#mbOffline').addEventListener('change', e => { MB.offline = e.target.checked; mbRender(); });
  $('#mbBody').addEventListener('click', mbFollow);
}
