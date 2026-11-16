/* WTFTD — app version: "new version available" alert (GitHub releases), bug report / suggestion links. */
'use strict';

const APP = { info: null };
const ISSUE_FORMS = { bug: 'bug_report.yml', idea: 'feature_request.yml' };
const ISSUE_MAX_SHARE = 2000;  // a share code longer than that would make the link too long for GitHub
const DONATE_URL = 'https://ko-fi.com/stonewarp';

const openUrl = url => api('open-url', { url }).catch(toastErr);

async function checkAppVersion() {
  try { APP.info = await api('app-version'); } catch { return; }
  renderAppVersion();
  const l = APP.info.latest;
  if (!APP.info.newer || !l) return;
  if (store.get('seenRelease', '') === l.tag) return;  // tell once per version, the pill stays
  store.set('seenRelease', l.tag);
  const auto = APP.info.canUpdate;
  toast({
    title: t('app.newVersion', { v: l.tag }), sub: t(auto ? 'app.newVersionHintAuto' : 'app.newVersionHint', { v: APP.info.version }), ms: 15000,
    actions: auto ? [{ label: t('app.updateNow'), icon: 'refresh', primary: true, run: updateApp }, { label: t('app.whatsNew'), icon: 'ext', run: () => openUrl(l.url) }]
      : [{ label: t('app.download'), icon: 'ext', primary: true, run: () => openUrl(l.url) }],
  });
}

// New version in one click (selfupdate.py): WTFTD downloads it, checks it, puts it in its own place and restarts. Its window
// closes and the new one's opens; on a refusal, the release page as before
async function updateApp() {
  const l = APP.info?.latest;
  if (!l || APP.updating) return;
  APP.updating = true;
  const working = toast({ title: t('app.updating', { v: l.tag }), sub: t('app.updatingHint'), ms: 0 });
  try {
    await api('app-update', {});
    working();
    toast({ title: t('app.updateRestart', { v: l.tag }), ms: 0 });
  } catch (e) {
    working();
    APP.updating = false;
    toast({ title: t('app.updateFailed'), sub: t('app.updateWhy.' + (e.data?.code || 'offline')), err: true, ms: 20000,
            actions: [{ label: t('app.download'), icon: 'ext', primary: true, run: () => openUrl(l.url) }] });
  }
}

function renderAppVersion() {
  const i = APP.info;
  $('#appVersion').textContent = i ? t('app.version', { v: i.version }) : '';
  $('#pillNewVersion')?.remove();
  if (i?.newer && i.latest) {
    $('#status').insertAdjacentHTML('afterbegin', `<button class="pill new" id="pillNewVersion" title="${esc(i.latest.name || i.latest.tag)}">
      ${icon('refresh', 'ic-sm')}${esc(t('app.newVersionShort', { v: i.latest.tag }))}</button>`);
    $('#pillNewVersion').addEventListener('click', () => (i.canUpdate ? updateApp() : openUrl(i.latest.url)));
  }
}

// the issue form on GitHub, filled in from here: the player reads it there and sends it with their own account.
// Field names = the ids in .github/ISSUE_TEMPLATE. No path, no name: issues are public
async function feedbackFields(kind, text) {
  const st = S.status || {}, title = text.split('\n')[0].slice(0, 70);
  if (kind === 'idea') return { title: `[Idea] ${title}`, idea: text };
  const out = { title: `[Bug] ${title}`, what: text, version: APP.info?.version || '',
                game: [st.data?.version, st.steam ? 'Steam' : 'standalone', st.dataSource, st.platform].filter(Boolean).join(', ') };
  if (S.cfg?.vehicle) {
    out.vehicle = I18N.unit(S.cfg.vehicle);
    const code = await encodeShare(shareVehicle(S.cfg, S.cfg.vehicle, out.vehicle)).catch(() => '');
    if (code.length < ISSUE_MAX_SHARE) out.share = code;
  }
  return out;
}

async function feedbackKind(kind) {
  $('#dlgFeedback').dataset.kind = kind;
  $$('#fbKind button').forEach(b => b.classList.toggle('active', b.dataset.kind === kind));
  $('#fbLabel').textContent = t(kind === 'bug' ? 'app.feedbackWhat' : 'app.feedbackIdea');
  const f = await feedbackFields(kind, '');
  const list = [f.version && t('app.version', { v: f.version }), f.game, f.vehicle, f.share && t('app.feedbackShare')].filter(Boolean);
  $('#fbAdded').textContent = list.length ? t('app.feedbackAdded', { list: list.join(' · ') }) : '';
}

function openFeedback(kind = 'bug') {
  feedbackKind(kind);
  $('#dlgFeedback').showModal();
  $('#fbText').focus();
}

async function sendFeedback() {
  const field = $('#fbText'), text = field.value.trim(), kind = $('#dlgFeedback').dataset.kind;
  field.setCustomValidity(text ? '' : t('app.feedbackEmpty'));  // a toast would stay behind the dialog
  if (!field.reportValidity()) return;
  const q = new URLSearchParams({ template: ISSUE_FORMS[kind], ...await feedbackFields(kind, text) });
  await openUrl(`${APP.info?.repo || 'https://github.com/StonewarP/WTFTD-War_Thunder_Full_Test_Drive'}/issues/new?${q}`);
  $('#fbText').value = '';
  $('#dlgFeedback').close();
}

function bindAppInfo() {
  $('#btnFeedback').addEventListener('click', () => openFeedback());
  $('#btnReportBug').addEventListener('click', () => openFeedback('bug'));
  $('#btnSuggest').addEventListener('click', () => openFeedback('idea'));
  $('#fbKind').addEventListener('click', e => { if (e.target.dataset.kind) feedbackKind(e.target.dataset.kind); });
  $('#fbSend').addEventListener('click', sendFeedback);
  $('#fbText').addEventListener('input', e => e.target.setCustomValidity(''));
  ['#btnSupport', '#btnSupport2'].forEach(s => $(s).addEventListener('click', () => openUrl(DONATE_URL)));
  setTimeout(checkAppVersion, 2500);
  setInterval(checkAppVersion, 6 * 3600 * 1000);
}
