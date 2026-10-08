/* WTFTD — compare up to 5 vehicles side by side: BR, stats (best value highlighted), guns, shell types. */
'use strict';

const CMP_MAX = 5;
S.compare = (store.get('compare', []) || []).filter(id => typeof id === 'string').slice(0, CMP_MAX);

const inCompare = id => S.compare.includes(id);

function toggleCompare(id) {
  if (inCompare(id)) S.compare = S.compare.filter(x => x !== id);
  else {
    if (S.compare.length >= CMP_MAX) { toast({ title: t('compare.max', { n: CMP_MAX }), err: true, ms: 3500 }); return; }
    S.compare = [...S.compare, id];
  }
  store.set('compare', S.compare);
  renderCompareTray();
  if (S.sel) renderDrawer();
}

function compareButtonHTML(v) {
  const on = inCompare(v.id);
  return `<button class="icon-btn${on ? ' on' : ''}" data-act="compare" title="${esc(t(on ? 'compare.remove' : 'compare.add'))}">${icon('sliders')}</button>`;
}

function renderCompareTray() {
  const tray = $('#compareTray');
  const list = S.compare.map(id => S.byId.get(id)).filter(Boolean);
  tray.classList.toggle('hidden', !list.length);
  if (!list.length) return;
  tray.innerHTML = `<div class="ct-items">${list.map(v => `<span class="ct-item" title="${esc(I18N.unitFull(v.id))}">
      <span class="ct-img">${unitImgTag(v.id, true)}</span>${flagHTML(v.n)}<span class="ct-name">${esc(I18N.unit(v.id))}</span>
      <button data-ctrm="${esc(v.id)}" title="${esc(t('compare.remove'))}">${icon('x', 'ic-sm')}</button></span>`).join('')}</div>
    <button class="btn btn-ghost btn-sm" data-ctact="clear">${esc(t('compare.clear'))}</button>
    <button class="btn btn-primary btn-sm" data-ctact="open"${list.length < 2 ? ' disabled' : ''}>${icon('sliders', 'ic-sm')}<span>${esc(t('compare.button', { n: list.length }))}</span></button>`;
}

async function openCompare() {
  if (!WP.arsenal) { try { WP.arsenal = await getData('arsenal.json'); } catch { WP.arsenal = {}; } }
  renderCompareTable();
  $('#dlgCompare').showModal();
}

function renderCompareTable() {
  const list = S.compare.map(id => S.byId.get(id)).filter(Boolean);
  if (!list.length) { $('#dlgCompare').close(); return; }
  // stats shown: those of the vehicles' types, in the usual order, when at least one vehicle has a value
  const keys = Object.keys(STATS).filter(k => list.some(v => STATS[k].cats.includes(v.c) && v.s?.[k] != null));
  const best = k => {
    const dir = STATS[k].better;
    const vals = list.map(v => statVal(v, k)).filter(x => x != null);
    if (!dir || vals.length < 2) return null;
    return dir > 0 ? Math.max(...vals) : Math.min(...vals);
  };
  const cell = (v, k, b) => {
    const x = statVal(v, k);
    return `<td class="${b != null && x === b ? 'best' : ''}">${v.s?.[k] != null ? esc(fmtStat(k, v.s[k])) : '<span class="muted">—</span>'}</td>`;
  };
  const guns = v => (v.wg || []).filter(k => !NOT_WEAPON.test(k)).slice(0, 4).map(k => {
    const a = WP.arsenal[k];
    return `<span class="cmp-chip">${a?.cal ? `<b>${Math.round(a.cal)}</b> ` : ''}${esc(I18N.weapon(k))}</span>`;
  }).join('') || '<span class="muted">—</span>';
  const shells = v => [...ammoTypes(v)].map(tp => `<span class="wp-badge">${esc(tp)}</span>`).join(' ') || '<span class="muted">—</span>';
  const pylonW = v => {
    const names = [...new Set((v.wp || []).filter(k => !NOT_WEAPON.test(k) && !['fuel', 'other'].includes(WP.arsenal[k]?.c)).map(k => I18N.weapon(k)))];
    return names.length ? `<span class="muted">${esc(t('compare.nWeapons', { n: names.length }))}</span>` : '<span class="muted">—</span>';
  };
  const head = list.map(v => `<th><div class="cmp-head">
      <button class="icon-btn cmp-rm" data-ctrm="${esc(v.id)}" title="${esc(t('compare.remove'))}">${icon('x', 'ic-sm')}</button>
      <div class="cmp-img">${unitImgTag(v.id, true)}</div>
      <div class="cmp-name">${flagHTML(v.n)}<b>${esc(I18N.unit(v.id))}</b></div>
      <div class="muted">${esc(className(v.k))}${v.r ? ' · ' + esc(t('rank', { r: ROMAN[v.r] || v.r })) : ''}</div>
      <button class="btn btn-ghost btn-sm" data-ctopen="${esc(v.id)}">${esc(t('compare.open'))}</button></div></th>`).join('');
  const brRows = ['AB', 'RB', 'SB'].map((m, i) => {
    const vals = list.map(v => v.br?.[i]);
    return `<tr><th>BR ${m}</th>${vals.map(b => `<td>${b != null ? fmtBR(b) : '—'}</td>`).join('')}</tr>`;
  }).join('');
  const statRows = keys.map(k => {
    const b = best(k);
    const label = statLabel(k, list.every(v => v.c === list[0].c) ? list[0].c : 'all');
    return `<tr><th>${esc(label)}${STATS[k].triple ? `<small>${esc(t('stat.armHint'))}</small>` : ''}</th>${list.map(v => cell(v, k, b)).join('')}</tr>`;
  }).join('');
  $('#cmpTable').innerHTML = `<table class="cmp"><thead><tr><th></th>${head}</tr></thead><tbody>
    ${brRows}${statRows}
    <tr><th>${esc(t('compare.guns'))}</th>${list.map(v => `<td class="cmp-wrap">${guns(v)}</td>`).join('')}</tr>
    <tr><th>${esc(t('compare.shells'))}</th>${list.map(v => `<td class="cmp-wrap">${shells(v)}</td>`).join('')}</tr>
    ${list.some(v => v.wp?.length) ? `<tr><th>${esc(t('compare.pylons'))}</th>${list.map(v => `<td>${pylonW(v)}</td>`).join('')}</tr>` : ''}
  </tbody></table>`;
}

function bindCompare() {
  const onClick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.ctrm) { toggleCompare(b.dataset.ctrm); if ($('#dlgCompare').open) renderCompareTable(); }
    else if (b.dataset.ctact === 'clear') { S.compare = []; store.set('compare', []); renderCompareTray(); if (S.sel) renderDrawer(); }
    else if (b.dataset.ctact === 'open') openCompare();
    else if (b.dataset.ctopen) { $('#dlgCompare').close(); showView('vehicles'); openVehicle(b.dataset.ctopen); }
  };
  $('#compareTray').addEventListener('click', onClick);
  $('#dlgCompare').addEventListener('click', onClick);
  renderCompareTray();
}
