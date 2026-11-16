/* WTFTD - WT Live in Mods: the posts of live.warthunder.com that WTFTD installs (vehicles, skins, sounds, missions,
   sights, hangars), read through the app (wtftd/wtlive.py), and one click to install one where it belongs. What a post
   says comes from whoever wrote it: data, every bit through esc() or textContent. */
'use strict';

const WL_TYPES = ['model', 'camouflage', 'sound', 'mission', 'sight', 'location'];
const WL_SORTS = ['created', 'downloads', 'rating'];
const WL = {
  type: WL_TYPES.includes(store.get('wlType', '')) ? store.get('wlType') : 'model',
  sort: WL_SORTS.includes(store.get('wlSort', '')) ? store.get('wlSort') : 'created',
  q: '', page: 0, posts: [], more: false, loading: false, error: '', asked: '', doing: 0,
  // post id -> {kind, names}: what an install from here put in place. A card says Installed while one of those is still
  // there (deleted in Mods, My maps or the sights: it's offered again)
  installed: new Map(Object.entries((() => { try { return store.get('wlInstalled2', {}); } catch { return {}; } })()).map(([k, v]) => [+k, v])),
};

const wlKey = () => `${WL.type}|${WL.sort}|${WL.q}`;
const wlDate = s => new Date(s * 1000).toLocaleDateString(document.documentElement.lang || undefined, { year: 'numeric', month: 'short', day: 'numeric' });
const wlNum = n => Number(n || 0).toLocaleString(document.documentElement.lang || undefined);
const WL_ERRORS = ['offline', 'file', 'filter', 'noSight'];  // the app's own words for WT Live (wl.err.*)

// a page of the feed, the first one when the filters changed. The next ones are added below the cards already there:
// the list isn't drawn again, so nothing moves or blinks while you scroll
async function wlLoad(next = false) {
  if (WL.loading) return;
  const key = wlKey();
  if (!next) { WL.page = 0; WL.posts = []; WL.more = false; }
  WL.loading = true; WL.error = ''; WL.asked = key;
  const grid = next && MO.tab === 'live' ? $('#moBody .wl-grid') : null;
  if (grid) wlFoot(); else moRender();
  let added = [];
  try {
    const r = await api('wtlive/feed', { content: WL.type, sort: WL.sort, page: WL.page, q: WL.q });
    if (WL.asked !== key) return;  // the filters changed meanwhile: that answer is for another list
    const seen = new Set(WL.posts.map(p => p.id));
    added = r.posts.filter(p => !seen.has(p.id));
    WL.posts.push(...added);
    WL.more = r.more;
    WL.page += 1;
  } catch (e) {
    WL.error = WL_ERRORS.includes(e.data?.code) ? t('wl.err.' + e.data.code) : t('toast.error', { msg: e.message || e });
  } finally {
    WL.loading = false;
    if (MO.tab === 'live' && grid?.isConnected && WL.asked === key) {
      grid.insertAdjacentHTML('beforeend', added.map(wlCard).join(''));
      wlFoot();
      wlWatch();  // still far from the end: the next page comes at once
    } else if (MO.tab === 'live') moRender();
  }
}

function wlButton(p) {
  if (WL.doing === p.id) return `<button class="btn btn-sm btn-primary" disabled>${esc(MO.step || t('mo.working'))}</button>`;
  const done = wlIsInstalled(p.id);
  return `<button class="btn btn-sm${done ? ' btn-ghost' : ' btn-primary'}" data-wlinstall="${p.id}"${MO.busy ? ' disabled' : ''}>${icon(done ? 'check' : 'play', 'ic-sm')}<span>${esc(t(done ? 'wl.installed' : 'mo.install'))}</span></button>`;
}

function wlCard(p) {
  return `<div class="wl-card" data-wlpost="${p.id}" role="button" tabindex="0">
    <div class="wl-img">${p.images[0] ? `<img src="${esc(p.images[0])}" alt="" loading="lazy" referrerpolicy="no-referrer">` : icon('file', 'ic-xl')}</div>
    <div class="wl-body"><div class="wl-title" title="${esc(p.title)}">${esc(p.title)}</div>
      <div class="wl-meta"><span>${esc(p.author)}</span> · <span>${esc(wlDate(p.created))}</span></div>
      <div class="wl-meta">${icon('heart', 'ic-sm')}${esc(wlNum(p.likes))} · ${esc(t('wl.downloads', { n: wlNum(p.downloads) }))} · ${esc(moSize(p.file.size))}</div></div>
    <div class="wl-foot">${wlButton(p)}</div></div>`;
}

function wlHTML() {
  if (WL.asked !== wlKey() && !WL.loading) setTimeout(() => wlLoad(), 0);  // first time here, or the filters changed
  const types = WL_TYPES.map(k => `<button data-wltype="${k}" class="${WL.type === k ? 'active' : ''}">${esc(t('wl.type.' + k))}</button>`).join('');
  const sorts = WL_SORTS.map(k => `<option value="${k}"${WL.sort === k ? ' selected' : ''}>${esc(t('wl.sort.' + k))}</option>`).join('');
  const list = WL.posts.length ? `<div class="wl-grid">${WL.posts.map(wlCard).join('')}</div>`
    : WL.loading ? '' : `<div class="empty">${icon('globe', 'ic-xl')}<p>${esc(WL.error || t('wl.none'))}</p></div>`;
  return `<div class="mo-warn">${icon('globe', 'ic-sm')}<p class="hint">${esc(t(WL.type === 'location' ? 'wl.hintHangar' : 'wl.hint'))}</p></div>
    <div class="wl-bar"><div class="seg wl-types">${types}</div>
      <select id="wlSort" aria-label="${esc(t('wl.sortBy'))}">${sorts}</select>
      <input type="search" id="wlSearch" placeholder="${esc(t('wl.search'))}" value="${esc(WL.q)}" spellcheck="false" autocomplete="off"></div>
    ${list}
    <div id="wlFoot">${wlEndHTML()}</div>`;
}

// below the cards: loading, a failed page and its button, or the mark that brings the next page
const wlEndHTML = () => (WL.loading ? `<p class="muted wl-more">${esc(t('wl.loading'))}</p>`
  : WL.error && WL.posts.length ? `<div class="wl-more"><span class="muted">${esc(WL.error)}</span><button class="btn btn-sm" data-wlmore>${esc(t('wl.more'))}</button></div>`
  : WL.more ? '<div class="wl-more" id="wlEnd"></div>' : '');
function wlFoot() {
  const f = $('#wlFoot');
  if (f) f.innerHTML = wlEndHTML();
}

// the next posts come well before the list's end (about three screens ahead, measured on .content, which is what
// scrolls); a failed page waits for its button: no loop of failures
let WL_END = null;
function wlWatch() {
  WL_END ||= new IntersectionObserver(entries => {
    if (entries.some(e => e.isIntersecting) && MO.tab === 'live' && WL.more && !WL.loading && !WL.error) wlLoad(true);
  }, { root: $('.content'), rootMargin: '3000px 0px' });
  WL_END.disconnect();
  const end = $('#wlEnd');
  if (end) WL_END.observe(end);
}

// a post opened: its pictures and what its author wrote, in WTFTD
function wlOpen(id) {
  const p = WL.posts.find(x => x.id === id);
  if (!p) return;
  $('#wlTitle').textContent = p.title;
  $('#wlMeta').textContent = `${p.author} · ${wlDate(p.created)} · ${t('wl.downloads', { n: wlNum(p.downloads) })} · ${p.file.name} · ${moSize(p.file.size)}`;
  WL.openId = p.id;
  $('#wlImages').innerHTML = p.images.map((src, i) => `<img src="${esc(src)}" alt="" loading="lazy" referrerpolicy="no-referrer" data-zoom-at="${i}" title="${esc(t('wl.zoom'))}">`).join('');
  $('#wlText').textContent = p.text;
  $('#wlGo').dataset.wlinstall = p.id;
  $('#wlGo').disabled = MO.busy;
  $('#wlGo').querySelector('span').textContent = t(wlIsInstalled(p.id) ? 'wl.installAgain' : 'mo.install');
  $('#dlgLive').showModal();
}

// a post's picture full size: WT Live's are thumbnails, the picture itself is the same address without _lq (1 to 3 MB:
// asked only now). The small one shows at once, the large one replaces it when it has come.
const wlBig = src => src.replace('_lq/', '/');
function wlZoom(i) {
  const p = WL.posts.find(x => x.id === WL.openId);
  if (!p || !p.images.length) return;
  WL.zoom = (i + p.images.length) % p.images.length;
  const img = $('#wlZoomImg'), small = p.images[WL.zoom], big = new Image();
  img.src = small;
  img.dataset.want = wlBig(small);
  big.referrerPolicy = 'no-referrer';
  big.onload = () => { if (img.dataset.want === big.src) img.src = big.src; };
  big.src = wlBig(small);
  $('#wlZoomN').textContent = p.images.length > 1 ? `${WL.zoom + 1} / ${p.images.length}` : '';
  $$('#dlgZoom [data-zoom]').forEach(b => b.classList.toggle('hidden', p.images.length < 2));
  if (!$('#dlgZoom').open) $('#dlgZoom').showModal();
}

// the cards' buttons only (the pictures stay as they are), or the whole tab when another one is shown
function wlButtons() {
  if (MO.tab !== 'live') return moRender();
  for (const c of $$('#moBody .wl-card')) {
    const p = WL.posts.find(x => x.id === +c.dataset.wlpost);
    if (p) c.querySelector('.wl-foot').innerHTML = wlButton(p);
  }
}

// what is installed now, by kind: Mods' lists, the imported missions, the sight library
const WL_LISTS = {
  vehicle: () => (MO.vehicles || []).map(x => x.name), skin: () => (MO.skins || []).map(x => x.name),
  sound: () => (MO.sounds || []).map(x => x.name), hangar: () => (MO.hangars || []).map(x => x.name),
  mission: () => (S.scenarios || []).filter(s => s.imported).map(s => s.id), sight: () => (MO.sights?.sights || []).map(s => s.id),
};
const wlNames = kind => new Set(WL_LISTS[kind]?.() || []);

function wlIsInstalled(id) {
  const rec = WL.installed.get(id);
  if (!rec) return false;
  const now = wlNames(rec.kind);
  return (rec.names || []).some(n => now.has(n));
}

function wlMark(id, kind, names) {
  if (!names.length) return;
  WL.installed.set(id, { kind, names: names.slice(0, 200) });
  try { store.set('wlInstalled2', Object.fromEntries([...WL.installed].slice(-2000))); } catch { /* kept for this session only */ }
}

// one click: the post's file into the app, then where it belongs (as an archive picked in Mods, an imported mission,
// sights for the library)
async function wlInstall(id) {
  const p = WL.posts.find(x => x.id === id);
  if (!p) return;
  if (MO.busy) return toast({ title: moWorking(), ms: 3000 });
  MO.token = (newId() + newId()).toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 24).padEnd(8, '0');
  const token = MO.token;
  MO.busy = true; MO.step = ''; WL.doing = p.id;
  wlButtons();
  const poll = setInterval(async () => {
    const r = await api('wtlive/progress', { token }).catch(() => null);
    if (r && r.size > 0 && WL.doing === p.id) {
      MO.step = `${moSize(r.done)} / ${moSize(r.size)}`;
      const b = $(`.wl-card[data-wlpost="${p.id}"] .wl-foot`);
      if (b) b.innerHTML = wlButton(p);
    }
  }, 700);
  let ok = false, names = null;  // names: what came in, when the install says so itself
  const before = wlNames(p.kind);
  try {
    await api('wtlive/fetch', { token, link: p.file.link, name: p.file.name });
    clearInterval(poll);
    MO.step = t('mo.working');
    if (p.kind === 'mission') {
      const r = await api('wtlive/mission', { token });
      await addImportedMissions(r.missions || []);
      names = (r.missions || []).map(m => m.scenario.id);
      // addImportedMissions says what came in, as Import does
      ok = true;
    } else if (p.kind === 'sight') {
      const r = await api('wtlive/sights', { token });
      S.sights = MO.sights = { dir: r.dir, sights: r.sights };  // the vehicle panel's list and Mods → Sights
      if (S.sel) renderDrawer();
      toast({ title: t('wl.sightsDone', { n: r.added.length }), sub: t('wl.sightsHint'), ms: 8000 });
      names = r.added;
      ok = true;
    } else {
      MO.hint = (p.text.match(/hangarBlk\s*:\s*t\s*=\s*"([^"\r\n]{1,120})"/) || [])[1] || '';  // a hangar's name as its post gives it
      const found = await api('mods/inspect', { token, kind: p.kind, hint: MO.hint });
      if (!(await moFixFirst(found))) throw Object.assign(new Error('cancelled'), { cancelled: true });
      const unclear = (found.skins || []).filter(s => !s.sure);
      ok = !!(unclear.length ? await moAsk(unclear, p.kind) : await moFinish(p.kind, {}, found));
    }
  } catch (e) {
    if (e.cancelled) { /* the player cancelled: nothing installed */ } else if (e.data?.code === 'import') toast({ title: t('share.gameErr.' + e.data.name), err: true, ms: 9000 });
    else if (WL_ERRORS.includes(e.data?.code)) toast({ title: t('wl.err.' + e.data.code), err: true, ms: 9000 });
    else moErr(e);
    api('mods/forget', { token }).catch(() => {});
  } finally {
    clearInterval(poll);
    if (ok) wlMark(p.id, p.kind, names || [...wlNames(p.kind)].filter(n => !before.has(n)));
    MO.busy = false; MO.step = ''; MO.hint = ''; WL.doing = 0;
    wlButtons();
  }
}

function bindLive() {
  const body = $('#moBody');
  body.addEventListener('click', e => {
    if (MO.tab !== 'live') return;
    const b = e.target.closest('button');
    if (b?.dataset.wltype) {
      WL.type = b.dataset.wltype;
      store.set('wlType', WL.type);
      return moRender();
    }
    if (b && b.dataset.wlmore !== undefined) return wlLoad(true);
    if (b?.dataset.wlinstall) return wlInstall(+b.dataset.wlinstall);
    const card = e.target.closest('[data-wlpost]');
    if (card && !b) wlOpen(+card.dataset.wlpost);
  });
  body.addEventListener('keydown', e => {
    const card = e.target.closest?.('[data-wlpost]');
    if (MO.tab === 'live' && card && e.target === card && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); wlOpen(+card.dataset.wlpost); }
  });
  body.addEventListener('change', e => {
    if (e.target.id !== 'wlSort') return;
    WL.sort = e.target.value;
    store.set('wlSort', WL.sort);
    moRender();
  });
  body.addEventListener('keydown', e => {
    if (e.target.id !== 'wlSearch' || e.key !== 'Enter') return;
    WL.q = e.target.value.trim().slice(0, 80);
    moRender();
  });
  body.addEventListener('search', e => {  // the field's clear button
    if (e.target.id === 'wlSearch' && !e.target.value && WL.q) { WL.q = ''; moRender(); }
  }, true);
  $('#wlImages').addEventListener('click', e => {
    const img = e.target.closest('[data-zoom-at]');
    if (img) wlZoom(+img.dataset.zoomAt);
  });
  $('#dlgZoom').addEventListener('click', e => {
    const b = e.target.closest('[data-zoom]');
    if (b) wlZoom(WL.zoom + +b.dataset.zoom);
  });
  $('#dlgZoom').addEventListener('keydown', e => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); wlZoom(WL.zoom + (e.key === 'ArrowLeft' ? -1 : 1)); }
  });
  $('#wlWeb').addEventListener('click', () => {  // the post on WT Live itself, in the browser
    const p = WL.posts.find(x => x.id === WL.openId);
    if (p) api('open-url', { url: p.url }).catch(toastErr);
  });
  $('#wlGo').addEventListener('click', e => {
    $('#dlgLive').close();
    wlInstall(+e.currentTarget.dataset.wlinstall);
  });
}
