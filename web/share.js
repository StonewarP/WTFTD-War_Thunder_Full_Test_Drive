/* WTFTD — share with a friend: a short code to paste (compressed JSON) or a .wtftd file. It says what it
   holds (kind: vehicle, map, mission — see library.js); the friend imports it (Import, or drops the file on
   the window) and finds it in My vehicles / My maps / My missions. Old codes (v1, a full setup) import as
   missions. */
'use strict';

const SHARE_PREFIX = 'WTFTD1.';

async function encodeShare(obj) {
  const stream = new Blob([JSON.stringify(obj)]).stream().pipeThrough(new CompressionStream('deflate-raw'));
  const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return SHARE_PREFIX + btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function decodeShare(text) {
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
  if (!data || typeof data !== 'object' || (!data.kind && !data.cfg?.vehicle && !data.vehicle)) throw new Error(t('share.invalid'));
  if (!data.kind && !data.cfg) data = { cfg: data };  // a bare setup
  return data;
}

// ------------------------------------------------------------------ export
async function openShareObj(obj, label) {
  try {
    const code = await encodeShare(obj);
    $('#shareWhat').textContent = `${t('share.kind.' + obj.kind)} · ${label || obj.name || ''}`;
    $('#shareCode').value = code;
    $('#dlgShare').dataset.file = safeFile(label || obj.name) + '.wtftd';
    $('#dlgShare').dataset.json = JSON.stringify(obj, null, 1);
    $('#dlgShare').showModal();
    $('#shareCode').select();
  } catch (e) { toastErr(e); }
}

// the open vehicle panel's setup (its Share button)
function openShare(cfg = S.cfg) {
  const name = I18N.unit(cfg.vehicle);
  return openShareObj(shareVehicle(cfg, cfg.vehicle, name), name);
}

const safeFile = s => (s || 'wtftd').replace(/[^\w\- .()]+/g, '_').trim().slice(0, 80) || 'wtftd';

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

function bindShare() {
  $('#shareCopy').addEventListener('click', async () => {
    try { await navigator.clipboard.writeText($('#shareCode').value); } catch { $('#shareCode').select(); document.execCommand('copy'); }
    toast({ title: t('action.copied'), ms: 2000 });
  });
  $('#shareFile').addEventListener('click', saveShareFile);
  $('#btnImport').addEventListener('click', openImport);
  $('#importGo').addEventListener('click', () => importShared($('#importCode').value));
  $('#importFile').addEventListener('change', async e => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (f) importShared(await f.text());
  });
  // drop a .wtftd file anywhere on the window
  window.addEventListener('dragover', e => { if ([...(e.dataTransfer?.items || [])].some(i => i.kind === 'file')) e.preventDefault(); });
  window.addEventListener('drop', async e => {
    const f = [...(e.dataTransfer?.files || [])].find(x => /\.(wtftd|json)$/i.test(x.name));
    if (!f) return;
    e.preventDefault();
    importShared(await f.text());
  });
}
