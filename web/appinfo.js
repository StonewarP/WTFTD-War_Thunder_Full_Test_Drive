/* WTFTD — app version: "new version available" alert (GitHub releases), bug report / suggestion links. */
'use strict';

const APP = { info: null };
const ISSUE_FORMS = { bug: 'bug_report.yml', idea: 'feature_request.yml' };
const DONATE_URL = 'https://ko-fi.com/stonewarp';

const openUrl = url => api('open-url', { url }).catch(toastErr);

async function checkAppVersion() {
  try { APP.info = await api('app-version'); } catch { return; }
  renderAppVersion();
  const l = APP.info.latest;
  if (!APP.info.newer || !l) return;
  if (store.get('seenRelease', '') === l.tag) return;  // tell once per version, the pill stays
  store.set('seenRelease', l.tag);
  toast({
    title: t('app.newVersion', { v: l.tag }), sub: t('app.newVersionHint', { v: APP.info.version }), ms: 15000,
    actions: [{ label: t('app.download'), icon: 'ext', primary: true, run: () => openUrl(l.url) }],
  });
}

function renderAppVersion() {
  const i = APP.info;
  $('#appVersion').textContent = i ? t('app.version', { v: i.version }) : '';
  $('#pillNewVersion')?.remove();
  if (i?.newer && i.latest) {
    $('#status').insertAdjacentHTML('afterbegin', `<button class="pill new" id="pillNewVersion" title="${esc(i.latest.name || i.latest.tag)}">
      ${icon('refresh', 'ic-sm')}${esc(t('app.newVersionShort', { v: i.latest.tag }))}</button>`);
    $('#pillNewVersion').addEventListener('click', () => openUrl(i.latest.url));
  }
}

function bindAppInfo() {
  $('#btnReportBug').addEventListener('click', () => openUrl(`${APP.info?.repo || 'https://github.com/StonewarP/WTFTD'}/issues/new?template=${ISSUE_FORMS.bug}`));
  $('#btnSuggest').addEventListener('click', () => openUrl(`${APP.info?.repo || 'https://github.com/StonewarP/WTFTD'}/issues/new?template=${ISSUE_FORMS.idea}`));
  ['#btnSupport', '#btnSupport2'].forEach(s => $(s).addEventListener('click', () => openUrl(DONATE_URL)));
  setTimeout(checkAppVersion, 2500);
  setInterval(checkAppVersion, 6 * 3600 * 1000);
}
