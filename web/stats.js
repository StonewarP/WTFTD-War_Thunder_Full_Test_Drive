/* WTFTD — vehicle stats: shown on the vehicle card, sortable, filterable (min / max), plus search by
   carried weapon / ammunition. Data: vehicles.json  v.s = {stat: value}, v.wp = [weapon & ammo keys]. */
'use strict';

const AIR = ['air', 'heli'], NAVAL = ['boat', 'ship'], ALL_CATS = ['ground', 'air', 'heli', 'boat', 'ship'];
// better: 1 = higher is better (sorted descending), -1 = lower is better, 0 = neutral
const STATS = {
  spd: { cats: ALL_CATS, unit: 'km/h', better: 1 },
  rev: { cats: ['ground'], unit: 'km/h', better: 1 },
  pw: { cats: ['ground', 'air'], unit: 'hp/t', better: 1 },
  hp: { cats: ['ground'], unit: 'hp', better: 1 },
  t: { cats: ['ground'], unit: 't', better: 0 },
  armT: { cats: ['ground'], unit: 'mm', better: 1, triple: true },
  armH: { cats: ['ground'], unit: 'mm', better: 1, triple: true },
  trav: { cats: ['ground'], unit: '°/s', better: 1 },
  cal: { cats: ['ground', ...NAVAL], unit: 'mm', better: 1 },
  heat: { cats: ['ground'], unit: 'mm', better: 1 },
  rel: { cats: ['ground'], unit: 's', better: -1, digits: 1 },
  turn: { cats: AIR, unit: 's', better: -1, digits: 1 },
  roll: { cats: ['air'], unit: '°/s', better: 1 },
  climb: { cats: AIR, unit: 'm/s', better: 1, digits: 1 },
  alt: { cats: AIR, unit: 'm', better: 0 },
  ceil: { cats: AIR, unit: 'm', better: 1 },
  tw: { cats: AIR, unit: '', better: 1, digits: 2 },
  wl: { cats: ['air'], unit: 'kg/m²', better: -1 },
  disp: { cats: NAVAL, unit: 't', better: 0 },
  crew: { cats: ALL_CATS, unit: '', better: 0 },
};

// aircraft: propeller planes have a power-to-weight ratio, jets a thrust-to-weight ratio (not comparable)
const statLabel = (k, cat) => t(cat === 'air' && k === 'pw' ? 'stat.pwProp' : cat === 'air' && k === 'tw' ? 'stat.twJet' : 'stat.' + k);
const statKeys = cat => Object.keys(STATS).filter(k => cat === 'all' ? ['spd', 'crew'].includes(k) : STATS[k].cats.includes(cat));
// one comparable number per stat (armor: the front plate)
const statVal = (v, k) => { const x = v.s?.[k]; return Array.isArray(x) ? x[0] : (typeof x === 'number' ? x : null); };

function fmtStat(k, x) {
  if (x == null) return '—';
  const d = STATS[k];
  const n = val => I18N.num(+(+val).toFixed(d.digits ?? 0));
  const txt = Array.isArray(x) ? x.map(n).join(' / ') : n(x);
  return d.unit ? `${txt} ${d.unit}` : txt;
}

// ------------------------------------------------------------------ filters
function statsMatch(v) {
  const f = S.f.stats || {};
  for (const [k, [lo, hi]] of Object.entries(f)) {
    if (lo == null && hi == null) continue;
    if (!STATS[k] || !STATS[k].cats.includes(v.c)) continue;  // stat of another vehicle type: ignore
    const x = statVal(v, k);
    if (x == null || (lo != null && x < lo) || (hi != null && x > hi)) return false;
  }
  return true;
}

function weaponIndex(v) {
  if (v._w == null) v._w = norm((v.wp || []).map(k => `${I18N.weapon(k)} ${I18N.bullet(k)} ${k}`).join(' | '));
  return v._w;
}

function weaponMatch(v) {
  const q = (S.f.wq || '').trim();
  if (!q) return true;
  if (!v.wp) return false;
  const idx = weaponIndex(v);
  return q.split(/[,+]/).map(s => norm(s.trim())).filter(Boolean).every(term => idx.includes(term));
}

// ------------------------------------------------------------------ sorting
function statCmp(sort) {
  const k = sort?.startsWith('s:') ? sort.slice(2) : null;
  if (!k || !STATS[k]) return null;
  const dir = STATS[k].better === -1 ? 1 : -1;  // best first
  return (a, b) => {
    const x = statVal(a, k), y = statVal(b, k);
    if (x == null || y == null) return (x == null) - (y == null);
    return (x - y) * dir || (brOf(a) ?? 99) - (brOf(b) ?? 99);
  };
}

function updateSortOptions() {
  const sel = $('#sort');
  if (!sel) return;
  const keys = statKeys(S.f.cat);
  if (S.f.sort?.startsWith('s:') && !keys.includes(S.f.sort.slice(2))) S.f.sort = 'br';
  const base = ['br', 'rank', 'name', 'nation'].map(k => `<option value="${k}">${esc(t('sort.' + k))}</option>`).join('');
  sel.innerHTML = base + `<optgroup label="${esc(t('stats.title'))}">${keys.map(k => `<option value="s:${k}">${esc(statLabel(k, S.f.cat))}${STATS[k].better ? (STATS[k].better > 0 ? ' ↓' : ' ↑') : ''}</option>`).join('')}</optgroup>`;
  sel.value = S.f.sort;
}

// ------------------------------------------------------------------ sidebar
function renderStatFilters() {
  const box = $('#statFilters');
  if (!box) return;
  const f = S.f.stats || {};
  const keys = statKeys(S.f.cat);
  box.innerHTML = `<label class="wsearch"><span>${esc(t('filters.weapon'))}</span>
      <input type="search" id="weaponSearch" value="${esc(S.f.wq || '')}" placeholder="${esc(t('filters.weaponPh'))}" autocomplete="off"></label>
    ${S.f.cat === 'all' ? `<p class="hint">${esc(t('filters.statsPickType'))}</p>` : ''}
    <div class="stat-rows">${keys.map(k => {
      const [lo, hi] = f[k] || [];
      const unit = STATS[k].unit ? ` (${STATS[k].unit})` : '';
      return `<div class="stat-row${lo != null || hi != null ? ' on' : ''}" title="${esc(statLabel(k, S.f.cat) + unit)}"><span>${esc(statLabel(k, S.f.cat))}</span>
        <input type="number" step="any" data-stat="${k}" data-b="0" value="${lo ?? ''}" placeholder="${esc(t('filters.min'))}">
        <input type="number" step="any" data-stat="${k}" data-b="1" value="${hi ?? ''}" placeholder="${esc(t('filters.max'))}"></div>`;
    }).join('')}</div>`;
}

function bindStatFilters() {
  const box = $('#statFilters');
  box.addEventListener('change', e => {
    const el = e.target;
    if (el.dataset.stat === undefined) return;
    const stats = S.f.stats ||= {};
    const cur = stats[el.dataset.stat] || [null, null];
    cur[+el.dataset.b] = el.value === '' ? null : +el.value;
    if (cur[0] == null && cur[1] == null) delete stats[el.dataset.stat]; else stats[el.dataset.stat] = cur;
    el.closest('.stat-row').classList.toggle('on', cur[0] != null || cur[1] != null);
    applyFilters();
  });
  box.addEventListener('input', debounce(e => {
    if (e.target.id !== 'weaponSearch') return;
    S.f.wq = e.target.value;
    applyFilters();
  }, 120));
}

// ------------------------------------------------------------------ vehicle card / drawer
function cardStatHTML(v) {
  const k = S.f.sort?.startsWith('s:') ? S.f.sort.slice(2) : null;
  if (!k || !STATS[k]) return '';
  return `<span class="card-stat" title="${esc(statLabel(k, v.c))}">${esc(fmtStat(k, v.s?.[k]))}</span>`;
}

function statsBlockHTML(v) {
  const keys = statKeys(v.c).filter(k => v.s?.[k] != null);
  if (!keys.length) return '';
  return `<div class="vstats">${keys.map(k => `<div class="vstat" title="${esc(STATS[k].triple ? t('stat.armHint') : '')}">
      <span>${esc(statLabel(k, v.c))}</span><b>${esc(fmtStat(k, v.s[k]))}</b></div>`).join('')}</div>`;
}
