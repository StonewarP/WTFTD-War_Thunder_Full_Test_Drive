/* WTFTD — share a setup with a friend: a short code to paste (compressed JSON) or a .wtftd file.
   The friend imports it (Saved setups → Import, or drops the file on the window) and gets the same
   mission setup: vehicle, loadout, ammo, map, editor changes, cheats, conditions. */
'use strict';

const SHARE_PREFIX = 'WTFTD1.';

function shareable(cfg) {
  const { _autoTitle, ...c } = cfg;
  return { app: 'WTFTD', v: 1, vehicle: c.vehicle, title: c.title || _autoTitle || '', cfg: c };
}

async function encodeSetup(cfg) {
  const json = JSON.stringify(shareable(cfg));
  const stream = new Blob([json]).stream().pipeThrough(new CompressionStream('deflate-raw'));
  const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return SHARE_PREFIX + btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function decodeSetup(text) {
  text = (text || '').trim();
  let data;
  if (text.startsWith('{')) data = JSON.parse(text);  // .wtftd file
  else {
    const m = text.match(/WTFTD1\.([A-Za-z0-9_-]+)/);
    if (!m) throw new Error(t('share.invalid'));
    const bin = atob(m[1].replace(/-/g, '+').replace(/_/g, '/'));
    const bytes = Uint8Array.from(bin, ch => ch.charCodeAt(0));
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
    data = JSON.parse(await new Response(stream).text());
  }
  const cfg = data?.cfg || data;
  if (!cfg || typeof cfg !== 'object' || !cfg.vehicle) throw new Error(t('share.invalid'));
  if (!S.byId.has(cfg.vehicle)) throw new Error(t('share.unknownVehicle', { id: cfg.vehicle }));
  return { cfg, title: data.title || cfg.title || '' };
}

// ------------------------------------------------------------------ export
async function openShare(cfg = S.cfg) {
  try {
    const code = await encodeSetup(cfg);
    const v = S.byId.get(cfg.vehicle);
    $('#shareWhat').textContent = `${v ? I18N.unit(v.id) : cfg.vehicle} · ${cfg.title || cfg._autoTitle || ''}`;
    $('#shareCode').value = code;
    $('#dlgShare').dataset.file = safeFile(cfg.title || cfg._autoTitle || cfg.vehicle) + '.wtftd';
    $('#dlgShare').dataset.json = JSON.stringify(shareable(cfg), null, 1);
    $('#dlgShare').showModal();
    $('#shareCode').select();
  } catch (e) { toastErr(e); }
}

const safeFile = s => (s || 'setup').replace(/[^\w\- .()]+/g, '_').trim().slice(0, 80) || 'setup';

function saveShareFile() {
  const dlg = $('#dlgShare');
  const url = URL.createObjectURL(new Blob([dlg.dataset.json], { type: 'application/json' }));
  const a = Object.assign(document.createElement('a'), { href: url, download: dlg.dataset.file });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast({ title: t('share.fileSaved', { file: dlg.dataset.file }), ms: 3500 });
}

// ------------------------------------------------------------------ import
function openImport() {
  $('#importCode').value = '';
  $('#dlgImport').showModal();
  $('#importCode').focus();
}

async function importSetup(text) {
  try {
    const { cfg, title } = await decodeSetup(text);
    const name = title || I18N.unit(cfg.vehicle);
    S.setups.unshift({ id: Date.now().toString(36), name, vehicle: cfg.vehicle, cfg, created: Date.now() });
    await persistSetups();
    $('#dlgImport').close();
    showView('vehicles');
    await openVehicle(cfg.vehicle, cfg);
    toast({ title: t('share.imported', { name }), sub: t('share.importedHint'), ms: 6000 });
  } catch (e) { toastErr(e); }
}

function bindShare() {
  $('#shareCopy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('#shareCode').value); } catch { $('#shareCode').select(); document.execCommand('copy'); }
    toast({ title: t('action.copied'), ms: 2000 });
  });
  $('#shareFile').addEventListener('click', saveShareFile);
  $('#btnImport').addEventListener('click', openImport);
  $('#importGo').addEventListener('click', () => importSetup($('#importCode').value));
  $('#importFile').addEventListener('change', async e => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (f) importSetup(await f.text());
  });
  // drop a .wtftd file anywhere on the window
  window.addEventListener('dragover', e => { if ([...(e.dataTransfer?.items || [])].some(i => i.kind === 'file')) e.preventDefault(); });
  window.addEventListener('drop', async e => {
    const f = [...(e.dataTransfer?.files || [])].find(x => /\.(wtftd|json)$/i.test(x.name));
    if (!f) return;
    e.preventDefault();
    importSetup(await f.text());
  });
}
