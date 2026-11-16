/* WTFTD — Mods (skins, sounds, vehicles of their own): what the player installs into the game, by their own click (wtftd/mods.py holds the rules). Names of files and
   folders come from what the player picked and from whoever made it: they are data, every one goes through esc() or into textContent. */
'use strict';

const MO = { tab: store.get('modsTab', 'skins'), game: true, skins: [], sounds: [], sound: {}, running: false, allowed: {}, busy: false, token: '', arm: '', waiting: null };

const moSize = n => (n >= 1 << 30 ? `${(n / (1 << 30)).toFixed(1)} GB` : n >= 1 << 20 ? `${Math.round(n / (1 << 20))} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
const moErr = e => toast({ title: e.data?.code ? t('mo.err.' + e.data.code, { name: e.data.name || '' }) : t('toast.error', { msg: e.message || e }), err: true, ms: 9000 });

async function moAction(path, body) {
  try {
    const r = await api('mods/' + path, body);
    Object.assign(MO, r);
    moRefresh();
    return r;
  } catch (e) { moErr(e); return false; }
}

function moRefresh() {
  if (MO.sights) S.sights = { dir: MO.sights.dir, sights: MO.sights.sights };  // the vehicle panel's sight list follows
  $('#modsCount').textContent = MO.skins.length + MO.sounds.length + (MO.vehicles || []).length + (MO.hangars || []).length || '';
  if (!$('#view-mods').classList.contains('hidden')) moRender();
  if (S.sel && $('#drawer .hero')) renderDrawer();
  moPictures();
}

// the pictures the encyclopedia has none of: a package's vehicles and the skins, drawn once with the 3D view (mdCapture)
// and kept by WTFTD; one at a time, in the background, each tried once a session
const MO_SHOTS = { busy: false, tried: new Set() };
async function moPictures() {
  if (MO_SHOTS.busy || !S.byId || !MO.game) return;
  MO_SHOTS.busy = true;
  try {
    for (;;) {
      const v = S.vehicles.find(x => x.mod && !x.pic && !MO_SHOTS.tried.has('v' + x.id));
      const s = v ? null : MO.skins.find(x => !x.pic && S.byId.has(x.vehicle) && !MO_SHOTS.tried.has('s' + x.name));
      if (!v && !s) return;
      MO_SHOTS.tried.add(v ? 'v' + v.id : 's' + s.name);
      const png = await mdCapture(v ? v.id : s.vehicle, s || undefined).catch(e => { console.warn(e); return null; });
      if (!png) continue;
      const data = await new Promise((done, fail) => Object.assign(new FileReader(), { onload: e => done(e.target.result.split(',')[1]), onerror: fail }).readAsDataURL(png));
      const r = await api('capture', { kind: v ? 'unit' : 'skin', id: v ? v.id : s.name, png: data }).catch(() => null);
      if (!r) continue;
      if (v) { v.pic = true; IMG_BAD.delete(unitImg(v.id)); applyFilters(); } else { s.pic = r.pic; moRefresh(); }
    }
  } finally { MO_SHOTS.busy = false; }
}

// the block of the vehicle panel: this vehicle's skins
function moPanelHTML(v) {
  const list = MO.skins.filter(s => (s.vehicles || [s.vehicle]).includes(v.id));
  if (!list.length) return '';
  return `<div class="lim"><div class="lim-title">${esc(t('mo.skins'))}</div><div class="mo-panel">${list.map(s => `<div class="mo-skin"><span title="${esc(s.name)}">${esc(s.name)}</span>
      <button class="icon-btn" data-act="skin3d" data-skin="${esc(s.name)}" data-vid="${esc(v.id)}" title="${esc(t('mo.preview'))}">${icon('cube', 'ic-sm')}</button>
      <button class="icon-btn" data-act="skinOpen" data-skin="${esc(s.name)}" title="${esc(t('mo.openFolder'))}">${icon('folder', 'ic-sm')}</button></div>`).join('')}</div></div>`;
}

// vid: the vehicle to show it on, when it fits several (the panel's own)
function moPreview(name, vid) {
  const skin = MO.skins.find(s => s.name === name);
  const on = skin && (skin.vehicles || []).includes(vid) ? vid : skin?.vehicle;
  if (skin) openModel('vehicle', on, `${I18N.unit(on)} · ${skin.name}`, undefined, skin);
}

const moOpen = (kind, name) => api('mods/open', { kind, name }).catch(moErr);

function moRemoveButton(kind, name) {
  const armed = MO.arm === `${kind}|${name}`;
  return `<button class="btn btn-sm${armed ? ' btn-danger-solid' : ' btn-ghost'}" data-morm="${esc(name)}" data-kind="${kind}">${esc(t(armed ? 'uninstall.confirm' : 'action.delete'))}</button>`;
}

function moSkinsHTML() {
  const row = s => {
    const v = S.byId.get(s.vehicle);
    return `<div class="list-item">${s.pic ? `<div class="list-thumb"><img src="${esc(s.pic)}" alt=""></div>` : v ? listThumb(v.id) : `<div class="list-thumb">${icon('file')}</div>`}
      <div class="list-main"><div class="list-title">${v ? flagHTML(v.n) : ''}<span>${esc(s.name)}</span>${s.ours ? '' : `<span class="chip dim">${esc(t('mo.byHand'))}</span>`}</div>
        <div class="list-sub">${v ? mbVehicle(v.id) : esc(t('mo.unknown'))}${(s.vehicles || []).length > 1 ? ` <span class="muted" title="${esc(s.vehicles.map(id => I18N.unit(id)).join(', '))}">+${s.vehicles.length - 1}</span>` : ''} · ${esc(t('mo.files', { n: s.files }))} · ${esc(moSize(s.bytes))}</div></div>
      <div class="list-actions">${v ? `<button class="btn btn-sm" data-mo3d="${esc(s.name)}">${icon('cube', 'ic-sm')}<span>${esc(t('mo.preview'))}</span></button>` : ''}
        <button class="icon-btn" data-moopen="${esc(s.name)}" title="${esc(t('mo.openFolder'))}">${icon('folder')}</button>
        ${s.ours ? moRemoveButton('skin', s.name) : ''}</div></div>`;
  };
  return `<div class="mo-actions"><button class="btn" data-mopick="zip" data-kind="skin"${MO.busy ? ' disabled' : ''}>${icon('file', 'ic-sm')}<span>${esc(t('mo.fromZip'))}</span></button>
      <button class="btn" data-mopick="folder"${MO.busy ? ' disabled' : ''}>${icon('folder', 'ic-sm')}<span>${esc(t('mo.fromFolder'))}</span></button>
      <button class="btn btn-ghost" data-moroot="skin">${esc(t('mo.openFolder'))}</button>
      <span class="muted">${esc(MO.busy ? moWorking() : t('mo.skinCount', { n: MO.skins.length }))}</span></div>
    ${MO.skins.length ? `<div class="list mo-list">${MO.skins.map(row).join('')}</div>` : `<div class="empty">${icon('cube', 'ic-xl')}<p>${esc(t('mo.noSkin'))}</p><p>${esc(t('mo.noSkinHint'))}</p></div>`}`;
}

function moSoundsHTML() {
  const st = MO.sound, row = m => `<div class="list-item"><div class="list-thumb">${icon('file')}</div>
    <div class="list-main"><div class="list-title"><span>${esc(m.name)}</span>${m.ours ? '' : `<span class="chip dim">${esc(t('mo.byHand'))}</span>`}</div>
      <div class="list-sub">${esc(t('mo.files', { n: m.files }))} · ${esc(moSize(m.bytes))}</div></div>
    <div class="list-actions">${m.ours ? moRemoveButton('sound', m.name) : ''}</div></div>`;
  const locked = MO.running || !st.block || (st.on && !st.ours) || (!st.on && !MO.sounds.length);
  const note = MO.running ? 'mo.soundRunning' : !st.block ? 'mo.err.noBlock' : st.on && !st.ours ? 'mo.onByHand' : st.on ? 'mo.onHint' : 'mo.offHint';
  return `<div class="mo-warn">${icon('target', 'ic-sm')}<p class="hint">${esc(t('mo.soundWarning'))}</p></div>
    <label class="switch mo-switch"><input type="checkbox" id="moSound"${st.on ? ' checked' : ''}${locked ? ' disabled' : ''}><span class="sw"></span><span>${esc(t('mo.useSounds'))}</span></label>
    <p class="hint mb-note">${esc(t(note))}</p>
    <div class="mo-actions"><button class="btn" data-mopick="zip" data-kind="sound"${MO.busy ? ' disabled' : ''}>${icon('file', 'ic-sm')}<span>${esc(t('mo.fromZip'))}</span></button>
      <button class="btn btn-ghost" data-moroot="sound">${esc(t('mo.openFolder'))}</button>
      <span class="muted">${esc(MO.busy ? moWorking() : t('mo.soundCount', { n: MO.sounds.length }))}</span></div>
    ${MO.sounds.length ? `<div class="list mo-list">${MO.sounds.map(row).join('')}</div>` : `<div class="empty">${icon('file', 'ic-xl')}<p>${esc(t('mo.noSound'))}</p></div>`}`;
}

// a package's vehicles among WTFTD's, named: Vehicles, the vehicle bar, My vehicles (after an install or a removal)
function moVehiclesIn(list) {
  I18N.addUnits(Object.fromEntries(list.map(v => [v.id, v.name])));
  for (const v of list) v._s = norm(v.name) + '|' + norm(v.id);
  S.vehicles = S.vehicles.filter(v => !v.mod).concat(list);
  S.byId = new Map(S.vehicles.map(v => [v.id, v]));
  applyFilters();
  moPictures();
}

// a vehicle package goes out with the game closed: it may hold its files open (it goes in any time, used from the next start)
async function moGameClosed(kind) {
  try { await moLoad(); } catch { /* the last state stands */ }
  if (MO.running) toast({ title: t({ sound: 'mo.soundRemoveRunning', hangar: 'mo.hangarRemoveRunning' }[kind] || 'mo.vehicleRemoveRunning'), err: true, ms: 7000 });
  return !MO.running;
}

// a package's vehicles in a few words: those of one name once (the CL-1201's four [CIWS] turrets: "[CIWS] x4"), two of
// them, then how many more; all of them where the pointer rests
function moShortNames(vehicles) {
  const groups = new Map();
  for (const v of vehicles) {
    const name = v.name.endsWith(` (${v.id})`) ? v.name.slice(0, -v.id.length - 3) : v.name;  // the id that tells twins apart
    groups.set(name, (groups.get(name) || 0) + 1);
  }
  const names = [...groups].map(([name, n]) => (n > 1 ? `${name} ×${n}` : name));
  return names.slice(0, 2).join(', ') + (names.length > 2 ? ` +${names.length - 2}` : '');
}

function moVehiclesHTML() {
  const hidden = p => p.vehicles.filter(v => v.invisible);  // an old modding kit's model: the game draws nothing (mo.invisible)
  const row = p => `<div class="list-item"><div class="list-thumb">${icon('air')}</div>
    <div class="list-main"><div class="list-title"><span title="${esc(p.vehicles.map(v => v.name).join(', '))}">${esc(moShortNames(p.vehicles) || p.name)}</span><span class="chip dim">${esc(p.name)}</span>
      ${hidden(p).length ? `<span class="chip warn" title="${esc(t('mo.invisible', { names: moShortNames(hidden(p)) }))}">${esc(t('mo.invisibleChip'))}</span>` : ''}
      ${(p.stops || []).some(s => s.fatal) ? `<span class="chip warn" title="${esc(t('mo.stops', { name: p.stops.find(s => s.fatal).ref }))}">${esc(t('mo.stopsChip'))}</span>`
        : p.stops?.length ? `<span class="chip warn" title="${esc(t('mo.missingFiles', { names: p.stops.map(s => s.ref.split('/').pop()).join(', ') }))}">${esc(t('mo.missingChip', { n: p.stops.length }))}</span>` : ''}</div>
      <div class="list-sub">${p.missions.length ? `${esc(t('mo.testMissions', { names: p.missions.join(', ') }))} · ` : ''}${esc(t('mo.files', { n: p.files }))} · ${esc(moSize(p.bytes))}</div></div>
    <div class="list-actions">${p.stops?.length ? `<button class="btn btn-sm btn-primary" data-morepair="${esc(p.name)}">${esc(t('mo.repair'))}</button>`
      : p.fixed ? `<button class="btn btn-sm" data-morepair="${esc(p.name)}" title="${esc(t('mo.fixEditHint'))}">${esc(t('mo.fixEdit', { n: p.fixed }))}</button>` : ''}${moRemoveButton('vehicle', p.name)}</div></div>`;
  const list = MO.vehicles || [];
  return `<div class="mo-warn">${icon('target', 'ic-sm')}<p class="hint">${esc(t('mo.vehicleWarning'))}</p></div>
    ${MO.running ? `<p class="hint mb-note">${esc(t('mo.vehicleRunning'))}</p>` : ''}
    <div class="mo-actions"><button class="btn" data-mopick="zip" data-kind="vehicle"${MO.busy ? ' disabled' : ''}>${icon('file', 'ic-sm')}<span>${esc(t('mo.fromZip'))}</span></button>
      <span class="muted">${esc(MO.busy ? moWorking() : t('mo.vehicleCount', { n: list.length }))}</span></div>
    ${list.length ? `<div class="list mo-list">${list.map(row).join('')}</div>` : `<div class="empty">${icon('air', 'ic-xl')}<p>${esc(t('mo.noVehicle'))}</p><p>${esc(t('mo.noVehicleHint'))}</p></div>`}`;
}

// the tank sights: WTFTD's library (from WT Live, a .zip or a .blk), deleted here, and those of the game's UserSights
// folder, the player's (listed, never deleted). A mission puts the one picked in the vehicle panel in the game.
function moSightsHTML() {
  const st = MO.sights || { dir: '', sights: [] };
  const where = s => (!s.folder ? t('mo.sightLibrary') : s.folder === 'all_tanks' ? t('mo.sightAllTanks') : S.byId?.has(s.folder) ? I18N.unit(s.folder) : s.folder);
  const row = s => `<div class="list-item"><div class="list-thumb">${icon('target')}</div>
    <div class="list-main"><div class="list-title"><span>${esc(s.name)}</span>${s.folder ? `<span class="chip dim">${esc(t('mo.byHand'))}</span>` : ''}</div>
      <div class="list-sub">${esc(where(s))}</div></div>
    <div class="list-actions">${s.folder ? '' : moRemoveButton('sight', s.id)}</div></div>`;
  return `<div class="mo-warn">${icon('target', 'ic-sm')}<p class="hint">${esc(t('mo.sightWarning'))}</p></div>
    <div class="mo-actions"><button class="btn" data-mopick="zip" data-kind="sight"${MO.busy ? ' disabled' : ''}>${icon('file', 'ic-sm')}<span>${esc(t('mo.fromZipBlk'))}</span></button>
      <button class="btn btn-ghost" data-moroot="sight">${esc(t('mo.openFolder'))}</button>
      <span class="muted">${esc(MO.busy ? moWorking() : t('mo.sightCount', { n: st.sights.length }))}</span></div>
    ${st.sights.length ? `<div class="list mo-list">${st.sights.map(row).join('')}</div>` : `<div class="empty">${icon('target', 'ic-xl')}<p>${esc(t('mo.noSight'))}</p><p>${esc(t('mo.noSightHint'))}</p></div>`}`;
}

// sights picked: a .blk straight into the library, a .zip (a pack: a folder per vehicle) through Mods' staging
async function moSightFiles(files) {
  if (MO.busy) return toast({ title: moWorking(), ms: 3000 });
  MO.busy = true;
  moRender();
  let n = 0;
  for (const file of files) {
    try {
      if (/\.blk$/i.test(file.name)) {
        await api('sight-import', { name: file.name, text: await file.text() });
        n += 1;
        continue;
      }
      const token = (newId() + newId()).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 24).padEnd(8, '0');
      const r = await fetch(`/api/mods/upload?${new URLSearchParams({ token, kind: 'auto', path: file.name })}`, { method: 'POST', body: file });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw Object.assign(new Error(data.error || r.statusText), { data });
      n += (await api('wtlive/sights', { token })).added.length;
    } catch (e) {
      if (e.data?.code === 'noSight') toast({ title: t('wl.err.noSight'), sub: file.name, err: true, ms: 8000 });
      else if (e.data?.code) moErr(e);
      else toastErr(e);
    }
  }
  MO.busy = false;
  if (n) toast({ title: t('wl.sightsDone', { n }), sub: t('wl.sightsHint'), ms: 8000 });
  try { await moLoad(); } catch { moRender(); }
}

// a custom hangar (from WT Live, or a .zip): its files in the game, and the line the player puts in config.blk to use it
// (WTFTD leaves that file alone)
const moHangarLine = h => `hangarBlk:t="${h.line}"`;
function moHangarsHTML() {
  const row = h => `<div class="list-item"><div class="list-thumb">${icon('map')}</div>
    <div class="list-main"><div class="list-title"><span>${esc(h.name)}</span></div>
      <div class="list-sub"><code class="mo-line">${esc(moHangarLine(h))}</code> · ${esc(t('mo.files', { n: h.files }))} · ${esc(moSize(h.bytes))}</div></div>
    <div class="list-actions"><button class="btn btn-sm" data-mocopy="${esc(moHangarLine(h))}">${icon('file', 'ic-sm')}<span>${esc(t('mo.copyLine'))}</span></button>
      ${moRemoveButton('hangar', h.name)}</div></div>`;
  const list = MO.hangars || [];
  return `<div class="mo-warn">${icon('target', 'ic-sm')}<p class="hint">${esc(t('mo.hangarWarning'))}</p></div>
    <div class="mo-actions"><button class="btn" data-mopick="zip" data-kind="hangar"${MO.busy ? ' disabled' : ''}>${icon('file', 'ic-sm')}<span>${esc(t('mo.fromZip'))}</span></button>
      <span class="muted">${esc(MO.busy ? moWorking() : t('mo.hangarCount', { n: list.length }))}</span></div>
    ${list.length ? `<div class="list mo-list">${list.map(row).join('')}</div>` : `<div class="empty">${icon('map', 'ic-xl')}<p>${esc(t('mo.noHangar'))}</p><p>${esc(t('mo.noHangarHint'))}</p></div>`}`;
}

function moRender() {
  $$('#moTabs button').forEach(b => b.classList.toggle('active', b.dataset.tab === MO.tab));
  $('#moTabs').classList.toggle('hidden', !MO.game);
  const tabs = { skins: moSkinsHTML, sounds: moSoundsHTML, vehicles: moVehiclesHTML, sights: moSightsHTML, hangars: moHangarsHTML, live: wlHTML };
  $('#moBody').innerHTML = !MO.game ? `<div class="empty">${icon('folder', 'ic-xl')}<p>${esc(t('mb.noGame'))}</p></div>` : (tabs[MO.tab] || moSkinsHTML)();

  if (MO.tab === 'live' && MO.game) wlWatch();  // the next posts as the list's end nears
}

async function moLoad() {
  Object.assign(MO, await api('mods'));
  moRefresh();
}

async function openModsView() {
  try { await moLoad(); } catch (e) { toastErr(e); }
  moRender();
}

const moWorking = () => t('mo.working') + (MO.step ? ` ${MO.step}` : '');

// several .zip at once, picked or dropped on the Mods view, of any kind: one after the other, each where it belongs (the
// app tells a vehicle package, a sound mod and skins apart); one that fails says why and the others go on
async function moSendMany(files) {
  if (MO.busy) return toast({ title: moWorking(), ms: 3000 });
  for (const [i, file] of files.entries()) {
    MO.step = files.length > 1 ? `${i + 1}/${files.length}` : '';
    await moSend([{ file, path: file.name }], 'auto');
  }
  MO.step = '';
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
    if (!(await moFixFirst(found))) throw Object.assign(new Error('cancelled'), { cancelled: true });
    const unclear = (found.skins || []).filter(s => !s.sure);
    if (unclear.length) await moAsk(unclear, found.kind || kind);
    else await moFinish(found.kind || kind, {}, found);
  } catch (e) {
    if (!e.cancelled) moErr(e);
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
  $('#dlgSkin').showModal();
  return new Promise(done => { MO.waiting = { kind, done }; });  // the next file waits for the answer
}

const moFew = names => names.slice(0, 4).join(', ') + (names.length > 4 ? ` +${names.length - 4}` : '');

// a vehicle package installed or removed: its weapons come into the pylon catalog and My weapons, or leave them
async function moWeaponsChanged() {
  await reloadWeapons();
  if (!$('#view-myweapons').classList.contains('hidden')) renderMyWeapons();
  if (S.sel) renderDrawer();
}

// a vehicle package about to go: its weapons go with it, and the pylons of My weapons and saved loadouts that carry
// them are left empty from then on (WTFTD finds them no more)
async function moWeaponsGo(pkg) {
  await loadWeapons();
  const keys = new Set(packageWeapons().filter(([, w]) => w.pkg === pkg).map(([k]) => k));
  if (!keys.size) return;
  const carried = val => val && typeof val === 'object' && keys.has(val.w);
  const n = MW.list.filter(cw => keys.has(cw.w)).length + S.loadouts.filter(sl => Object.values(sl.pylons || {}).some(carried)).length;
  toast({ title: t('mo.weaponsGo', { names: moFew([...keys].map(k => I18N.weapon(k))) }), sub: n ? t('mo.weaponsUsed', { n }) : '', err: n > 0, ms: n ? 10000 : 6000 });
}

// a package made for an older game names game files the game no longer has, in any part of its vehicles (the T-65's
// damage model, the FA-22+'s AIM-9JL and presets): the player picks what stands in for each, the closest first. The
// damage model's must get one (the game stops at its start without); the others may stay as they are (they fail when
// used), which is the choice where nothing in the game looks like them. null when they cancel.
function moAskFix(items, apply = null) {
  const short = path => path.split('/').pop().replace(/\.blk$/i, '');
  const opt = (value, label, on) => `<option value="${esc(value)}"${on ? ' selected' : ''}>${esc(label)}</option>`;
  // what shows picked: the choice made before (at install or a Repair, "" when left as it is), else the closest
  const rows = list => list.map(m => {
    const pick = m.decided ? m.current : (m.current || m.best);
    return `<div class="mo-fix-row">
    <div class="mo-fix-file"><div class="mo-fix-name"><b title="${esc(short(m.ref))}">${esc(short(m.ref))}</b>
      <span class="chip ${m.fatal ? 'warn' : 'dim'}">${esc(t(m.fatal ? 'mo.stopsChip' : 'mo.fixUsed'))}</span></div>
      <code class="mo-fix-path" title="${esc(m.ref)}">${esc(m.ref)}</code></div>
    <select data-ref="${esc(m.ref)}" aria-label="${esc(short(m.ref))}">${m.fatal ? '' : opt('', t('mo.fixLeave'), !pick)}${m.options.map(o => opt(o, short(o) + (o === m.best ? ` · ${t('mo.fixBest')}` : ''), o === pick)).join('')}</select></div>`;
  }).join('');
  const body = $('#moFix'), go = $('#moFixGo');
  MO.fixApply = apply;
  const answer = new Promise(done => { MO.fixing = done; });
  if (Array.isArray(items)) body.innerHTML = rows(items);
  else {  // a Repair: the dialog opens at once, its stand-ins come as they're ranked
    body.innerHTML = `<div class="mo-fix-wait"><span class="spin"></span><span>${esc(t('mo.fixLoading'))}</span></div>`;
    go.disabled = true;
    Promise.resolve(items).then(list => {
      if (!MO.fixing) return;  // closed meanwhile
      body.innerHTML = list.length ? rows(list) : `<p class="muted">${esc(t('mo.fixNone'))}</p>`;
      go.disabled = !list.length;
    }).catch(e => { $('#dlgFix').close(); moErr(e); });
  }
  $('#dlgFix').showModal();
  return answer;
}

// before installing a package: its stand-ins picked (MO.fixes, sent with the install), or false when the player cancels
async function moFixFirst(found) {
  MO.fixes = null;
  const missing = found.vehicle?.missing || [];
  if (!missing.length) return true;
  MO.fixes = await moAskFix(missing);
  return !!MO.fixes;
}

// found: what inspect said of it (a hangar's line)
async function moFinish(kind, vehicles, found = {}) {
  const ok = await moAction('install', { token: MO.token, kind, vehicles, hint: MO.hint || '', fixes: MO.fixes || {} });
  MO.fixes = null;
  if (ok && kind === 'vehicle') {  // its vehicles among WTFTD's, its test missions imported
    moVehiclesIn(ok.modVehicles || []);
    const c = ok.copies || {}, copies = [...(c.vehicles || []).map(id => I18N.unit(id)), ...(c.models || []), ...(c.textures || [])];
    const hidden = (ok.installed || []).filter(v => v.invisible), arms = ok.weapons || [];
    toast({ title: t('mo.vehicleInstalled', { names: moShortNames(ok.installed || []) }), err: hidden.length > 0,
      sub: (hidden.length ? t('mo.invisible', { names: moShortNames(hidden) }) + ' ' : '') + (copies.length ? t('mo.copies', { names: copies.join(', ') }) + ' ' : '')
        + (arms.length ? t('mo.weaponsIn', { names: moFew(arms) }) + ' ' : '') + (ok.running ? t('mo.vehicleRestart') + ' ' : '') + t('mo.vehicleInstalledHint'),
      ms: ok.running || copies.length || hidden.length || arms.length ? 14000 : 8000 });
    moWeaponsChanged();
    await addImportedMissions(ok.missions || []);
  } else if (ok && kind === 'hangar') {
    const line = moHangarLine(found.hangar || {});
    toast({ title: t('mo.hangarInstalled', { name: found.hangar?.name || '' }), sub: t('mo.hangarLine', { line }), ms: 30000,
      actions: [{ label: t('mo.copyLine'), icon: 'file', primary: true, run: () => moCopy(line) }] });
  } else if (ok) toast({ title: t('mo.installed'), sub: kind === 'sound' && ok.running ? t('mo.soundRestart') : '', ms: ok.running ? 9000 : 6000 });
  else api('mods/forget', { token: MO.token }).catch(() => {});
  return ok;
}

async function moCopy(text) {
  try { await navigator.clipboard.writeText(text); toast({ title: t('mo.lineCopied'), sub: text, ms: 5000 }); }
  catch { toast({ title: text, sub: t('mo.copyByHand'), ms: 15000 }); }
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
    if (d.morm && (d.kind === 'vehicle' || d.kind === 'sound' || d.kind === 'hangar') && !(await moGameClosed(d.kind))) return;
    if (d.mocopy) return moCopy(d.mocopy);
    if (d.morepair) {  // a package's stand-ins, missing or picked before: changed any time (the game closed, the app checks)
      const name = d.morepair;
      await moAskFix(api('mods/repairs', { name }).then(r => r.items), async fixes => {
        const r = await moAction('repair', { name, fixes });
        if (r) toast({ title: t('mo.repaired', { name }), sub: t('mo.repairedHint'), ms: 9000 });
        return !!r;
      });
      return;
    }
    if (d.mopick === 'zip') {
      MO.pickKind = d.kind === 'hangar' || d.kind === 'sight' ? d.kind : 'auto';
      $('#moZip').accept = d.kind === 'sight' ? '.zip,.blk' : '.zip';  // a sight may come alone
      return $('#moZip').click();
    }
    if (d.mopick === 'folder') return $('#moFolder').click();
    if (d.moroot) return moOpen(d.moroot);
    if (d.moopen) return moOpen('skin', d.moopen);
    if (d.mo3d) return moPreview(d.mo3d);
    if (d.morm) {
      const key = `${d.kind}|${d.morm}`;
      if (MO.arm !== key) {
        MO.arm = key;
        if (d.kind === 'vehicle') moWeaponsGo(d.morm);
        return moRender();
      }
      MO.arm = '';
      const r = await moAction('remove', { kind: d.kind, name: d.morm });
      if (r && d.kind === 'vehicle') {
        moVehiclesIn(r.modVehicles || []);
        moWeaponsChanged();
      }
      return;
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
    const files = [...e.target.files];
    e.target.value = '';
    if (!files.length) return;
    if (MO.pickKind === 'sight') return moSightFiles(files);
    if (MO.pickKind !== 'hangar') return moSendMany(files);
    (async () => { for (const file of files) await moSend([{ file, path: file.name }], 'hangar'); })();  // a hangar's files look like a package's
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
    const { kind, done } = MO.waiting;
    MO.waiting = null;
    $('#dlgSkin').close();
    done(await moFinish(kind, vehicles));
  });
  $('#moFixGo').addEventListener('click', async () => {
    const fixes = Object.fromEntries($$('#moFix select').map(s => [s.dataset.ref, s.value]));
    if (MO.fixApply) {  // a Repair: the dialog stays, its button busy, until it's done (or failed: then it can be tried again)
      const go = $('#moFixGo');
      go.disabled = true;
      go.innerHTML = `<span class="spin"></span><span>${esc(t('mo.fixApplying'))}</span>`;
      const ok = await MO.fixApply(fixes);
      go.disabled = false;
      go.textContent = t('mo.fixGo');
      if (!ok) return;
    }
    const done = MO.fixing;
    MO.fixing = null;
    $('#dlgFix').close();
    done?.(fixes);
  });
  $('#dlgFix').addEventListener('close', () => {  // cancelled: nothing installed or changed
    const done = MO.fixing;
    MO.fixing = null;
    MO.fixApply = null;
    done?.(null);
  });
  $('#dlgSkin').addEventListener('close', () => {
    if (!MO.waiting) return;
    const { done } = MO.waiting;
    MO.waiting = null;
    api('mods/forget', { token: MO.token }).catch(() => {});
    done(false);
  });
  bindLive();
}
