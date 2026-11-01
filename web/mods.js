/* WTFTD — Skins and sounds: what the player installs into the game, by their own click (wtftd/mods.py holds the rules). Names of files and
   folders come from what the player picked and from whoever made it: they are data, every one goes through esc() or into textContent. */
'use strict';

const MO = { tab: store.get('modsTab', 'skins'), game: true, skins: [], sounds: [], sound: {}, running: false, allowed: {}, busy: false, token: '', arm: '', waiting: null };

const moSize = n => (n >= 1 << 30 ? `${(n / (1 << 30)).toFixed(1)} GB` : n >= 1 << 20 ? `${Math.round(n / (1 << 20))} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const moErr = e => toast({ title: e.data?.code ? t('mo.err.' + e.data.code, { name: e.data.name || '' }) : t('toast.error', { msg: e.message || e }), err: true, ms: 9000 });

async function moAction(path, body) {
  try {
    Object.assign(MO, await api('mods/' + path, body));
    moRefresh();
    return true;
  } catch (e) { moErr(e); return false; }
}

function moRefresh() {
  $('#modsCount').textContent = MO.skins.length + MO.sounds.length || '';
  if (!$('#view-mods').classList.contains('hidden')) moRender();
  if (S.sel && $('#drawer .hero')) renderDrawer();
}

// the block of the vehicle panel: this vehicle's skins
function moPanelHTML(v) {
  const list = MO.skins.filter(s => s.vehicle === v.id);
  if (!list.length) return '';
  return `<div class="lim"><div class="lim-title">${esc(t('mo.skins'))}</div><div class="mo-panel">${list.map(s => `<div class="mo-skin"><span title="${esc(s.name)}">${esc(s.name)}</span>
      <button class="icon-btn" data-act="skin3d" data-skin="${esc(s.name)}" title="${esc(t('mo.preview'))}">${icon('cube', 'ic-sm')}</button>
      <button class="icon-btn" data-act="skinOpen" data-skin="${esc(s.name)}" title="${esc(t('mo.openFolder'))}">${icon('folder', 'ic-sm')}</button></div>`).join('')}</div></div>`;
}

function moPreview(name) {
  const skin = MO.skins.find(s => s.name === name);
  if (skin) openModel('vehicle', skin.vehicle, `${I18N.unit(skin.vehicle)} · ${skin.name}`, undefined, skin);
}

const moOpen = (kind, name) => api('mods/open', { kind, name }).catch(moErr);

function moRemoveButton(kind, name) {
  const armed = MO.arm === `${kind}|${name}`;
  return `<button class="btn btn-sm${armed ? ' btn-danger-solid' : ' btn-ghost'}" data-morm="${esc(name)}" data-kind="${kind}">${esc(t(armed ? 'uninstall.confirm' : 'action.delete'))}</button>`;
}

function moSkinsHTML() {
  const row = s => {
    const v = S.byId.get(s.vehicle);
    return `<div class="list-item">${v ? listThumb(v.id) : `<div class="list-thumb">${icon('file')}</div>`}
      <div class="list-main"><div class="list-title">${v ? flagHTML(v.n) : ''}<span>${esc(s.name)}</span>${s.ours ? '' : `<span class="chip dim">${esc(t('mo.byHand'))}</span>`}</div>
        <div class="list-sub">${v ? mbVehicle(v.id) : esc(t('mo.unknown'))} · ${esc(t('mo.files', { n: s.files }))} · ${esc(moSize(s.bytes))}</div></div>
      <div class="list-actions">${v ? `<button class="btn btn-sm" data-mo3d="${esc(s.name)}">${icon('cube', 'ic-sm')}<span>${esc(t('mo.preview'))}</span></button>` : ''}
        <button class="icon-btn" data-moopen="${esc(s.name)}" title="${esc(t('mo.openFolder'))}">${icon('folder')}</button>
        ${s.ours ? moRemoveButton('skin', s.name) : ''}</div></div>`;
  };
  return `<div class="mo-actions"><button class="btn" data-mopick="zip" data-kind="skin"${MO.busy ? ' disabled' : ''}>${icon('file', 'ic-sm')}<span>${esc(t('mo.fromZip'))}</span></button>
      <button class="btn" data-mopick="folder"${MO.busy ? ' disabled' : ''}>${icon('folder', 'ic-sm')}<span>${esc(t('mo.fromFolder'))}</span></button>
      <button class="btn btn-ghost" data-moroot="skin">${esc(t('mo.openFolder'))}</button>
      <span class="muted">${esc(MO.busy ? t('mo.working') : t('mo.skinCount', { n: MO.skins.length }))}</span></div>
    ${MO.skins.length ? `<div class="list mo-list">${MO.skins.map(row).join('')}</div>` : `<div class="empty">${icon('cube', 'ic-xl')}<p>${esc(t('mo.noSkin'))}</p><p>${esc(t('mo.noSkinHint'))}</p></div>`}`;
}

function moSoundsHTML() {
  const st = MO.sound, row = m => `<div class="list-item"><div class="list-thumb">${icon('file')}</div>
    <div class="list-main"><div class="list-title"><span>${esc(m.name)}</span>${m.ours ? '' : `<span class="chip dim">${esc(t('mo.byHand'))}</span>`}</div>
      <div class="list-sub">${esc(t('mo.files', { n: m.files }))} · ${esc(moSize(m.bytes))}</div></div>
    <div class="list-actions">${m.ours ? moRemoveButton('sound', m.name) : ''}</div></div>`;
  const locked = MO.running || !st.block || (st.on && !st.ours) || (!st.on && !MO.sounds.length);
  const note = MO.running ? 'mo.gameRunning' : !st.block ? 'mo.err.noBlock' : st.on && !st.ours ? 'mo.onByHand' : st.on ? 'mo.onHint' : 'mo.offHint';
  return `<div class="mo-warn">${icon('target', 'ic-sm')}<p class="hint">${esc(t('mo.soundWarning'))}</p></div>
    <label class="switch mo-switch"><input type="checkbox" id="moSound"${st.on ? ' checked' : ''}${locked ? ' disabled' : ''}><span class="sw"></span><span>${esc(t('mo.useSounds'))}</span></label>
    <p class="hint mb-note">${esc(t(note))}</p>
    <div class="mo-actions"><button class="btn" data-mopick="zip" data-kind="sound"${MO.busy || MO.running ? ' disabled' : ''}>${icon('file', 'ic-sm')}<span>${esc(t('mo.fromZip'))}</span></button>
      <button class="btn btn-ghost" data-moroot="sound">${esc(t('mo.openFolder'))}</button>
      <span class="muted">${esc(MO.busy ? t('mo.working') : t('mo.soundCount', { n: MO.sounds.length }))}</span></div>
    ${MO.sounds.length ? `<div class="list mo-list">${MO.sounds.map(row).join('')}</div>` : `<div class="empty">${icon('file', 'ic-xl')}<p>${esc(t('mo.noSound'))}</p></div>`}`;
}

function moRender() {
  $$('#moTabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === MO.tab));
  $('#moTabs').classList.toggle('hidden', !MO.game);
  $('#moBody').innerHTML = !MO.game ? `<div class="empty">${icon('folder', 'ic-xl')}<p>${esc(t('mb.noGame'))}</p></div>` : MO.tab === 'skins' ? moSkinsHTML() : moSoundsHTML();
}

async function moLoad() {
  Object.assign(MO, await api('mods'));
  moRefresh();
}

async function openModsView() {
  try { await moLoad(); } catch (e) { toastErr(e); }
  moRender();
}

// picked files to the app, one at a time and each as it is on disk: the page holds none of it in memory
async function moSend(files, kind) {
  MO.token = (newId() + newId()).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 24).padEnd(8, '0');
  MO.busy = true;
  moRender();
  try {
    for (const { file, path } of files) {
      const q = new URLSearchParams({ token: MO.token, kind, path });
      const r = await fetch(`/api/mods/upload?${q}`, { method: 'POST', body: file });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw Object.assign(new Error(data.error || r.statusText), { data });
    }
    const found = await api('mods/inspect', { token: MO.token, kind });
    const unclear = (found.skins || []).filter(s => !s.sure);
    if (unclear.length) moAsk(unclear, kind);
    else await moFinish(kind, {});
  } catch (e) {
    moErr(e);
    api('mods/forget', { token: MO.token }).catch(() => {});
  }
  MO.busy = false;
  moRender();
}

// which vehicle a skin is for, when its files don't say
function moAsk(list, kind) {
  $('#moVehicles').innerHTML = S.vehicles.filter(v => !v.h).map(v => `<option value="${esc(hgGoalName(v))}"></option>`).join('');
  $('#moAsk').innerHTML = list.map(s => `<label class="mo-ask-row"><b>${esc(s.folder)}</b><small class="muted">${esc(t('mo.files', { n: s.files }))} · ${esc(moSize(s.bytes))}</small>
    <input type="search" list="moVehicles" data-folder="${esc(s.folder)}" spellcheck="false" autocomplete="off" placeholder="${esc(t('mo.askVehicle'))}" value="${esc(S.byId.has(s.vehicle) ? hgGoalName(S.byId.get(s.vehicle)) : '')}"></label>`).join('');
  MO.waiting = kind;
  $('#dlgSkin').showModal();
}

async function moFinish(kind, vehicles) {
  const ok = await moAction('install', { token: MO.token, kind, vehicles });
  if (ok) toast({ title: t('mo.installed') });
  else api('mods/forget', { token: MO.token }).catch(() => {});
}

function bindMods() {
  moLoad().catch(() => {});
  $('#moTabs').addEventListener('click', e => {
    if (!e.target.dataset.tab) return;
    MO.tab = e.target.dataset.tab;
    store.set('modsTab', MO.tab);
    moRender();
  });
  $('#moBody').addEventListener('click', async e => {
    const b = e.target.closest('button');
    if (!b) return;
    const d = b.dataset;
    if (d.mopick === 'zip') { $('#moZip').dataset.kind = d.kind; return $('#moZip').click(); }
    if (d.mopick === 'folder') return $('#moFolder').click();
    if (d.moroot) return moOpen(d.moroot);
    if (d.moopen) return moOpen('skin', d.moopen);
    if (d.mo3d) return moPreview(d.mo3d);
    if (d.morm) {
      const key = `${d.kind}|${d.morm}`;
      if (MO.arm !== key) { MO.arm = key; return moRender(); }
      MO.arm = '';
      return moAction('remove', { kind: d.kind, name: d.morm });
    }
    mbFollow(e);
  });
  $('#moBody').addEventListener('change', async e => {
    if (e.target.id !== 'moSound') return;
    const on = e.target.checked;
    if (await moAction('sound', { on })) toast({ title: t(on ? 'mo.soundsOn' : 'mo.soundsOff') });
    else moRender();
  });
  $('#moZip').addEventListener('change', e => {
    const file = e.target.files[0];
    e.target.value = '';
    if (file) moSend([{ file, path: file.name }], e.target.dataset.kind);
  });
  $('#moFolder').addEventListener('change', e => {
    const files = [...e.target.files].map(file => ({ file, path: file.webkitRelativePath || file.name }));
    e.target.value = '';
    if (files.length) moSend(files, 'skin');
  });
  $('#moAskGo').addEventListener('click', async () => {
    const vehicles = {};
    for (const el of $$('#moAsk input')) {
      const v = S.vehicles.find(x => hgGoalName(x) === el.value);
      if (!v) { el.focus(); return toast({ title: t('mo.askVehicle'), err: true, ms: 3000 }); }
      vehicles[el.dataset.folder] = v.id;
    }
    const kind = MO.waiting;
    MO.waiting = null;
    $('#dlgSkin').close();
    await moFinish(kind, vehicles);
  });
  $('#dlgSkin').addEventListener('close', () => { if (MO.waiting) { MO.waiting = null; api('mods/forget', { token: MO.token }).catch(() => {}); } });
}
