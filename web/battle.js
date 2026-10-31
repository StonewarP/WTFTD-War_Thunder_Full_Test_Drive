/* WTFTD — Battle: the game's chat and battle log (its local API), asked for only what's new. Other players write the
   chat: everything goes through esc(). */
'use strict';

const BT = { chat: [], log: [], lastChat: 0, lastEvent: 0, lastDamage: 0, timer: 0, gone: false, filter: '' };
const BT_MAX = 2000;

function btLines(rows) {
  const f = BT.filter.toLowerCase();
  return rows.filter(r => !f || `${r.sender} ${r.text}`.toLowerCase().includes(f)).map(r => `<div class="bt-line${r.enemy ? ' enemy' : ''}">
      <time>${esc(flTime(r.time))}</time>${r.mode ? `<i>${esc(r.mode)}</i>` : ''}${r.sender ? `<b>${esc(r.sender)}</b>` : ''}<span>${esc(r.text)}</span></div>`).join('');
}

function btShow(el, rows) {
  const atEnd = el.scrollHeight - el.scrollTop - el.clientHeight < 40;  // reading older lines: stay there
  el.innerHTML = btLines(rows) || `<div class="muted bt-none">${esc(t('bt.empty'))}</div>`;
  if (atEnd) el.scrollTop = el.scrollHeight;
}
function btRender() {
  btShow($('#btChat'), BT.chat);
  btShow($('#btLog'), BT.log);
}

async function btPoll() {
  clearTimeout(BT.timer);
  if ($('#view-battle').classList.contains('hidden') && !$('#btSave').checked) return;  // saving goes on behind other tabs
  try {
    const st = await api(`battle/${BT.lastChat}/${BT.lastEvent}/${BT.lastDamage}`);
    if (!st.up) BT.gone = true;
    else if (BT.gone) {  // a game started again numbers everything from 1
      BT.gone = false;
      Object.assign(BT, { chat: [], log: [], lastChat: 0, lastEvent: 0, lastDamage: 0 });
    }
    $('#btState').textContent = t(st.up ? 'bt.on' : 'bt.off');
    if (st.chat.length || st.events.length || st.damage.length) {
      BT.lastChat = st.chat.at(-1)?.id ?? BT.lastChat;
      BT.lastEvent = st.events.at(-1)?.id ?? BT.lastEvent;
      BT.lastDamage = st.damage.at(-1)?.id ?? BT.lastDamage;
      BT.chat = BT.chat.concat(st.chat).slice(-BT_MAX);
      BT.log = BT.log.concat(st.events, st.damage).sort((a, b) => a.time - b.time).slice(-BT_MAX);
      btRender();
    }
  } catch { /* the app is closing */ }
  BT.timer = setTimeout(btPoll, 1500);
}

function openBattleView() {
  btRender();
  btPoll();
}

function bindBattle() {
  const size = store.get('battleSize', 14);
  const apply = v => document.documentElement.style.setProperty('--bt-size', `${v}px`);
  apply(size);
  $('#btSize').value = size;
  $('#btSize').addEventListener('input', e => { apply(e.target.value); store.set('battleSize', +e.target.value); });
  $('#btFilter').addEventListener('input', e => { BT.filter = e.target.value; btRender(); });
  $('#btClear').addEventListener('click', () => { BT.chat = []; BT.log = []; btRender(); });
  $('#btFolder').addEventListener('click', () => api('flight-logs-open', {}).catch(toastErr));
  $('#btSave').checked = S.status?.settings?.battleLog === true;
  $('#btSave').addEventListener('change', e => { api('settings', { battleLog: e.target.checked }).then(btPoll).catch(toastErr); });
  if ($('#btSave').checked) btPoll();
}
