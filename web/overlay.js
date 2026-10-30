/* WTFTD — My overlay: what the in-flight window shows and how it looks, and the alarms' thresholds and sounds.
   Kept in settings.json "overlay" (checked by alarms.clean). Every change is saved at once and the server sends the
   lines back filled with sample values, so the preview here is what the window draws. */
'use strict';

const OV = { cfg: null, screen: [3840, 2160], lines: [], input: null, timer: 0 };
const OV_WHEN = ['always', 'gear', 'flaps', 'airbrake', 'alarm', 'log'];
const OV_ALARMS = { airframe: 1540, gear: 700, flaps: 600 };  // the example under each threshold, km/h
const OV_FONTS = ['Consolas', 'Cascadia Mono', 'Courier New', 'Lucida Console', 'Segoe UI', 'Bahnschrift', 'Arial', 'Tahoma', 'Verdana', 'Impact'];
const OV_VALUES = {
  speed: ['ias', 'tas', 'mach', 'hspeed', 'accel', 'sep', 'vne', 'mne', 'margin', 'airframe_pct', 'swept'],
  gearflaps: ['gear', 'gear_max', 'gear_pct', 'flaps', 'flaps_max', 'flaps_pct', 'airbrake'],
  flight: ['alt', 'vy', 'aoa', 'aos', 'g', 'g_max', 'turn', 'turn_rate', 'turn_radius', 'roll', 'pitch', 'bank', 'heading'],
  engine: ['throttle', 'rpm', 'thrust', 'thrust_total', 'twr', 'mass', 'power', 'oil', 'fuel', 'fuel_max', 'fuel_pct', 'burn', 'fuel_time', 'range'],
};

function ovShow(st) {
  OV.lines = st.lines;
  OV.screen = st.screen;
  ovDraw();
}

// saved a moment after the last change, not at every key
function ovSave() {
  clearTimeout(OV.timer);
  OV.timer = setTimeout(ovFlush, 150);
}
async function ovFlush(extra = {}) {
  clearTimeout(OV.timer);
  try { ovShow(await api('overlay', { cfg: OV.cfg, ...extra })); } catch (e) { toastErr(e); }
}

function ovDraw() {
  const box = $('#ovScreen'), text = $('#ovText'), c = OV.cfg;
  box.style.aspectRatio = `${OV.screen[0]} / ${OV.screen[1]}`;
  const k = box.clientWidth / OV.screen[0];
  Object.assign(text.style, { left: `${c.x * k}px`, top: `${c.y * k}px`, opacity: c.opacity / 100,
                              fontFamily: `"${c.font}", monospace`, fontWeight: c.bold ? 700 : 400 });
  const html = scale => OV.lines.map(([s, color, size]) => `<div style="color:${esc(color)};font-size:${size * scale}px">${esc(s) || '&nbsp;'}</div>`).join('');
  text.innerHTML = html(k);
  // the same text big enough to read: the size of the letters compared with each other, not on the screen
  const zoom = $('#ovZoom');
  Object.assign(zoom.style, { fontFamily: text.style.fontFamily, fontWeight: text.style.fontWeight });
  zoom.innerHTML = html(22 / Math.max(c.size, 1));
}

function ovRenderLines() {
  const opt = (v, label, on) => `<option value="${esc(v)}"${v === on ? ' selected' : ''}>${esc(label)}</option>`;
  $('#ovLines').innerHTML = OV.cfg.lines.map((l, i) => `<div class="ov-line" data-i="${i}">
      <div class="ov-move"><button class="icon-btn" data-ovmove="-1"${i ? '' : ' disabled'} title="${esc(t('ov.up'))}">▲</button><button class="icon-btn" data-ovmove="1"${i < OV.cfg.lines.length - 1 ? '' : ' disabled'} title="${esc(t('ov.down'))}">▼</button></div>
      <input type="text" class="ov-tpl" data-ol="text" value="${esc(l.text)}" maxlength="120" spellcheck="false">
      <label class="ov-mini"><span>${esc(t('ov.when'))}</span><select data-ol="when">${OV_WHEN.map(w => opt(w, t('ov.when.' + w), l.when)).join('')}</select></label>
      <label class="ov-mini"><span>${esc(t('ov.redWith'))}</span><select data-ol="alarm">${opt('', t('ov.redNone'), l.alarm)}${Object.keys(OV_ALARMS).map(a => opt(a, t('ov.alarm.' + a), l.alarm)).join('')}</select></label>
      <label class="ov-mini ov-num"><span>${esc(t('ov.lineSize'))}</span><input type="number" data-ol="size" min="0" max="400" value="${l.size || ''}" placeholder="${esc(OV.cfg.size)}"></label>
      <label class="ov-mini ov-swatch"><span>${esc(t('ov.lineColor'))}</span><input type="color" data-ol="color" value="${esc(l.color || OV.cfg.color)}"></label>
      <button class="icon-btn ov-clear${l.color ? '' : ' hidden'}" data-ovnocolor title="${esc(t('ov.noColor'))}">${icon('x', 'ic-sm')}</button>
      <button class="icon-btn btn-danger" data-ovdel title="${esc(t('action.delete'))}">${icon('trash')}</button></div>`).join('');
}

function ovRenderAlarms() {
  $('#ovAlarms').innerHTML = Object.entries(OV_ALARMS).map(([n, limit]) => {
    const a = OV.cfg.alarms[n];
    return `<div class="ov-alarm" data-a="${n}">
      <div class="row-between"><label class="switch"><input type="checkbox" data-oa="on"${a.on ? ' checked' : ''}><span class="sw"></span><b>${esc(t('ov.alarm.' + n))}</b></label>
        <button class="btn btn-sm" data-ovtest="${n}">${esc(t('ov.test'))}</button></div>
      <div class="ov-alarm-row">
        <label class="ov-mini"><span>${esc(t('ov.at'))}</span><input type="number" data-oa="at" min="1" max="200" value="${a.at}"></label>
        <label class="ov-mini"><span>${esc(t('ov.pitch'))}</span><input type="number" data-oa="hz" min="37" max="32767" step="50" value="${a.hz}"></label>
        <label class="ov-mini"><span>${esc(t('ov.length'))}</span><input type="number" data-oa="ms" min="10" max="2000" step="10" value="${a.ms}"></label>
      </div>
      <small class="muted" data-oex="${limit}"></small></div>`;
  }).join('');
  ovExamples();
}
function ovExamples() {
  $$('#ovAlarms [data-oex]').forEach(el => {
    const limit = +el.dataset.oex, at = OV.cfg.alarms[el.closest('[data-a]').dataset.a].at;
    el.textContent = t('ov.example', { speed: Math.round(limit * at / 100), limit });
  });
}

function ovRender(st) {
  OV.cfg = st.cfg;
  $('#ovEnabled').checked = st.enabled;
  $('#ovOnScreen').checked = st.onScreen;
  $$('#view-overlay [data-ov]').forEach(el => {
    if (el.type === 'checkbox') el.checked = OV.cfg[el.dataset.ov];
    else el.value = OV.cfg[el.dataset.ov];
  });
  $$('#view-overlay [data-ovkey]').forEach(el => { el.value = OV.cfg[el.dataset.ovkey + 'Name']; });
  ovRenderLines();
  ovRenderAlarms();
  ovShow(st);
}

async function openOverlayView() {
  try { ovRender(await api('overlay')); } catch (e) { toastErr(e); }
}

// leaving the tab takes the sample off the screen
function leaveOverlayView() {
  if ($('#ovOnScreen').checked) {
    $('#ovOnScreen').checked = false;
    api('overlay-preview', { on: false }).catch(() => {});
  }
}

function ovInsert(name) {
  const edited = OV.input?.isConnected ? OV.input : null, input = edited || $$('#ovLines .ov-tpl').pop();
  if (!input) return;
  input.setRangeText(`{${name}}`, edited ? input.selectionStart : input.value.length, edited ? input.selectionEnd : input.value.length, 'end');
  input.focus();
  input.dispatchEvent(new Event('input', { bubbles: true }));
}

function ovDrag() {
  const box = $('#ovScreen'), text = $('#ovText');
  text.addEventListener('pointerdown', e => {
    e.preventDefault();
    text.setPointerCapture(e.pointerId);
    const k = box.clientWidth / OV.screen[0], start = { x: OV.cfg.x, y: OV.cfg.y, px: e.clientX, py: e.clientY };
    const move = ev => {
      OV.cfg.x = Math.round(start.x + (ev.clientX - start.px) / k);
      OV.cfg.y = Math.round(start.y + (ev.clientY - start.py) / k);
      $('#ovX').value = OV.cfg.x;
      $('#ovY').value = OV.cfg.y;
      ovDraw();
      ovSave();
    };
    text.addEventListener('pointermove', move);
    text.addEventListener('pointerup', () => text.removeEventListener('pointermove', move), { once: true });
  });
}

function bindOverlay() {
  $('[data-view="overlay"]').classList.toggle('hidden', !S.status?.alarms);  // Windows only
  $('#ovFonts').innerHTML = OV_FONTS.map(f => `<option value="${esc(f)}">`).join('');
  $('#ovValues').innerHTML = Object.entries(OV_VALUES).map(([group, names]) => `<div class="ov-group"><b>${esc(t('ov.g.' + group))}</b>${names.map(n => `<button class="chip ov-chip" data-ovv="${n}" title="{${n}}">${esc(t('ov.v.' + n))}</button>`).join('')}</div>`).join('');
  ovDrag();
  const view = $('#view-overlay');
  view.addEventListener('focusin', e => { if (e.target.classList.contains('ov-tpl')) OV.input = e.target; });
  view.addEventListener('input', e => {
    const el = e.target, value = el.type === 'checkbox' ? el.checked : el.type === 'number' ? parseInt(el.value, 10) : el.value;
    if (el.dataset.ov) {
      if (el.type === 'number' && Number.isNaN(value)) return;
      OV.cfg[el.dataset.ov] = value;
      if (el.dataset.ov === 'size' || el.dataset.ov === 'color') ovRenderLines();  // what lines without their own show
      ovDraw();
    } else if (el.dataset.ol) {
      const line = OV.cfg.lines[+el.closest('.ov-line').dataset.i];
      line[el.dataset.ol] = el.dataset.ol === 'size' ? value || 0 : value;
      if (el.dataset.ol === 'color') $('.ov-clear', el.closest('.ov-line')).classList.remove('hidden');
    } else if (el.dataset.oa) {
      if (el.type === 'number' && Number.isNaN(value)) return;
      OV.cfg.alarms[el.closest('[data-a]').dataset.a][el.dataset.oa] = value;
      ovExamples();
    } else return;
    ovSave();
  });
  view.addEventListener('click', async e => {
    const b = e.target.closest('button');
    if (!b) return;
    const row = b.closest('.ov-line'), i = row ? +row.dataset.i : -1, lines = OV.cfg.lines;
    if (b.dataset.ovv) return ovInsert(b.dataset.ovv);
    if (b.dataset.ovtest) { await ovFlush(); return api('overlay-test', { alarm: b.dataset.ovtest }).catch(toastErr); }
    if (b.dataset.ovmove) { const to = i + +b.dataset.ovmove; [lines[i], lines[to]] = [lines[to], lines[i]]; }
    else if ('ovdel' in b.dataset) lines.splice(i, 1);
    else if ('ovnocolor' in b.dataset) lines[i].color = '';
    else return;
    ovRenderLines();
    ovSave();
  });
  $('#ovAddLine').addEventListener('click', () => {
    OV.cfg.lines.push({ text: '', when: 'always', alarm: '', color: '', size: 0 });
    ovRenderLines();
    $$('#ovLines .ov-tpl').pop().focus();
    ovSave();
  });
  $('#ovEnabled').addEventListener('change', e => ovFlush({ enabled: e.target.checked }));
  $('#ovOnScreen').addEventListener('change', e => api('overlay-preview', { on: e.target.checked }).catch(toastErr));
  $('#ovReset').addEventListener('click', async () => {
    const before = OV.cfg;
    try { ovRender(await api('overlay', { reset: true })); } catch (e) { return toastErr(e); }
    toast({ title: t('ov.resetDone'), actions: [{ label: t('ov.undo'), run: async () => ovRender(await api('overlay', { cfg: before })) }] });
  });
  $$('#view-overlay [data-ovkey]').forEach(field => field.addEventListener('keydown', e => {
    e.preventDefault();
    if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;
    const mods = [[e.ctrlKey, 17, 'Ctrl'], [e.shiftKey, 16, 'Shift'], [e.altKey, 18, 'Alt']].filter(m => m[0]);
    const none = e.key === 'Escape' || e.key === 'Backspace', key = field.dataset.ovkey;
    OV.cfg[key] = none ? [] : [...mods.map(m => m[1]), e.keyCode];
    OV.cfg[key + 'Name'] = none ? '' : [...mods.map(m => m[2]), e.code.replace(/^(Key|Digit)/, '')].join('+');
    field.value = OV.cfg[key + 'Name'];
    ovSave();
  }));
  addEventListener('resize', () => { if (OV.cfg && !$('#view-overlay').classList.contains('hidden')) ovDraw(); });
}
