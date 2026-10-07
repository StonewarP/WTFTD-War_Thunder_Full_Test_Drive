/* WTFTD — quick scenario editor: top-down map of the scenario's units.
   Edits live in S.cfg.edits = { sid, units: {name: {...}}, add: [{...}] } and are applied server-side. */
'use strict';

const ED_BLOCK_CATS = { tankModels: ['ground'], armada: ['air', 'heli'], ships: ['ship', 'boat'] };
const ED_COLORS = { enemy: '#ff5a4f', ally: '#5ab8ff', player: '#f3b33d', other: '#6b7687' };

const ED = {
  data: null, sel: null, mode: 'select', addBlock: 'tankModels', addSide: 'enemy',
  view: { scale: 1, cx: 0, cz: 0 }, drag: null, canvas: null, ctx: null, search: '', layers: [],
};

function edEdits() {
  const c = S.cfg;
  if (!c.edits || c.edits.sid !== c.scenario) c.edits = { sid: c.scenario, units: {}, add: [] };
  return c.edits;
}
function edCount() {
  const e = S.cfg?.edits;
  if (!e || e.sid !== S.cfg.scenario) return 0;
  return Object.keys(e.units || {}).length + (e.add || []).length;
}

async function openEditor() {
  const sid = S.cfg.scenario;
  try { ED.data = await api('scenario-units/' + encodeURIComponent(sid)); } catch (e) { toastErr(e); return; }
  edResolveStart(ED.data);
  if (S.cfg.targets?.mode && S.cfg.targets.mode !== 'scenario') {
    try {
      const swaps = await api('target-swaps', { vehicle: S.cfg.vehicle, scenario: sid, targets: S.cfg.targets });
      for (const u of ED.data.units) if (swaps[u.name]) { u.scnCls = u.cls; u.cls = swaps[u.name]; }
    } catch { /* keep the scenario's vehicles */ }
  }
  edEdits();
  ED.sel = null; ED.mode = 'select'; ED.search = '';
  ED.layers = [];
  ED.terrain = null;
  edLoadTerrain(ED.data.level);
  let map = null;
  try { map = await api('level-map/' + encodeURIComponent(ED.data.level || '')); } catch { /* unknown level */ }
  edMapHint(map?.layers?.length ? '' : map?.noOodle ? 'editor.noOodle' : 'editor.noMap');
  for (const l of map?.layers || []) {
    const layer = { ...l, img: null };
    ED.layers.push(layer);
    const img = new Image();
    img.onload = () => { layer.img = img; edDraw(); };
    img.onerror = () => { if (!ED.layers.some(x => x.img)) edMapHint('editor.mapError'); };
    img.src = l.url;
  }
  $('#dlgEditor').showModal();
  ED.canvas = $('#edCanvas');
  ED.ctx = ED.canvas.getContext('2d');
  edResize();
  edFit();
  edRenderPanel();
  edDraw();
}

// the scenario's triggers decide where you and some units really appear: show that, not the raw unit position
function edResolveStart(data) {
  const p = data.units.find(u => u.player);
  if (p && data.spawn) {
    Object.assign(p, { tmX: p.x, tmZ: p.z, x: data.spawn.x, y: data.spawn.y, z: data.spawn.z }, data.spawn.yaw != null ? { yaw: data.spawn.yaw } : {});
  }
  for (const u of data.units) {
    if (u.tp?.start) Object.assign(u, { x: u.tp.x, y: u.tp.y, z: u.tp.z });
  }
}

function edMapHint(key) {
  $('#edMapHint').classList.toggle('hidden', !key);
  if (key) $('#edMapHint span').textContent = t(key);
}

// ------------------------------------------------------------------ geometry
function edAllPoints() {
  const e = edEdits();
  return [...ED.data.units, ...e.add.map((a, idx) => ({ ...a, added: true, idx }))];
}
function edFit() {
  const pts = edAllPoints().filter(u => u.edit || u.player || u.added);
  const src = pts.length ? pts : ED.data.units;
  const xs = src.map(u => u.x), zs = src.map(u => u.z);
  const minx = Math.min(...xs), maxx = Math.max(...xs), minz = Math.min(...zs), maxz = Math.max(...zs);
  const w = ED.canvas.width, h = ED.canvas.height;
  const span = Math.max(maxx - minx, maxz - minz, 400) * 1.25;
  ED.view = { scale: Math.min(w, h) / span, cx: (minx + maxx) / 2, cz: (minz + maxz) / 2 };
}
function edFitMap() {
  const l = ED.layers[ED.layers.length - 1];  // the most detailed layer (ground battle map when there is one)
  if (!l) return edFit();
  const w = ED.canvas.width, h = ED.canvas.height;
  const span = Math.max(l.max[0] - l.min[0], l.max[1] - l.min[1]) * 1.04;
  ED.view = { scale: Math.min(w, h) / span, cx: (l.min[0] + l.max[0]) / 2, cz: (l.min[1] + l.max[1]) / 2 };
}
const edToScreen = (x, z) => [ED.canvas.width / 2 + (x - ED.view.cx) * ED.view.scale, ED.canvas.height / 2 - (z - ED.view.cz) * ED.view.scale];
const edToWorld = (sx, sy) => [ED.view.cx + (sx - ED.canvas.width / 2) / ED.view.scale, ED.view.cz - (sy - ED.canvas.height / 2) / ED.view.scale];

function edResize() {
  const box = ED.canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  ED.canvas.width = Math.max(300, box.width) * dpr;
  ED.canvas.height = Math.max(300, box.height) * dpr;
  ED.canvas.style.width = box.width + 'px';
  ED.canvas.style.height = box.height + 'px';
}

// ------------------------------------------------------------------ state per unit
function edUnitState(u) {
  const e = edEdits();
  if (u.added) return { ...u, removed: false };
  const ov = e.units[u.name] || {};
  return { ...u, ...ov, cls: ov.cls || u.cls, removed: !!ov.remove, moved: ov.x != null, ox: u.x, oz: u.z };
}
// u: a unit state (edUnitState), so the side picked in the editor wins
function edSide(u) {
  if (u.player) return 'player';
  if (!u.edit && !u.added) return 'other';  // scenery / objects, whatever their team
  if (u.side) return u.side;
  if (u.added) return 'enemy';
  if (!u.army) return 'other';
  return u.army === (ED.data.army || 1) ? 'ally' : 'enemy';
}
// movement choices for a side: enemies can hunt you, allies can escort you
function edBehaviors(side, air, added) {
  return [['', added ? 'editor.move.free' : 'editor.asScenario'], ...(air ? [] : [['stay', 'editor.move.stay']]),
    side === 'ally' ? ['follow', 'editor.move.follow'] : ['hunt', 'editor.move.hunt']];
}

// ------------------------------------------------------------------ drawing
function edDraw() {
  const { ctx, canvas } = ED;
  if (!ctx) return;
  const dpr = window.devicePixelRatio || 1;
  const css = getComputedStyle(document.documentElement);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = css.getPropertyValue('--bg-2').trim() || '#0e1217';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // tactical maps of the level (full map, then the detailed ground battle map), placed by their world extents
  ctx.save();
  ctx.imageSmoothingQuality = 'high';
  for (const l of ED.layers) {
    if (!l.img) continue;
    const [mnx, mnz] = l.min, [mxx, mxz] = l.max;
    const [sx0, yTop] = edToScreen(mnx, l.zUp ? mxz : mnz), [sx1, yBot] = edToScreen(mxx, l.zUp ? mnz : mxz);
    ctx.globalAlpha = 0.92;
    if (yBot >= yTop) ctx.drawImage(l.img, sx0, yTop, sx1 - sx0, yBot - yTop);
    else { ctx.save(); ctx.translate(0, yTop); ctx.scale(1, -1); ctx.drawImage(l.img, sx0, 0, sx1 - sx0, yTop - yBot); ctx.restore(); }
  }
  ctx.restore();

  // grid
  const target = 90 * dpr / ED.view.scale;
  const step = [25, 50, 100, 250, 500, 1000, 2500, 5000, 10000].find(s => s >= target) || 10000;
  const [wx0, wz1] = edToWorld(0, 0), [wx1, wz0] = edToWorld(canvas.width, canvas.height);
  ctx.strokeStyle = ED.layers.some(l => l.img) ? 'rgba(255,255,255,.08)' : (css.getPropertyValue('--line').trim() || '#232b37');
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = Math.floor(wx0 / step) * step; x <= wx1; x += step) { const [sx] = edToScreen(x, 0); ctx.moveTo(sx, 0); ctx.lineTo(sx, canvas.height); }
  for (let z = Math.floor(wz0 / step) * step; z <= wz1; z += step) { const [, sy] = edToScreen(0, z); ctx.moveTo(0, sy); ctx.lineTo(canvas.width, sy); }
  ctx.stroke();
  // scale bar
  ctx.fillStyle = css.getPropertyValue('--muted').trim();
  ctx.font = `${11 * dpr}px Segoe UI, sans-serif`;
  const barPx = step * ED.view.scale;
  ctx.fillRect(14 * dpr, canvas.height - 18 * dpr, barPx, 2 * dpr);
  ctx.fillText(`${step} m`, 14 * dpr, canvas.height - 24 * dpr);

  const player = ED.data.units.find(u => u.player);
  const pPos = player ? edPlayerPos(player) : null;
  const rw = ED.data.spawn?.runway;
  if (rw) {  // runway the scenario spawns you on
    const [a, b] = edToScreen(rw[0][0], rw[0][1]), [c, d] = edToScreen(rw[1][0], rw[1][1]);
    ctx.save(); ctx.lineCap = 'round';
    ctx.strokeStyle = 'rgba(0,0,0,.45)'; ctx.lineWidth = 9 * dpr; ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c, d); ctx.stroke();
    ctx.strokeStyle = ED_COLORS.player + 'cc'; ctx.lineWidth = 5 * dpr; ctx.setLineDash([10 * dpr, 8 * dpr]);
    ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c, d); ctx.stroke(); ctx.restore();
  }
  for (const u of ED.data.units) {  // where units respawn later in the mission
    if (!u.tp || u.tp.start || !(u.edit || u.player)) continue;
    const [a, b] = edToScreen(u.tp.x, u.tp.z), [c, d] = edToScreen(u.x, u.z);
    ctx.save(); ctx.setLineDash([2 * dpr, 4 * dpr]); ctx.strokeStyle = 'rgba(255,255,255,.4)'; ctx.lineWidth = 1 * dpr;
    ctx.beginPath(); ctx.moveTo(c, d); ctx.lineTo(a, b); ctx.stroke(); ctx.setLineDash([]);
    ctx.strokeStyle = ED_COLORS[edSide(edUnitState(u))] || '#fff'; ctx.lineWidth = 2 * dpr;
    ctx.beginPath(); ctx.arc(a, b, 6 * dpr, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
  }
  // hunt / escort lines
  for (const u of edAllPoints().map(edUnitState)) {
    if ((u.behavior === 'hunt' || u.behavior === 'follow') && pPos && !u.removed) {
      const [a, b] = edToScreen(u.x, u.z), [c, d] = edToScreen(pPos.x, pPos.z);
      ctx.setLineDash([6 * dpr, 6 * dpr]); ctx.strokeStyle = ED_COLORS[u.behavior === 'hunt' ? 'enemy' : 'ally'] + '99';
      ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c, d); ctx.stroke(); ctx.setLineDash([]);
    }
  }
  // markers: others first, then editable, then player
  const pts = edAllPoints().map(edUnitState);
  pts.sort((a, b) => (a.edit || a.added ? 1 : 0) - (b.edit || b.added ? 1 : 0) + (a.player ? 2 : 0) - (b.player ? 2 : 0));
  for (const u of pts) edMarker(u, u.player ? pPos : u, dpr);
}

function edPlayerPos(p) {
  const pl = edEdits().player;
  return pl ? { ...p, ...pl } : p;
}

function edMarker(u, pos, dpr) {
  const { ctx } = ED;
  const [sx, sy] = edToScreen(pos.x, pos.z);
  const side = edSide(u);
  const editable = u.edit || u.added || u.player;
  if (u.moved && !u.removed) {  // where the unit was in the scenario
    const [ox, oy] = edToScreen(u.ox, u.oz);
    ctx.save(); ctx.setLineDash([3 * dpr, 4 * dpr]); ctx.strokeStyle = 'rgba(255,255,255,.55)'; ctx.lineWidth = 1.5 * dpr;
    ctx.beginPath(); ctx.moveTo(ox, oy); ctx.lineTo(sx, sy); ctx.stroke();
    ctx.beginPath(); ctx.arc(ox, oy, 3 * dpr, 0, Math.PI * 2); ctx.stroke(); ctx.restore();
  }
  const r = (editable ? 7 : 3) * dpr;
  const color = ED_COLORS[side];
  ctx.save();
  ctx.globalAlpha = u.removed ? 0.35 : 1;
  ctx.fillStyle = color;
  ctx.strokeStyle = u.added ? '#fff' : 'rgba(0,0,0,.6)';
  ctx.lineWidth = (u.added ? 2 : 1) * dpr;
  ctx.beginPath();
  if (u.player) {
    ctx.arc(sx, sy, r + 2 * dpr, 0, Math.PI * 2);
  } else if (u.block === 'armada') {
    ctx.moveTo(sx, sy - r); ctx.lineTo(sx + r, sy + r * 0.8); ctx.lineTo(sx - r, sy + r * 0.8); ctx.closePath();
  } else if (u.block === 'ships') {
    ctx.moveTo(sx, sy - r); ctx.lineTo(sx + r, sy); ctx.lineTo(sx, sy + r); ctx.lineTo(sx - r, sy); ctx.closePath();
  } else if (editable) {
    ctx.rect(sx - r * 0.85, sy - r * 0.85, r * 1.7, r * 1.7);
  } else {
    ctx.arc(sx, sy, r, 0, Math.PI * 2);
  }
  ctx.fill(); if (editable) ctx.stroke();
  if (u.removed) {
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 * dpr; ctx.beginPath();
    ctx.moveTo(sx - r, sy - r); ctx.lineTo(sx + r, sy + r); ctx.moveTo(sx + r, sy - r); ctx.lineTo(sx - r, sy + r); ctx.stroke();
  }
  if (u.behavior === 'stay' && !u.removed) {
    ctx.fillStyle = '#fff'; ctx.fillRect(sx - 2 * dpr, sy - 2 * dpr, 4 * dpr, 4 * dpr);
  }
  const selected = ED.sel && ((u.player && ED.sel.player) || (!u.player && ED.sel.key === edKey(u)));
  if (selected) {
    ctx.strokeStyle = ED_COLORS.player; ctx.lineWidth = 2 * dpr; ctx.beginPath(); ctx.arc(sx, sy, r + 6 * dpr, 0, Math.PI * 2); ctx.stroke();
  }
  if (editable && ED.view.scale * 300 > 40 * dpr) {
    ctx.globalAlpha = u.removed ? 0.4 : 0.95;
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--text').trim();
    ctx.font = `${(u.player ? 12 : 11) * dpr}px Segoe UI, sans-serif`;
    const label = u.player ? t('editor.you') : I18N.unit(u.cls) + (u.count > 1 ? ` ×${u.count}` : '');
    if (ED.layers.some(l => l.img)) {  // keep labels readable over the map
      ctx.lineWidth = 3 * dpr; ctx.strokeStyle = 'rgba(0,0,0,.65)'; ctx.strokeText(label, sx + r + 5 * dpr, sy + 4 * dpr);
      ctx.fillStyle = '#fff';
    }
    ctx.fillText(label, sx + r + 5 * dpr, sy + 4 * dpr);
  }
  ctx.restore();
}

const edKey = u => (u.added ? 'add:' + u.idx : 'u:' + u.name);

// ------------------------------------------------------------------ interaction
function edHit(sx, sy) {
  const dpr = window.devicePixelRatio || 1;
  let best = null, bd = 14 * dpr;
  for (const u of edAllPoints().map(edUnitState)) {
    if (!(u.edit || u.added || u.player)) continue;
    const pos = u.player ? edPlayerPos(u) : u;
    const [x, y] = edToScreen(pos.x, pos.z);
    const d = Math.hypot(x - sx, y - sy);
    if (d < bd) { bd = d; best = u; }
  }
  return best;
}

function edCanvasPoint(ev) {
  const rect = ED.canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  return [(ev.clientX - rect.left) * dpr, (ev.clientY - rect.top) * dpr];
}

// ground height of the level (decoded from the game's heightmap by the server), when it has one
async function edLoadTerrain(level) {
  try {
    const meta = await api('terrain/' + encodeURIComponent(level || ''));
    if (!meta.available) return;
    const buf = await (await fetch(meta.url)).arrayBuffer();
    if (ED.data?.level !== level) return;
    ED.terrain = { ...meta, grid: new Uint16Array(buf) };
    edRenderPanel();
  } catch { /* no terrain: heights are estimated */ }
}

function edGround(x, z) {
  const T = ED.terrain;
  if (!T) return null;
  const fx = (x - T.ofs[0]) / T.cell, fz = (z - T.ofs[1]) / T.cell;
  const i = Math.floor(fx), j = Math.floor(fz);
  if (i < 0 || j < 0 || i >= T.w - 1 || j >= T.h - 1) return null;
  const tx = fx - i, tz = fz - j, g = T.grid, w = T.w;
  const v = (g[j * w + i] * (1 - tx) + g[j * w + i + 1] * tx) * (1 - tz) + (g[(j + 1) * w + i] * (1 - tx) + g[(j + 1) * w + i + 1] * tx) * tz;
  return T.hmin + v * T.hscale / 65535;
}

function edGroundY(x, z) {
  const g = edGround(x, z);
  if (g != null) return g + 0.5;  // on the ground (+0.5 m so the vehicle settles on it)
  // no heightmap: the nearest known ground-level unit gives the terrain height (+1 m)
  let best = null, bd = Infinity;
  for (const u of ED.data.units) {
    if (u.block === 'armada') continue;
    const d = Math.hypot(u.x - x, u.z - z);
    if (d < bd) { bd = d; best = u; }
  }
  return best ? best.y + 1 : 50;
}

function edAdd(x, z) {
  const e = edEdits();
  const block = ED.addBlock;
  const player = ED.data.units.find(u => u.player);
  const defaultCls = { tankModels: S.cfg.vehicle && S.byId.get(S.cfg.vehicle)?.c === 'ground' ? S.cfg.vehicle : 'ussr_t_72a',
    armada: 'mig-21_mf', ships: 'us_destroyer_fletcher' }[block];
  const y = block === 'armada' ? Math.max((player?.y || 0) + 800, (edGround(x, z) ?? 0) + 800) : block === 'ships' ? 0 : Math.round(edGroundY(x, z) * 10) / 10;
  const yaw = player ? Math.atan2(player.z - z, player.x - x) * 180 / Math.PI : 0;
  e.add.push({ block, cls: defaultCls, x: Math.round(x), y: Math.round(y), z: Math.round(z), yaw: Math.round(yaw), count: 1, attack: 'fire_at_will', behavior: '', speed: 450, side: ED.addSide });
  ED.sel = { key: 'add:' + (e.add.length - 1) };
  ED.mode = 'select';
}

function edBind() {
  const cv = $('#edCanvas');
  cv.addEventListener('pointerdown', ev => {
    const [sx, sy] = edCanvasPoint(ev);
    cv.setPointerCapture(ev.pointerId);
    if (ED.mode === 'add') {
      const [x, z] = edToWorld(sx, sy);
      edAdd(x, z);
      edRenderPanel(); edDraw();
      return;
    }
    const hit = edHit(sx, sy);
    if (hit) {
      ED.sel = hit.player ? { player: true } : { key: edKey(hit) };
      const movable = hit.added || hit.player || (hit.edit && !hit.tpl && !hit.removed);
      ED.drag = movable ? { kind: 'unit', u: hit, moved: false } : null;
      edRenderPanel(); edDraw();
    } else {
      ED.drag = { kind: 'pan', sx, sy, cx: ED.view.cx, cz: ED.view.cz };
    }
  });
  cv.addEventListener('pointermove', ev => {
    if (!ED.drag) return;
    const [sx, sy] = edCanvasPoint(ev);
    if (ED.drag.kind === 'pan') {
      ED.view.cx = ED.drag.cx - (sx - ED.drag.sx) / ED.view.scale;
      ED.view.cz = ED.drag.cz + (sy - ED.drag.sy) / ED.view.scale;
    } else {
      const [x, z] = edToWorld(sx, sy);
      const e = edEdits();
      if (ED.drag.u.player) {
        const p = ED.data.units.find(u => u.player);
        const onGround = S.cfg.block === 'tankModels' && edGround(x, z) != null;
        let y = onGround ? Math.round(edGroundY(x, z) * 10) / 10 : (e.player?.y ?? p.y);
        // an aircraft moved off its runway starts in the air
        if (S.cfg.block === 'armada' && !e.player) y = Math.max(y, Math.round((edGround(x, z) ?? p.y) + (S.cfg.altitude || 1000)));
        e.player = { x: Math.round(x), y, z: Math.round(z), yaw: e.player?.yaw ?? p.yaw };
      } else if (ED.drag.u.added) {
        const a = e.add[ED.drag.u.idx];
        a.x = Math.round(x); a.z = Math.round(z);
        if (a.block === 'tankModels') a.y = Math.round(edGroundY(x, z) * 10) / 10;
      } else {
        const u = ED.data.units.find(x => x.name === ED.drag.u.name);
        edSet(u, { x: Math.round(x), z: Math.round(z), ...(u.block === 'tankModels' ? { y: Math.round(edGroundY(x, z) * 10) / 10 } : {}) });
      }
      ED.drag.moved = true;
    }
    edDraw();
  });
  cv.addEventListener('pointerup', () => { if (ED.drag?.moved) edRenderPanel(); ED.drag = null; });
  cv.addEventListener('wheel', ev => {
    ev.preventDefault();
    const [sx, sy] = edCanvasPoint(ev);
    const [wx, wz] = edToWorld(sx, sy);
    ED.view.scale *= ev.deltaY < 0 ? 1.18 : 1 / 1.18;
    const [nx, nz] = edToWorld(sx, sy);
    ED.view.cx += wx - nx; ED.view.cz += wz - nz;
    edDraw();
  }, { passive: false });
  window.addEventListener('resize', () => { if ($('#dlgEditor').open) { edResize(); edDraw(); } });

  $('#edPanel').addEventListener('click', edPanelClick);
  $('#edPanel').addEventListener('change', edPanelChange);
  $('#edPanel').addEventListener('input', ev => {
    if (ev.target.id === 'edSearch') { ED.search = ev.target.value; edRenderResults(); }
  });
  $('#edTools').addEventListener('click', ev => {
    const b = ev.target.closest('button'); if (!b) return;
    if (b.dataset.edmode) { ED.mode = b.dataset.edmode; if (b.dataset.block) ED.addBlock = b.dataset.block; }
    if (b.dataset.edside) ED.addSide = b.dataset.edside;
    if (b.dataset.edact === 'fit') edFit();
    if (b.dataset.edact === 'fitMap') edFitMap();
    if (b.dataset.edact === 'reset') { S.cfg.edits = { sid: S.cfg.scenario, units: {}, add: [] }; ED.sel = null; }
    edRenderPanel(); edDraw();
  });
  $('#edDone').addEventListener('click', () => $('#dlgEditor').close());
  $('#dlgEditor').addEventListener('keydown', ev => {
    if (!['Delete', 'Backspace'].includes(ev.key) || ev.target.closest('input, select, textarea')) return;
    const u = edSelected();
    if (!u || u.player) return;
    ev.preventDefault();
    if (u.added) { edEdits().add.splice(u.idx, 1); ED.sel = null; } else edSet(u, { remove: !edUnitState(u).removed });
    edRenderPanel(); edDraw();
  });
  $('#dlgEditor').addEventListener('close', () => { if (S.sel) renderDrawer(); });
}

// ------------------------------------------------------------------ side panel
function edSelected() {
  if (!ED.sel) return null;
  if (ED.sel.player) return ED.data.units.find(u => u.player);
  const [kind, id] = ED.sel.key.split(/:(.*)/s);
  if (kind === 'add') { const a = edEdits().add[+id]; return a ? { ...a, added: true, idx: +id } : null; }
  return ED.data.units.find(u => u.name === id) || null;
}

function edSet(u, patch) {
  const e = edEdits();
  if (u.added) { Object.assign(e.add[u.idx], patch); return; }
  const cur = Object.assign({}, e.units[u.name], patch);
  for (const k of Object.keys(cur)) if (cur[k] === '' || cur[k] == null || cur[k] === false || (k === 'cls' && cur[k] === u.cls) || (k === 'count' && +cur[k] === +u.count) || (u.tpl && k === 'attack' && cur[k] !== 'hold_fire') || (k === 'side' && cur[k] === edSide({ ...u, side: '' }))) delete cur[k];
  if (Object.keys(cur).length) e.units[u.name] = cur; else delete e.units[u.name];
}

function edRenderPanel() {
  $$('#edTools [data-edmode]').forEach(b => b.classList.toggle('active', b.dataset.edmode === ED.mode && (ED.mode !== 'add' || b.dataset.block === ED.addBlock)));
  $$('#edTools [data-edside]').forEach(b => b.classList.toggle('active', b.dataset.edside === ED.addSide));
  $('#edFitMap').classList.toggle('hidden', !ED.layers.length);
  $('#edHint').textContent = ED.mode === 'add' ? t(ED.addSide === 'ally' ? 'editor.hintAddAlly' : 'editor.hintAdd') : t('editor.hintSelect');
  $('#edChanges').textContent = t('editor.changes', { n: edCount() });
  const u = edSelected();
  const panel = $('#edInspector');
  if (!u) { panel.innerHTML = `<p class="hint">${esc(t('editor.noSel'))}</p>`; edRenderList(); return; }
  if (u.player) {
    const p = edPlayerPos(u);
    const sp = ED.data.spawn;
    const spawnNote = sp ? `<p class="hint">${esc(t(edEdits().player ? 'editor.spawnMoved' : sp.runway ? 'editor.spawnRunway' : 'editor.spawnArea'))}</p>` : '';
    panel.innerHTML = `<div class="ed-title">${icon('target', 'ic-sm')} ${esc(t('editor.playerStart'))}</div>
      <p class="hint">${esc(t(S.cfg.block === 'armada' ? 'editor.playerHintAir' : 'editor.playerHint'))}</p>${spawnNote}
      <div class="field-row"><div class="field"><label>${esc(t('editor.height'))}</label><input type="number" data-edf="py" value="${Math.round(p.y)}">${edGroundInfo(p, S.cfg.block !== 'tankModels', 'py')}</div>
      <div class="field"><label>${esc(t('adv.heading'))}</label><input type="number" data-edf="pyaw" value="${Math.round(p.yaw || 0)}"></div></div>
      ${edEdits().player ? `<button class="btn btn-ghost btn-sm" data-edact="resetPlayer">${icon('refresh', 'ic-sm')}${esc(t('mods.reset'))}</button>` : ''}`;
    edRenderList();
    return;
  }
  const st = edUnitState(u);
  const cats = ED_BLOCK_CATS[u.block] || [];
  const v = S.byId.get(st.cls);
  const air = u.block === 'armada';
  const side = edSide(st);
  const moveSeg = `<div class="field"><label>${esc(t('editor.move'))}</label><div class="seg seg-wrap3">
      ${edBehaviors(side, air, u.added).map(([k, l]) => `<button class="${(st.behavior || '') === k ? 'active' : ''}" data-edbeh="${k}">${esc(t(l))}</button>`).join('')}
    </div>${st.behavior === 'follow' ? `<small class="muted">${esc(t('editor.followHint'))}</small>` : ''}${st.moves && !u.added ? `<small class="muted">${esc(t('editor.movesHint'))}</small>` : ''}</div>`;
  const removed = `<p class="hint">${esc(t('editor.removedHint'))}</p><button class="btn btn-sm" data-edact="restore">${icon('refresh', 'ic-sm')}${esc(t('editor.restore'))}</button>`;
  if (u.tpl) {
    panel.innerHTML = `<div class="ed-title">${v ? flagHTML(v.n) : ''}<b>${esc(v ? I18N.unit(v.id) : st.cls)}</b></div>
      <div class="ed-sub muted">${esc(u.name)} · ${esc(t('editor.fromTemplate'))}</div>
      ${st.removed ? removed : `
      <p class="hint">${esc(t('editor.tplNote'))}</p>
      <div class="field"><label>${esc(t('editor.fire'))}</label><select data-edf="attack">
        ${[['', 'editor.asScenario'], ['hold_fire', 'editor.fire.passive']].map(([k, l]) => `<option value="${k}"${(st.attack === 'hold_fire' ? 'hold_fire' : '') === k ? ' selected' : ''}>${esc(t(l))}</option>`).join('')}
      </select></div>
      ${moveSeg}
      <button class="btn btn-ghost btn-sm btn-danger" data-edact="remove">${icon('trash', 'ic-sm')}${esc(t('editor.remove'))}</button>`}`;
    edRenderList();
    return;
  }
  panel.innerHTML = `<div class="ed-title">${v ? flagHTML(v.n) : ''}<b>${esc(v ? I18N.unit(v.id) : st.cls)}</b>${v?.br ? `<span class="chip">${fmtBR(v.br[1])}</span>` : ''}</div>
    <div class="ed-sub muted">${esc(u.added ? t('editor.added') : u.name)} · ${esc(t('editor.block.' + u.block))}</div>
    ${u.scnCls && st.cls === u.cls ? `<p class="hint">${esc(t('editor.retargeted', { cls: I18N.unit(u.scnCls) }))}</p>` : ''}
    ${u.tp ? `<p class="hint">${esc(t(u.tp.start ? (st.moved ? 'editor.tpStartMoved' : 'editor.tpStart') : 'editor.tpLater'))}</p>` : ''}
    ${st.removed ? removed : `
    <div class="field"><label>${esc(t('editor.side'))}</label><div class="seg ed-side">
      <button class="${side === 'enemy' ? 'active' : ''}" data-edside="enemy"><i class="dot enemy"></i>${esc(t('editor.enemy'))}</button>
      <button class="${side === 'ally' ? 'active' : ''}" data-edside="ally"><i class="dot ally"></i>${esc(t('editor.ally'))}</button></div></div>
    <div class="field"><label>${esc(t('editor.vehicle'))}</label>
      <input id="edSearch" type="search" placeholder="${esc(t('editor.searchVehicle'))}" value="${esc(ED.search)}" autocomplete="off">
      <div class="ed-results" id="edResults" data-cats="${cats.join(',')}"></div></div>
    <div class="field-row">
      <div class="field"><label>${esc(t('editor.count'))}</label><input type="number" min="1" max="12" data-edf="count" value="${st.count || 1}"></div>
      <div class="field"><label>${esc(t('editor.fire'))}</label><select data-edf="attack">
        ${[['', 'editor.asScenario'], ['fire_at_will', 'editor.fire.aggressive'], ['return_fire', 'editor.fire.return'], ['hold_fire', 'editor.fire.passive']]
          .filter(([k]) => k || !u.added).map(([k, l]) => `<option value="${k}"${(st.attack || '') === k && (k || !u.added) ? ' selected' : ''}>${esc(t(l))}</option>`).join('')}
      </select></div>
    </div>
    ${moveSeg}
    ${air ? `<div class="field-row"><div class="field"><label>${esc(t('cond.altitude'))}</label><input type="number" data-edf="y" value="${Math.round(st.y)}">${edGroundInfo(st, true)}</div>
      ${u.added ? `<div class="field"><label>${esc(t('cond.speed'))} (km/h)</label><input type="number" data-edf="speed" value="${Math.round(st.speed || 450)}"></div>` : ''}</div>` : ''}
    ${u.block === 'tankModels' && (u.added || st.moved) ? `<div class="field"><label>${esc(t('editor.height'))}</label><input type="number" data-edf="y" value="${Math.round(st.y)}">${edGroundInfo(st, false) || `<small class="muted">${esc(t('editor.heightHint'))}</small>`}</div>` : ''}
    <div class="row gap ed-actions">
      ${st.moved ? `<button class="btn btn-ghost btn-sm" data-edact="resetPos">${icon('refresh', 'ic-sm')}${esc(t('editor.resetPos'))}</button>` : ''}
      <button class="btn btn-ghost btn-sm btn-danger" data-edact="${u.added ? 'delete' : 'remove'}">${icon('trash', 'ic-sm')}${esc(t(u.added ? 'action.delete' : 'editor.remove'))}</button>
    </div>`}`;
  edRenderResults();
  edRenderList();
}

// under a height field: ground level here, and height above it (aircraft) or a button to put the unit on it
function edGroundInfo(u, air, field = 'y') {
  const g = edGround(u.x, u.z);
  if (g == null) return '';
  const agl = Math.round(u.y - g);
  return `<small class="muted ed-ground">${esc(t('editor.groundHere', { h: Math.round(g) }))}${air ? ` · ${esc(t('editor.agl', { h: agl }))}` : ''}
    ${!air && Math.abs(u.y - g - 0.5) > 0.6 ? `<button class="btn btn-ghost btn-xs" data-edground="${field}">${esc(t('editor.onGround'))}</button>` : ''}</small>`;
}

function edRenderResults() {
  const box = $('#edResults');
  if (!box) return;
  const cats = box.dataset.cats.split(',');
  const q = norm(ED.search);
  const u = edSelected();
  const cur = u ? edUnitState(u).cls : '';
  let list = S.vehicles.filter(v => cats.includes(v.c) && !v.h && (!q || v._s.includes(q)));
  if (!q) {
    const ref = S.byId.get(cur)?.br?.[1] ?? 5;
    list.sort((a, b) => Math.abs((a.br[1] ?? 99) - ref) - Math.abs((b.br[1] ?? 99) - ref));
  }
  list = list.slice(0, 40);
  box.innerHTML = list.map(v => `<button class="ed-res${v.id === cur ? ' active' : ''}" data-edcls="${esc(v.id)}">${flagHTML(v.n)}<span>${esc(I18N.unit(v.id))}</span><b>${fmtBR(v.br?.[1])}</b></button>`).join('')
    || `<p class="hint">${esc(t('results.empty'))}</p>`;
}

function edRenderList() {
  const e = edEdits();
  const groups = { enemy: [], ally: [] };
  for (const u of ED.data.units.filter(x => x.edit)) {
    const st = edUnitState(u);
    const side = edSide(st);
    const changed = !!e.units[u.name];
    (groups[side] || groups.enemy).push(`<button class="ed-row${ED.sel?.key === 'u:' + u.name ? ' active' : ''}${st.removed ? ' removed' : ''}" data-edsel="u:${esc(u.name)}">
      <i class="dot ${side}"></i><span>${esc(I18N.unit(st.cls))}${st.count > 1 ? ` ×${st.count}` : ''}</span>${u.tpl ? `<i class="chip dim">${esc(t('editor.tpl'))}</i>` : ''}${changed ? '<b>●</b>' : ''}</button>`);
  }
  e.add.forEach((a, i) => {
    const side = a.side === 'ally' ? 'ally' : 'enemy';
    groups[side].push(`<button class="ed-row added${ED.sel?.key === 'add:' + i ? ' active' : ''}" data-edsel="add:${i}">
      <i class="dot ${side}"></i><span>${esc(I18N.unit(a.cls))}${a.count > 1 ? ` ×${a.count}` : ''}</span><b>+</b></button>`);
  });
  const html = ['enemy', 'ally'].filter(k => groups[k].length)
    .map(k => `<div class="ed-group">${esc(t(k === 'enemy' ? 'editor.enemies' : 'editor.allies'))} <span class="muted">${groups[k].length}</span></div>${groups[k].join('')}`).join('');
  $('#edList').innerHTML = html || `<p class="hint">${esc(t('editor.noUnits'))}</p>`;
}

function edPanelClick(ev) {
  const b = ev.target.closest('button'); if (!b) return;
  const u = edSelected();
  if (b.dataset.edsel) { ED.sel = { key: b.dataset.edsel }; ED.search = ''; edRenderPanel(); edDraw(); return; }
  if (!u) return;
  if (b.dataset.edcls) { edSet(u, { cls: b.dataset.edcls }); }
  else if (b.dataset.edbeh !== undefined) { edSet(u, { behavior: b.dataset.edbeh }); }
  else if (b.dataset.edside) {
    const beh = edUnitState(u).behavior;
    // hunting you only makes sense for enemies, escorting you only for allies
    const keep = !(beh === 'hunt' && b.dataset.edside === 'ally') && !(beh === 'follow' && b.dataset.edside === 'enemy');
    edSet(u, { side: b.dataset.edside, ...(keep ? {} : { behavior: '' }) });
  }
  else if (b.dataset.edact === 'remove') { edSet(u, { remove: true }); }
  else if (b.dataset.edact === 'restore') { edSet(u, { remove: false }); }
  else if (b.dataset.edact === 'resetPos') { edSet(u, { x: null, y: null, z: null }); }
  else if (b.dataset.edact === 'delete') { edEdits().add.splice(u.idx, 1); ED.sel = null; }
  else if (b.dataset.edact === 'resetPlayer') { delete edEdits().player; }
  else if (b.dataset.edground) {
    if (b.dataset.edground === 'py') {
      const p = edPlayerPos(u);
      edEdits().player = { x: p.x, y: Math.round(edGroundY(p.x, p.z) * 10) / 10, z: p.z, yaw: p.yaw || 0 };
    } else {
      const st = edUnitState(u);
      edSet(u, u.added ? { y: Math.round(edGroundY(st.x, st.z) * 10) / 10 } : { x: st.x, z: st.z, y: Math.round(edGroundY(st.x, st.z) * 10) / 10 });
    }
  }
  else return;
  edRenderPanel(); edDraw();
}

function edPanelChange(ev) {
  const el = ev.target, f = el.dataset.edf;
  if (!f) return;
  const u = edSelected(); if (!u) return;
  const e = edEdits();
  if (f === 'py' || f === 'pyaw') {
    const p = edPlayerPos(u);
    e.player = { x: p.x, y: f === 'py' ? +el.value : p.y, z: p.z, yaw: f === 'pyaw' ? +el.value : (p.yaw || 0) };
  } else if (f === 'count') edSet(u, { count: Math.max(1, Math.min(12, +el.value || 1)) });
  else if (f === 'attack') edSet(u, { attack: el.value });
  else if (f === 'speed') edSet(u, { speed: +el.value });
  else if (f === 'y') {
    const st = edUnitState(u);
    edSet(u, u.added ? { y: +el.value } : { x: st.x, z: st.z, y: +el.value });  // a height change keeps the unit where it is
  }
  edRenderPanel(); edDraw();
}
