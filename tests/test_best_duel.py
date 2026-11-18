"""Best vehicles in node: the new stats as the app reads and shows them (web/stats.js, web/compare.js), the duel
engine that ranks the vehicles (web/duel.js) and the BRs the page lists from it (web/best.js)."""
import json
import math
import shutil
import subprocess
import unittest

from wtftd.paths import WEB

# stats.js and compare.js with the rest of the page stubbed: an element per selector, labels as their keys
APP = r"""
const fs = require('fs'), vm = require('vm');
const els = {};
globalThis.$ = sel => (els[sel] ||= { open: false, innerHTML: '', on: {}, classList: { toggle() {} },
  showModal() { this.open = true; }, close() { this.open = false; }, addEventListener(type, fn) { this.on[type] = fn; } });
globalThis.document = { addEventListener() {} };
globalThis.store = { get: (k, d) => d, set() {} };
globalThis.S = { f: { brMode: 1 }, details: new Map(), byId: new Map() };
globalThis.HG = { owned: new Set() };
globalThis.t = k => k;
globalThis.I18N = { num: String, unit: String, unitFull: String };
globalThis.esc = s => String(s ?? '');
globalThis.icon = globalThis.unitImgTag = globalThis.flagHTML = globalThis.bnCompareRows = () => '';
globalThis.className = String;
globalThis.fmtBR = b => b.toFixed(1);
globalThis.ROMAN = ['', 'I'];
globalThis.getData = async () => ({});
globalThis.vehicleDetails = async () => ({});
let refreshed = 0;
globalThis.bvRefresh = () => { refreshed++; };
for (const f of process.argv.slice(1)) vm.runInThisContext(fs.readFileSync(f, 'utf8'));

(async () => {
  const out = {};
  const pen = { s: { pen: [200, 180, 150] }, su: { pen: [150, 140, 100] } };
  S.upg = false;
  out.stock = [statAt(pen, 'pen'), statAt({ s: pen.s }, 'pen'), statVal(pen, 'pen')];
  S.upg = true;
  out.full = statAt(pen, 'pen');
  out.fmt = [fmtStat('rf', 2), fmtStat('irq', 0), fmtStat('irq', null), fmtStat('pen', [180, 160, 120]), fmtStat('fg', 1.76)];
  out.dep = [fmtStat('dep', 8), fmtStat('dep', 4.5), fmtStat('dep', 10)];

  const tank = id => ({ id, c: 'ground', n: 'usa', k: 'tank', r: 1, br: [1, 1, 1], s: { spd: 40, pen: [180, 160, 120], dep: 8 }, su: { pen: [150, 140, 100] } });
  out.panel = statsBlockHTML(tank('x'));
  S.byId = new Map(['a', 'x', 'y'].map(id => [id, tank(id)]));
  S.compare = ['a'];
  bindCompare();
  const table = () => $('#cmpTable').innerHTML;
  const shown = () => [...table().matchAll(/data-ctopen="([^"]*)"/g)].map(m => m[1]);
  await openCompare(['x', 'y']);
  out.pair = { shown: shown(), tray: [...S.compare], open: $('#dlgCompare').open, html: table() };
  setUpgrade(false);
  out.upg = { shown: shown(), refreshed };
  $('#dlgCompare').on.click({ target: { closest: () => ({ dataset: { ctrm: 'x' } }) } });  // the dialog's remove button
  out.removed = { shown: shown(), tray: [...S.compare] };
  $('#dlgCompare').close();
  await openCompare();
  out.trayShown = shown();

  // su null: the stock vehicle has no value for it (no unguided round, no shell that penetrates): unknown, not the upgraded one
  const z = { ...tank('z'), s: { vel: 1430, pen: [180, 160, 120] }, su: { vel: null, pen: null } }, w = { ...tank('w'), s: { vel: 1000, pen: [150, 140, 100] }, su: null };
  S.byId.set('z', z).set('w', w);
  S.upg = false;
  S.f.sort = 's:vel';
  await openCompare(['z', 'w']);
  out.unknown = { stock: [statAt(z, 'vel'), statAt(z, 'pen'), statVal(z, 'pen')], panel: statsBlockHTML(z), card: cardStatHTML(z), cmp: table() };
  S.upg = true;
  renderCompareTable();
  out.unknown.full = [statAt(z, 'vel'), statAt(z, 'pen')];
  out.unknown.cmpFull = table();

  // a per-mode stat without a value in the chosen mode (ships at SB: rep, slm [x, y, null]), stock or upgraded
  const ship = id => ({ id, c: 'ship', n: 'uk', k: 'destroyer', r: 1, br: [3, 3, 3], s: { spd: 60, rep: [1553, 2433, null], slm: [100, 240, null] }, su: { rep: [1194, 1870, null] } });
  S.byId.set('s1', ship('s1')).set('s2', ship('s2')).set('r', { ...tank('r'), s: { spd: 40, rep: [500, 900, 1200], slm: [100, 200, 300] } });
  out.modes = {};
  for (const upg of [false, true]) {
    S.upg = upg;
    S.f.brMode = 2;
    await openCompare(['s1', 's2']);
    const ships = table();
    await openCompare(['s1', 'r']);
    const mixed = table();
    S.f.brMode = 1;
    renderCompareTable();
    out.modes[upg ? 'full' : 'stock'] = { ships, mixed, rb: table() };
  }
  console.log(JSON.stringify(out));
})();
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class StatsInTheApp(unittest.TestCase):
    got = None

    @classmethod
    def setUpClass(cls):
        run = subprocess.run(["node", "-e", APP, str(WEB / "stats.js"), str(WEB / "compare.js")], capture_output=True, encoding="utf-8", check=True)
        cls.got = json.loads(run.stdout)

    def test_statat_stock_array(self):
        self.assertEqual(self.got["stock"][0], [150, 140, 100])
        self.assertEqual(self.got["stock"][1], [200, 180, 150])  # no stock values: the vehicle's own
        self.assertEqual(self.got["stock"][2], 150)  # one number to sort and filter by: at 500 m
        self.assertEqual(self.got["full"], [200, 180, 150])

    def test_fmtstat_value_labels(self):
        self.assertEqual(self.got["fmt"][0], "stat.rf.2")
        self.assertEqual(self.got["fmt"][1], self.got["fmt"][2])  # a stock vehicle without it: no value, not "stat.irq.0"
        self.assertEqual(self.got["fmt"][3:], ["180 / 160 / 120 mm", "1.8 kg/s"])

    def test_fmtstat_bare_degree_sign(self):
        # the app writes the degree sign right after the number; one decimal (T-90A 4.5), none on a whole value
        self.assertEqual(self.got["dep"], ["8°", "4.5°", "10°"])

    def test_shown_once_with_their_own_hint(self):
        panel, html = self.got["panel"], self.got["pair"]["html"]
        self.assertIn('title="stat.penHint"><span>stat.pen</span>', panel)
        self.assertIn("<th>stat.pen<small>stat.penHint</small></th>", html)
        for text in (panel, html):  # the gun depression already has its own row in the comparison
            self.assertNotIn("stat.dep", text)
        self.assertLess(html.index("compare.sec.fire"), html.index("<th>stat.pen"))

    def test_compare_temporary_list(self):
        self.assertEqual(self.got["pair"]["shown"], ["x", "y"])
        self.assertTrue(self.got["pair"]["open"])
        self.assertEqual(self.got["pair"]["tray"], ["a"])
        self.assertEqual(self.got["removed"], {"shown": ["y"], "tray": ["a"]})
        self.assertEqual(self.got["trayShown"], ["a"])  # the tray's own button: the tray again

    def test_upgrade_switch_refreshes_the_page(self):
        self.assertEqual(self.got["upg"], {"shown": ["x", "y"], "refreshed": 1})

    def test_statat_stock_null_is_unknown(self):
        u = self.got["unknown"]
        self.assertEqual(u["stock"], [None, None, None])  # a scalar or a whole triple: not the upgraded value
        self.assertEqual(u["full"], [1430, [180, 160, 120]])

    def test_null_stock_value_shows_the_missing_mark(self):
        u, dash, to = self.got["unknown"], chr(0x2014), chr(0x2192)  # the app's no-value mark; the tooltip's arrow
        self.assertIn(f'<div class="vstat upg-chg" title="upg.stock: {dash} {to} upg.full: 1430 m/s"><span>stat.vel</span><b>{dash}</b></div>', u["panel"])
        self.assertIn(f"<span>stat.pen</span><b>{dash}</b>", u["panel"])
        self.assertEqual(u["card"], f'<span class="card-stat" title="stat.vel">{dash}</span>')  # the Vehicles list
        for th in ("stat.vel</th>", "stat.pen<small>stat.penHint</small></th>"):  # the dialog's mark for a vehicle without it
            self.assertIn(f'{th}<td><span class="muted">{dash}</span></td>', u["cmp"])
        self.assertIn('<td class="best upg-chg">1430 m/s</td>', u["cmpFull"])  # upgraded: marked as changed by the modules

    def test_mode_stat_without_a_value_in_the_mode(self):
        dash = chr(0x2014)
        for state, rb in (("stock", 1870), ("full", 2433)):
            m = self.got["modes"][state]
            for k in ("stat.rep", "stat.slm"):  # no row when no vehicle has one, the dialog's own mark beside one that has
                self.assertNotIn(k, m["ships"], state)
                self.assertIn(f'<th>{k} · filters.mode.sb</th><td><span class="muted">{dash}</span></td>', m["mixed"], state)
            self.assertIn(f'<th>stat.rep · filters.mode.rb</th><td class="upg-chg">{rb} SL</td>', m["rb"], state)


# web/duel.js alone with made-up vehicles; a number that is not finite is marked before JSON turns it into null
DUEL = r"""
const fs = require('fs'), vm = require('vm');
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const foe = (type, id, i = 0) => BV_STYLES[type].find(s => s.id === id).foes[i];
const RB = { mode: 1, stock: false };
const air = (id, s, more) => ({ id, c: 'air', k: 'fighter', ro: ['fighter'], br: [4, 4, 4], s, ...more });
const heli = (id, s) => ({ id, c: 'heli', k: 'helicopter', br: [9, 9, 9], s });
const tank = (id, s, more) => ({ id, c: 'ground', k: 'tank', ro: ['medium_tank'], br: [6, 6, 6], s, ...more });
const spaa = (id, s, more) => ({ id, c: 'ground', k: 'SPAA', ro: ['spaa'], br: [9, 9, 9], s, ...more });
const boat = (id, s) => ({ id, c: 'boat', k: 'torpedo_boat', ro: ['boat', 'torpedo_boat'], br: [3, 3, 3], s });
const term = (res, k) => res.terms.find(x => x.k === k) || null;
const ids = rows => rows.map(r => r.v.id);
const out = {};

out.terms = { turn: bvTerm('turn', 18, 20.5), even: bvTerm('turn', 18, 18.5), rel: bvTerm('rel', 5, 7),
  fg: [bvTerm('fg', 3, 2), bvTerm('fg', 2, 3), bvTerm('fg', 2.5, 2), bvTerm('fg', 2, 2.5)],
  spd: [bvTerm('spd', 600, 620, 'prop'), bvTerm('spd', 600, 620, 'jet'), bvTerm('spd', 600, 640, 'prop')] };
out.caps = { none: bvTerm('rad', 0, 0), lacks: bvTerm('rad', 0, 54), one: bvTerm('ir', 1, 0), absent: [bvVal({ s: {} }, 'rad'), bvVal({ s: {} }, 'spd')] };

const turnFoe = foe('air', 'turn'), fighter = s => ({ turn: 18, wl: 150, pw: 400, fg: 3, climb: 15, roll: 100, spd: 500, ...s });
// of the 4.8 compared (flares need an IR missile on either side), unknown: turn and roll 1.8; turn, roll and spd 2.0; turn and wl 2.5
out.cover = [{ wl: 150, fg: 3, climb: 15, spd: 500, pw: 400 }, { wl: 150, fg: 3, climb: 15, pw: 400 }, { fg: 3, climb: 15, spd: 500, roll: 100, pw: 400 }]
  .map(s => bvDuel(air('a', fighter()), air('b', s), turnFoe, RB).v);

const pick = terms => ({ is: () => true, terms }), radar = air('r', { spd: 500, rad: 50 }), plain = air('p', { spd: 500 });
out.verdicts = [bvDuel(radar, plain, pick({ rad: 1, spd: 4 }), RB), bvDuel(radar, plain, pick({ rad: 19, spd: 81 }), RB),
  bvDuel(plain, radar, pick({ rad: 1, spd: 4 }), RB), bvDuel(radar, plain, pick({ rad: .6, spd: 2.4 }), RB),
  bvDuel(plain, radar, pick({ rad: .6, spd: 2.4 }), RB)].map(r => [r.v, r.D]);

const gate = r => [r.v, r.gate];
const refuse = (a, b) => gate(bvDuel(air('a', fighter(a)), air('b', fighter({ turn: 22, wl: 200, pw: 300, climb: 17.4, spd: 525, ...b })), turnFoe, RB));
const above = (a, b) => gate(bvDuel(air('a', { spd: 600, climb: a, fg: 6, roll: 120, vne: 750, pw: 400, ceil: 10000, turn: 20, wl: 180 }),
  air('b', { spd: 650, climb: b, fg: 2, roll: 90, vne: 650, pw: 400, ceil: 10000, turn: 20, wl: 180 }), foe('air', 'bnz'), RB));
const outgun = (pen, br = 6, brB = br) => gate(bvDuel(tank('a', { pen: [pen, 180, 150], rel: 3, trav: 30, cal: 100, stab: 2, crew: 5, pw: 20, rev: 20 }, { br: [br, br, br] }),
  tank('b', { pen: [450, 430, 400], rel: 8, trav: 10, cal: 120, crew: 4, pw: 15, rev: 5 }, { br: [brB, brB, brB] }), foe('ground', 'brawl'), RB));
out.gates = {
  refuse: refuse({}, {}), stays: refuse({}, { spd: 520 }), above: above(15, 18), outgun: outgun(200), armor: [outgun(200, 9), outgun(200, 8.3, 8.7), outgun(200, 8.7, 8.3)],
  exact: [refuse({ climb: 12 }, { climb: 13.8 }), refuse({ spd: 480 }, { spd: 501.6 }), above(20, 21.6), outgun(225)],
  listed: Object.fromEntries(Object.values(BV_STYLES).flat().map(s => [s.id, s.foes.map(f => f.gates ?? null)])),
};

const armored = (id, br) => tank(id, { pen: [200, 180, 150], armH: [100, 80, 40], armT: [120, 60, 50], rel: 5, trav: 20, cal: 100, crew: 4, pw: 15, rev: 10, spd: 50 }, { br: [br, br, br] });
const has = (a, b, f, k) => !!term(bvDuel(a, b, foe('ground', f), RB), k);
out.armor = [has(armored('a', 8.3), armored('b', 8.3), 'brawl', 'front'), has(armored('a', 8.7), armored('b', 8.3), 'brawl', 'front'),
  has(armored('a', 8.3), armored('b', 8.7), 'brawl', 'front'), has(armored('a', 8.3), armored('b', 8.3), 'flank', 'side'),
  has(armored('a', 8.3), armored('b', 8.7), 'flank', 'side')];

const jet = (id, spd) => air(id, { spd, tw: .8, turn: 25, roll: 100 }), prop = (id, spd) => air(id, { spd, pw: 400, turn: 25, roll: 100 });
const spdT = (a, b) => term(bvDuel(a, b, turnFoe, RB), 'spd').t, hasPwr = (a, b) => !!term(bvDuel(a, b, turnFoe, RB), 'pwr');
out.kinds = { spd: [spdT(jet('a', 600), jet('b', 620)), spdT(prop('a', 600), prop('b', 620)), spdT(jet('a', 600), prop('b', 620))],
  pwr: [hasPwr(jet('a', 600), jet('b', 620)), hasPwr(prop('a', 600), prop('b', 620)), hasPwr(jet('a', 600), prop('b', 620))],
  skip: bvTerm('pwr', 400, .5, 'mixed'), mixed: bvDuel(jet('a', 600), prop('b', 620), turnFoe, RB).v,
  rel: [has(armored('a', 6), armored('b', 6), 'brawl', 'rel'), has(tank('a', { rel: .2, auto: 1 }), armored('b', 6), 'brawl', 'rel')],
  turret: term(bvDuel(armored('a', 8.3), armored('b', 8.3), foe('ground', 'snipe'), RB), 'front').a };

const hatgm = foe('heli', 'hatgm'), reach = r => { const x = term(r, 'reach'); return [x.t, x.a, x.b]; };
const side = term(bvDuel(tank('a', { pen: [160, 150, 120] }), tank('b', { armH: [100, 80, 40], armT: [120, 60, 50] }), foe('ground', 'flank'), RB), 'side');
out.pair = { missile: reach(bvDuel(heli('h', { atg: 4, atr: 8000 }), spaa('s', { sam: 5500 }), hatgm, RB)),
  guns: reach(bvDuel(heli('h', { atg: 2, atr: 2000 }), spaa('g', { aab: 3 }), hatgm, RB)), side: [side.t, side.a, side.b],
  wide: [reach(bvDuel(heli('h', { atg: 2, atr: 3750 }), spaa('g', { aab: 3 }), hatgm, RB))[0], bvDuel(heli('h', { rkt: 300 }), spaa('t', { sam: 3200 }), foe('heli', 'hrocket'), RB).v],
  kill: [bvVal(tank('m', { pen: [75, 70, 60], atp: 500, atr: 4000 }), 'kill1000'), bvVal(tank('m', { pen: [75, 70, 60], atp: 500, atr: 1500 }), 'kill2000')] };

const casV = [air('x', { pay: 1000, spd: 500 }, { k: 'assault', br: [10.3, 10.3, 10.3], bt: [9.7, 9.7, 9.7] }), spaa('s', { sam: 6000 }),
  air('f', { spd: 600 }, { br: [8, 8, 8], bt: [10.7, 10.7, 10.7] }), air('g', { spd: 600 }, { br: [9.7, 9.7, 9.7], bt: [12, 12, 12] })];
const casCtx = br => ({ vehicles: casV, type: 'air', style: 'cas', mode: 1, br, stock: false, onlyStyle: true });
const cas = bvRank(casCtx(9.7));
out.cas = { at: ids(cas), n: cas[0]?.n, other: ids(bvRank(casCtx(10.3))), met: cas[0] ? bvMatchups(cas[0], casCtx(9.7)).map(x => x.o.id).sort() : [] };
// one SPAA beaten, three fighters lost to
const casB = (id, more) => air(id, { spd: 700, climb: 20, turn: 18, roll: 100 }, { br: [9.7, 9.7, 9.7], bt: [9.7, 9.7, 9.7], ...more });
out.cas.halves = bvRank({ vehicles: [casB('x', { k: 'assault', s: { pay: 1000, atg: 2, atr: 8000, spd: 500, climb: 10, turn: 20, roll: 80 } }), spaa('s', { aab: 3 }),
  casB('f1'), casB('f2'), casB('f3')], type: 'air', style: 'cas', mode: 1, br: 9.7, stock: false, onlyStyle: true }).map(r => [r.v.id, r.w, r.e, r.l, r.net]);
// a's stock carries nothing
const casS = [air('a', { pay: 1000, spd: 500 }, { br: [5, 5, 5], bt: [5, 5, 5], su: { pay: 0 } }), air('b', { pay: 600, spd: 500 }, { br: [5, 5, 5], bt: [5, 5, 5] }),
  air('c', { pay: 400, spd: 500 }, { k: 'assault', br: [5, 5, 5], bt: [5, 5, 5] })];
const casRows = stock => bvRank({ vehicles: casS, type: 'air', style: 'cas', mode: 1, br: 5, stock, onlyStyle: true }).map(r => [r.v.id, r.mission]).sort();
out.cas.stock = { stock: casRows(true), upgraded: casRows(false), cand: [true, false, undefined].map(s => bvStyleOf('air', 'cas').cand(casS[0], s)) };

out.window = [bvInWindow(6.7, 5.7), bvInWindow(6.7, 7.7), bvInWindow(6.7, 5.3), bvInWindow(6.7, 8.0), bvSteps(7.7, 6.7),
  bvBr({ br: [1, 2, 3], bt: [1, 2.3, 3] }, 1, 'bt'), bvBr({ br: [1, 2, 3] }, 2, 'bt'), bvBr({ br: null }, 1)];

const records = [{ id: 'ok' }, { id: 'gone', ra: 5 }, { id: 'hid', h: 1 }, { id: 'npc', ra: 6 }, { id: 'pack', mod: 1 },
  ...['x_killstreak', 'nt_x', 'uav_x', 'ucav_x', 'germ_panther_II_tutorial', 'ussr_t_80u_race', 'f_4e_event', 'f_16c_block_50_missile_test',
    'ussr_t_72b3_arena', 'us_m551_football', 'ussr_t_80u_yt_cup_2019', 'us_sl_amraam_launcher', 'us_m8_scott_snowball', 'ussr_t_72b3_arena_m'].map(id => ({ id }))];
out.pool = [bvPool(records).map(v => v.id), bvPool(records, { removed: false }).map(v => v.id)];

const bomber = (id, pay, s) => air(id, { pay, spd: 450, ceil: 8000, def: 3, climb: 8, crew: 6, ...s }, { k: 'bomber', br: [5, 5, 5] });
const bombs = bvRank({ vehicles: [bomber('b1', 100), bomber('b2', 200, { spd: 550 }), bomber('b3', 200), air('f', { spd: 500, ceil: 9000, climb: 15, crew: 1 }, { br: [5, 5, 5] })],
  type: 'air', style: 'bomber', mode: 1, br: 5, stock: false, onlyStyle: true });
out.mission = { m: BV_STYLES.air.find(s => s.id === 'bomber').m, rows: bombs.map(r => ({ id: r.v.id, score: r.score, net: r.net, mission: r.mission, w: r.w, e: r.e, l: r.l })) };

// y and x both beat the bomber (the same score), x by more; z loses
const hunt = bvRank({ vehicles: [air('y', { spd: 520, climb: 12, ceil: 9000, fg: 3 }), air('x', { spd: 600, climb: 20, ceil: 11000, fg: 3 }),
  air('z', { spd: 380, climb: 6, ceil: 6000, fg: 3 }), air('b', { spd: 450, climb: 8, ceil: 8000 }, { k: 'bomber' })],
  type: 'air', style: 'hunter', mode: 1, br: 4, stock: false, onlyStyle: true });
out.order = hunt.map(r => [r.v.id, r.score, r.meanD]);

const twin = id => air(id, fighter(), { su: { turn: 20 } }), stocked = bvDuel(twin('a'), twin('b'), turnFoe, { mode: 1, stock: true });
const gun = id => tank(id, { pen: [200, 180, 150] }, { su: { pen: [150, 140, 100] } });
const pen = term(bvDuel(gun('a'), gun('b'), foe('ground', 'brawl'), { mode: 1, stock: true }), 'pen500');
out.stock = { duel: [stocked.v, term(stocked, 'turn').a, term(stocked, 'turn').b], upgraded: bvDuel(twin('a'), twin('b'), turnFoe, RB).v, pen: [pen.a, pen.b],
  rank: bvRank({ vehicles: [twin('a'), twin('b')], type: 'air', style: 'turn', mode: 1, br: 4, stock: true, onlyStyle: true }).map(r => [r.v.id, r.w, r.l]) };
// su null: the stock candidate has no value for it (no unguided round in its stock rounds), unknown like a stat it lacks
const quick = id => tank(id, { vel: 1500, rev: 10, pen: [200, 180, 150] }, { su: { vel: null, pen: null } });
const velDuel = (a, stock) => bvDuel(a, tank('b', { vel: 1000, rev: 10 }), pick({ vel: 1, rev: 1 }), { mode: 1, stock });
out.unknown = { stock: velDuel(quick('a'), true), none: velDuel(tank('a', { rev: 10 }), true), upgraded: velDuel(quick('a'), false).v,
  pen: [bvVal(quick('a'), 'pen500', true), bvVal(quick('a'), 'kill1000', true), bvVal(quick('a'), 'pen500', false)] };

out.modes = { airAB: term(bvDuel(twin('a'), twin('b'), turnFoe, { mode: 0 }), 'turn').w, airSB: term(bvDuel(twin('a'), twin('b'), turnFoe, { mode: 2 }), 'turn').w,
  groundAB: term(bvDuel(tank('a', { th: 1, dep: 8 }), tank('b', { th: 1, dep: 8 }), foe('ground', 'snipe'), { mode: 0 }), 'th').w,
  heliAB: term(bvDuel(heli('a', { th: 1 }), heli('b', { th: 1 }), foe('heli', 'hair'), { mode: 0 }), 'th').w };
const heliTh = mode => bvRank({ vehicles: [heli('h', { atg: 4, th: 1 }), heli('i', { atg: 4 })], type: 'heli', style: 'hatgm', mode, br: 9, stock: false, onlyStyle: true })
  .find(r => r.v.id === 'h').mission;
out.heliMission = [heliTh(0), heliTh(1)];

// a term that needs a stat on either side: flares against IR missiles
const cmIn = (f, a, b) => !!term(bvDuel(a, b, f, RB), 'cm');
const rotor = (id, s) => heli(id, { fg: 2, spd: 250, climb: 10, ...s }), radarJet = (id, s) => air(id, { tw: .8, spd: 1200, climb: 100, turn: 25, rm: 2, rmq: 1, rmr: 30, rad: 40, ...s }, { br: [10, 10, 10] });
out.need = { hair: [cmIn(foe('heli', 'hair'), rotor('a', { cm: 60 }), rotor('b')), cmIn(foe('heli', 'hair'), rotor('a', { cm: 60, ir: 2 }), rotor('b')), cmIn(foe('heli', 'hair'), rotor('a', { cm: 60 }), rotor('b', { ir: 2 }))],
  missile: [cmIn(foe('air', 'missile'), radarJet('a', { cm: 60 }), radarJet('b')), cmIn(foe('air', 'missile'), radarJet('a', { cm: 60 }), radarJet('b', { ir: 2 }))],
  turn: [cmIn(turnFoe, air('a', fighter({ cm: 60 })), air('b', fighter())), cmIn(turnFoe, air('a', fighter({ cm: 60 })), air('b', fighter({ irq: 1 })))],
  rwr: Object.keys(foe('heli', 'hair').terms).includes('rwr') };
// a side's flares act only on the other side's IR missiles
const cmT = b => term(bvDuel(rotor('a', { ir: 4, cm: 192 }), b, foe('heli', 'hair'), RB), 'cm')?.t ?? null;
out.need.oneSided = [cmT(rotor('b', { cm: 30 })), cmT(rotor('b', { cm: 0 })), cmT(rotor('b', { ir: 2, cm: 30 }))];
// Missiles and radar in Stock: candidates by their stock missiles
const msl = bvStyleOf('air', 'missile');
out.missileStock = [radarJet('a'), radarJet('b', {}), radarJet('c', { ir: 2 })].map((v, i) => { if (i === 1) v.su = { rm: 0 }; return [msl.cand(v, false), msl.cand(v, true)]; });

const prey = [air('y', { spd: 600, climb: 20, ceil: 11000, fg: 3 }), air('b', { spd: 450 }, { k: 'bomber' }), air('s', { spd: 800 }, { k: 'assault' }), air('r', { spd: 900, rm: 2 }, { k: 'assault' })];
out.hunter = bvMatchups({ v: prey[0] }, { vehicles: prey, type: 'air', style: 'hunter', mode: 1 }).map(x => x.o.id).sort();

// gl: the main weapon fires guided missiles only; s a SAM-only one
const gunTD = tank('g', { pen: [200, 180, 150], cal: 100, rel: 6, trav: 20, crew: 4, pw: 15, rev: 10, spd: 50, vel: 900, dep: 8 });
const atgmTD = tank('m', { gl: 1, atg: 4, atr: 4000, atp: 600, pen: [600, 600, 600], cal: 152, rel: 10 }, { ro: ['tank_destroyer'] });
const glV = [gunTD, tank('t', { pen: [150, 140, 120], cal: 76 }), atgmTD, spaa('s', { gl: 1, sam: 8000, pen: [50, 50, 50], cal: 239 }, { br: [6, 6, 6] }), { ...heli('h', { atg: 4, atr: 6000 }), br: [6, 6, 6] }];
const glMet = (v, type, style) => bvMatchups({ v }, { vehicles: glV, type, style, mode: 1 }).map(x => x.o.id).sort();
out.gl = { ...Object.fromEntries(['brawl', 'snipe', 'flank', 'ambush'].map(s => [s, glMet(gunTD, 'ground', s)])), hatgm: glMet(glV[4], 'heli', 'hatgm'),
  cal: [term(bvDuel(gunTD, atgmTD, foe('ground', 'ambush'), RB), 'cal'), term(bvDuel(atgmTD, gunTD, foe('ground', 'ambush'), RB), 'cal'), !!term(bvDuel(gunTD, glV[1], foe('ground', 'ambush'), RB), 'cal')] };
// with every vehicle listed: one its style's opponents leave out duels nobody either
const glAll = s => bvRank({ vehicles: glV, type: 'ground', style: s, mode: 1, br: 6, stock: false, onlyStyle: false });
out.glSelf = { ...Object.fromEntries(['brawl', 'snipe', 'flank', 'ambush'].map(s => [s, glAll(s).filter(r => r.n).map(r => r.v.id).sort()])),
  off: glAll('brawl').filter(r => r.off).map(r => r.v.id).sort(), met: bvMatchups({ v: atgmTD }, { vehicles: glV, type: 'ground', style: 'brawl', mode: 1 }).length };

// with every vehicle listed: a tank, gun SPAA, SAM SPAA, a gun SPAA whose stock has no AA gun
const aaTarget = air('j', { spd: 900 }, { br: [9, 9, 9], bt: [9, 9, 9] });
out.aa = [tank('t', { pw: 20 }, { br: [9, 9, 9] }), spaa('g', { aab: 3 }), spaa('m', { sam: 6000, aab: 2 }), spaa('u', { aab: 3 }, { su: { aab: 0 } })]
  .map((v, i) => reach(bvDuel(v, aaTarget, foe('ground', 'spaa'), { mode: 1, stock: i === 3 })));

const ship = (id, s, ro) => ({ ...boat(id, s), c: 'ship', k: ro === 'destroyer' ? 'destroyer' : 'cruiser', ro: [ro] });
out.torp = [boat('b', { tor: 2 }), boat('c', {}), ship('d', { tor: 8 }, 'destroyer'), ship('k', { tor: 12 }, 'heavy_cruiser')].map(v => bvStyleOf('naval', 'ntorp').cand(v));
const gunBoat = (id, fm, fa) => boat(id, { fm, fa, crew: 20, cal: 76, disp: 100, spd: 50 }), dd = (id, fm, tor) => ship(id, { fm, tor, spd: 65, crew: 300 }, 'destroyer');
const allGuns = bvDuel(gunBoat('a', 100, 700), gunBoat('b', 300, 300), foe('naval', 'nbrawl'), RB);
out.naval = { fa: [term(allGuns, 'fa')?.t ?? null, !!term(allGuns, 'fm'), allGuns.v], ndd: bvDuel(dd('g', 1500, 16), dd('v', 1809, 6), foe('naval', 'ndd'), RB).v,
  nddOrder: Object.keys(foe('naval', 'ndd').terms), notes: Object.fromEntries(BV_STYLES.naval.map(s => [s.id, s.notes])) };
out.rkt = [heli('a', { pay: 120, atg: 4 }), heli('b', { pay: 500, rkt: 300 })].map(v => bvStyleOf('heli', 'hrocket').cand(v));
// its mission too: p's heavier pay is a guided missile preset; no rkt is none, not unknown
out.rocket = { order: ids(bvRank({ vehicles: [heli('p', { pay: 500, rkt: 50 }), heli('r', { pay: 300, rkt: 300 })], type: 'heli', style: 'hrocket', mode: 1, br: 9, stock: false, onlyStyle: true })),
  none: bvVal(heli('a', { pay: 120, atg: 4 }), 'rkt') };

// zeros and empty records through every style, mode and both upgrade states, rows and their matchups
const odd = [air('f', {}, { br: [3, 3, 3] }), air('g', { spd: 500, climb: 15, turn: 20, fg: 2 }, { br: [3, 3, 3] }),
  air('b', { fg: 0, pay: 0, spd: 400, climb: 8, ceil: 7000 }, { k: 'bomber', br: [3, 3, 3] }), heli('h', { atg: 0, pay: 0 }),
  tank('t', {}), tank('u', { pen: [0, 0, 0], armH: [0, 0, 0], rel: 0, trav: 0, pw: 0 }), spaa('s', {}, { br: [3, 3, 3] }),
  boat('n', { fm: 0, fa: 0, disp: 0, spd: 0, crew: 0, cal: 0 }), boat('m', { fm: 100, fa: 300, disp: 50, spd: 40, crew: 10, cal: 20, tor: 2 }), { id: 'nobr', c: 'air', k: 'fighter', s: {} }];
out.odd = [];
for (const type of Object.keys(BV_STYLES)) for (const st of BV_STYLES[type]) for (const mode of [0, 1, 2]) for (const stock of [false, true]) {
  const ctx = { vehicles: odd, type, style: st.id, mode, br: null, stock, onlyStyle: false };
  out.odd.push({ type, style: st.id, mode, stock, rows: bvRank(ctx).map(r => ({ ...r, v: r.v.id, met: bvMatchups(r, ctx).map(x => ({ o: x.o.id, ...x.res })) })) });
}

const ace = air('a', fighter({ fg: 2, roll: undefined }), { br: [7.7, 7.7, 7.7] }), worse = air('b', fighter({ turn: 24, climb: 9, fg: 1, roll: undefined }), { br: [7.7, 7.7, 7.7] });
const small = (vehicles, style) => bvRank({ vehicles, type: 'air', style, mode: 1, br: 7.7, stock: false, onlyStyle: true }).map(r => [r.v.id, r.n, r.w, r.l, r.score, r.mission]);
out.small = { one: small([ace, worse], 'turn'), none: small([ace], 'turn'), hunter: small([ace, worse], 'hunter') };

let seed = 7;
const rnd = () => (seed = seed * 16807 % 2147483647) / 2147483647, BRS = Array.from({ length: 43 }, (_, i) => Math.round((1 + i / 3) * 10) / 10);
const fleet = Array.from({ length: 1500 }, (_, i) => {
  const b = BRS[i % 43], jet = b >= 8;
  return air('p' + i, { spd: 300 + 80 * b + 60 * rnd(), climb: 8 + 12 * rnd(), turn: 16 + 10 * rnd(), roll: 60 + 90 * rnd(), wl: 120 + 120 * rnd(),
    [jet ? 'tw' : 'pw']: jet ? .3 + .7 * rnd() : 200 + 300 * rnd(), fg: 1 + 10 * rnd(), irq: jet ? Math.floor(4 * rnd()) : 0, cm: jet ? Math.floor(80 * rnd()) : 0 }, { br: [b, b, b] });
});
const t0 = performance.now(), every = bvRank({ vehicles: fleet, type: 'air', style: 'turn', mode: 1, br: null, stock: false, onlyStyle: true });
out.speed = { ms: performance.now() - t0, rows: every.length, met: every.reduce((n, r) => n + r.n, 0) };

console.log(JSON.stringify(out, (k, x) => (typeof x === 'number' && !Number.isFinite(x) ? 'NOT FINITE' : x)));
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class DuelEngine(unittest.TestCase):
    """web/duel.js: terms, duels, gates, windows and rankings on made-up vehicles."""
    got = None
    raw = ""

    @classmethod
    def setUpClass(cls):
        run = subprocess.run(["node", "-e", DUEL, str(WEB / "duel.js")], capture_output=True, encoding="utf-8", check=True)
        cls.raw, cls.got = run.stdout, json.loads(run.stdout)

    def test_terms_abs_rel_and_direction(self):
        t = self.got["terms"]
        self.assertEqual(t["turn"], 1)  # lower is better: 18 s against 20.5 s, decisive from 10%
        self.assertEqual(t["even"], 0)  # 2.8%: inside the 5% band
        self.assertEqual(t["rel"], 1)  # a reload 2 s shorter, decisive from 1.5 s
        self.assertEqual(t["fg"][:2], [1, -1])
        self.assertEqual(t["fg"][2], -t["fg"][3])  # a log ratio: the same seen from either side
        self.assertTrue(0 < t["fg"][2] < 1)
        self.assertEqual(t["spd"], [-0.5, 0, -1])  # propeller pair 10 / 30 km/h, jets 50 / 100

    def test_capabilities(self):
        c = self.got["caps"]
        self.assertIsNone(c["none"])  # neither has a radar: it tells nothing
        self.assertEqual((c["lacks"], c["one"]), (-1, 1))  # none against some decides, whatever the band
        self.assertEqual(c["absent"], [0, None])  # absent: a capability is 0, a measured stat unknown

    def test_coverage_and_not_enough_data(self):
        self.assertEqual(self.got["cover"], ["even", "na", "na"])  # 3.0, 2.8 and 2.3 of 4.8 known

    def test_verdict_thresholds(self):
        v = self.got["verdicts"]
        self.assertEqual(v[:3], [["adv", 0.2], ["even", 0.19], ["dis", -0.2]])
        self.assertEqual([x[0] for x in v[3:]], ["adv", "dis"])  # an exact 0.2 the float sum gives as 0.19999999999999998

    def test_gates(self):
        g = self.got["gates"]
        self.assertEqual(g["refuse"], ["even", "refuse"])  # 5% faster and climbing 16% better: it leaves
        self.assertEqual(g["stays"], ["adv", None])  # 4% faster: it can't
        self.assertEqual(g["above"], ["dis", "above"])
        self.assertEqual(g["outgun"], ["dis", "outgun"])  # 200 mm against 450 at 500 m
        # an exact limit is not past it: 15% (12 against 13.8) and 4.5% (480 against 501.6) compute as a hair more,
        # 8% better climb (20 against 21.6) as a hair beyond the band; 225 mm is half of 450
        self.assertEqual(g["exact"], [["adv", None]] * 4)
        # only where armor counts: from 8.7, on either side, a shaped charge's millimetres and a dart's don't compare
        self.assertEqual(g["armor"], [["adv", None]] * 3)
        gated = {"turn": ["refuse"], "bnz": ["above"], "brawl": ["outgun"], "snipe": ["outgun"], "ambush": ["outgun"]}
        for style, foes in g["listed"].items():  # every foe has its list, empty for most
            self.assertEqual(foes, [gated.get(style, [])] * len(foes), style)

    def test_armor_cut_at_8_7(self):
        self.assertEqual(self.got["armor"], [True, False, False, True, False])

    def test_pair_kinds_and_skips(self):
        k = self.got["kinds"]
        self.assertEqual(k["spd"][:2], [0, -0.5])  # 20 km/h: inside the jets' 50, half way for propellers (10 / 30)
        self.assertAlmostEqual(k["spd"][2], -(math.log(620 / 600) - math.log(1.02)) / (math.log(1.06) - math.log(1.02)))  # 2% / 6%
        self.assertEqual(k["pwr"], [True, True, False])  # thrust against power: not compared
        self.assertIsNone(k["skip"])
        self.assertEqual(k["mixed"], "even")  # nor counted in the coverage: 2.8 of 4.2 known, not of 4.8
        self.assertEqual(k["rel"], [True, False])  # an autocannon's reload is not a gun's
        self.assertEqual(k["turret"], 150 / 120)  # the sniper's target is hull down: its turret front

    def test_pair_terms_reach_side_kill(self):
        p = self.got["pair"]
        self.assertEqual(p["missile"], [1, 8000, 5500])  # 2500 m more than its SAMs: decisive from 1500
        self.assertLess(p["guns"][0], 0)  # 2000 m against guns that reach 3000
        self.assertEqual(p["guns"][2], 3000)
        # helicopter against SPAA on the SPAA styles' bands (500 / 2000 m): 750 m more than guns; 700 m short of a SAM
        self.assertAlmostEqual(p["wide"][0], 1 / 6)
        self.assertEqual(p["wide"][1], "even")
        self.assertEqual(p["side"], [1, 160, 80])  # the thickest side plate
        self.assertEqual(p["kill"], [500, 60])  # the missile within its range, else the gun

    def test_cas_uses_ground_battle_br(self):
        c = self.got["cas"]
        self.assertEqual((c["at"], c["n"], c["other"]), (["x"], 2, []))
        self.assertEqual(c["met"], ["f", "s"])  # f at 10.7 in ground battles; g at 12.0 is too far

    def test_cas_groups_count_as_halves(self):
        # the SPAA beaten and the three fighters lost to: (1 - 1) / 2, not (1 - 3) / 4; the counts shown stay the sums
        self.assertEqual(self.got["cas"]["halves"], [["x", 1, 0, 3, 0]])

    def test_cas_candidates_in_stock(self):
        s = self.got["cas"]["stock"]
        self.assertEqual(s["cand"], [False, True, True])
        self.assertEqual([r[0] for r in s["upgraded"]], ["a", "b", "c"])
        self.assertEqual([r[0] for r in s["stock"]], ["b", "c"])
        # nor in the mission's population: c's payload against b's alone, every other mission stat even
        self.assertAlmostEqual(s["stock"][1][1], 2 * (0.25 + 1.6 * 0.5) / 2.6 - 1)

    def test_term_needs_a_stat_on_either_side(self):
        n = self.got["need"]
        self.assertEqual(n["hair"], [False, False, True])  # flares decoy the other side's IR missiles only
        self.assertEqual(n["missile"], [False, True])
        self.assertEqual(n["turn"], [False, True])
        self.assertFalse(n["rwr"])  # no helicopter carries a radar missile
        # a side's flares count only against the other's IR missiles: 192 against none count for nothing
        self.assertEqual(n["oneSided"], [-1, None, 1])

    def test_missile_candidates_in_stock(self):  # by the stock aircraft's missiles
        self.assertEqual(self.got["missileStock"], [[True, True], [True, False], [True, True]])

    def test_hunter_meets_bombers_and_attackers_without_radar_missiles(self):
        self.assertEqual(self.got["hunter"], ["b", "s"])

    def test_missile_carriers(self):
        g = self.got["gl"]
        self.assertEqual(g["brawl"], ["t"])
        for style in ("snipe", "flank", "ambush"):  # the SAM-only one fights no ground vehicle
            self.assertEqual(g[style], ["m", "t"], style)
        self.assertEqual(g["hatgm"], ["g", "m", "s", "t"])
        self.assertEqual(g["cal"], [None, None, True])  # a missile's diameter is no caliber

    def test_missile_carriers_with_every_vehicle_listed(self):  # not scored as gun tanks
        g = self.got["glSelf"]
        self.assertEqual(g["brawl"], ["g", "t"])
        for style in ("snipe", "flank", "ambush"):
            self.assertEqual(g[style], ["g", "m", "t"], style)
        self.assertEqual(g["off"], ["m", "s"])
        self.assertEqual(g["met"], 0)

    def test_anti_aircraft_reach_needs_aa_weapons(self):
        self.assertEqual(self.got["aa"][0], [-1, 0, 2000])  # listed with the filter off
        self.assertAlmostEqual(self.got["aa"][1][0], 1 / 3)
        self.assertEqual(self.got["aa"][1][1:], [3000, 2000])
        self.assertEqual(self.got["aa"][2], [1, 6000, 2000])
        self.assertEqual(self.got["aa"][3], [-1, 0, 2000])

    def test_naval_styles(self):
        self.assertEqual(self.got["torp"], [True, False, True, False])  # boats and destroyers with torpedoes
        n = self.got["naval"]
        self.assertEqual(n["fa"], [1, False, "adv"])  # every gun's firepower, not the primary group's
        self.assertEqual(n["ndd"], "even")  # 16 tubes against 6 no longer decide alone
        self.assertEqual(n["nddOrder"], ["fm", "spd", "crew", "tor"])  # the weights line in the help's order: heaviest first
        self.assertEqual(n["notes"], {"nbrawl": ["navalArmor"], "ntorp": [], "ndd": [], "nrange": []})

    def test_rockets_and_guns_candidates(self):
        self.assertEqual(self.got["rkt"], [False, True])  # unguided rockets and bombs, not the ATGM mass in pay

    def test_rockets_and_guns_mission_reads_rkt(self):
        self.assertEqual(self.got["rocket"], {"order": ["r", "p"], "none": 0})

    def test_window(self):
        self.assertEqual(self.got["window"], [True, True, False, False, 3, 2.3, 3, None])

    def test_pool_leaves_out_unplayable(self):
        self.assertEqual(self.got["pool"], [["ok", "gone", "ussr_t_72b3_arena_m"], ["ok", "ussr_t_72b3_arena_m"]])

    def test_mission_percentile_and_score(self):
        m, rows = self.got["mission"]["m"], {r["id"]: r for r in self.got["mission"]["rows"]}
        for i, share in (("b1", 1 / 6), ("b2", 2 / 3), ("b3", 2 / 3)):  # ties count half
            r = rows[i]
            self.assertAlmostEqual(r["mission"], 2 * share - 1)
            self.assertAlmostEqual(r["net"], (r["w"] - r["l"]) / (r["w"] + r["e"] + r["l"]))
            self.assertAlmostEqual(r["score"], (1 - m) * r["net"] + m * r["mission"])
        self.assertEqual([r["id"] for r in self.got["mission"]["rows"]], ["b2", "b3", "b1"])

    def test_rank_order_and_ties(self):
        order = self.got["order"]
        self.assertEqual([r[0] for r in order], ["x", "y", "z"])
        self.assertEqual(order[0][1], order[1][1])
        self.assertGreater(order[0][2], order[1][2])

    def test_stock_candidate_against_upgraded_opponents(self):
        s = self.got["stock"]
        self.assertEqual(s["duel"], ["dis", 20, 18])  # its stock turn time against the opponent's upgraded one
        self.assertEqual(s["upgraded"], "even")
        self.assertEqual(s["pen"], [150, 200])  # stock values of a triple too
        self.assertEqual(s["rank"], [["a", 0, 1], ["b", 0, 1]])  # each stock one loses to the other upgraded

    def test_stock_null_is_an_unknown_measured_stat(self):
        u = self.got["unknown"]
        self.assertEqual(u["stock"], u["none"])  # su.vel null reads as a vehicle without vel, not as its upgraded 1500
        self.assertEqual(u["stock"]["v"], "na")  # skipped, its weight still in the total: 1 of 2 known, under 60%
        self.assertNotIn("vel", [x["k"] for x in u["stock"]["terms"]])
        self.assertEqual(u["upgraded"], "adv")
        self.assertEqual(u["pen"], [None, None, 200])  # a whole triple null: unknown at every range

    def test_mode_factors(self):
        m = dict(self.got["modes"])
        self.assertAlmostEqual(m.pop("airAB"), 1.5 * 1.3)
        self.assertEqual(m, {"airSB": 1.5, "groundAB": 0.25, "heliAB": 0.2})  # helicopters: ground battles
        for got, w in zip(self.got["heliMission"], (0.2, 0.4)):  # th 1 against 0, every other mission stat even
            self.assertAlmostEqual(got, 0.5 * w / (2.3 + w))

    def test_zero_and_empty_never_give_nan(self):
        self.assertNotIn("NOT FINITE", self.raw)
        runs = {(r["type"], r["style"], r["mode"], r["stock"]): r["rows"] for r in self.got["odd"]}
        self.assertEqual(len(runs), 19 * 3 * 2)
        for rows in runs.values():
            for r in rows:
                self.assertTrue(all(isinstance(r[k], (int, float)) for k in ("score", "net", "meanD")), r)
                self.assertEqual(r["n"], len(r["met"]))
                self.assertNotIn("nobr", [r["v"]] + [m["o"] for m in r["met"]])  # no BR: nowhere to meet
        hunter = {r["v"]: r for r in runs[("air", "hunter", 1, False)]}
        self.assertEqual([m["v"] for m in hunter["f"]["met"]], ["na"])  # no stats at all against the bomber
        self.assertEqual((hunter["f"]["score"], hunter["f"]["mission"]), (-0.5, -0.5))  # no duel: its guns, 0 kg/s against 0 and 2
        turn = {r["v"]: r for r in runs[("air", "turn", 1, False)]}
        self.assertEqual({m["o"]: m["v"] for m in turn["f"]["met"]}, {"g": "na"})  # only the capabilities compare
        self.assertEqual(runs[("heli", "hrocket", 1, False)][0]["n"], 0)  # no SPAA within 1.0 of 9.0
        boats = {r["v"]: r for r in runs[("naval", "nbrawl", 1, False)]}
        self.assertEqual([m["v"] for m in boats["n"]["met"]], ["dis"])  # zeros against a gunboat

    def test_small_and_empty_pools(self):
        s = self.got["small"]
        self.assertEqual(s["one"], [["a", 1, 1, 0, 1, None], ["b", 1, 0, 1, -1, None]])
        self.assertEqual(s["none"], [["a", 0, 0, 0, 0, None]])  # alone: nothing to beat, no mission part
        self.assertEqual(s["hunter"], [["a", 0, 0, 0, 0.5, 0.5], ["b", 0, 0, 0, -0.5, -0.5]])  # no bombers: the mission part only

    def test_every_br_is_fast(self):
        s = self.got["speed"]
        self.assertEqual(s["rows"], 1500)
        self.assertGreater(s["met"], 300000)
        self.assertLess(s["ms"], 300)


# web/best.js's BR list (bvRender) with the bar and the table stubbed out: the BRs it hands the bar, upgraded then in Stock
BR_LIST = r"""
const fs = require('fs'), vm = require('vm');
globalThis.store = { get: (k, d) => d };
globalThis.S = { vehicles: [] };
globalThis.MODES = ['ab', 'rb', 'sb'];
globalThis.NATIONS = [];
globalThis.$ = () => ({});
for (const f of process.argv.slice(1)) vm.runInThisContext(fs.readFileSync(f, 'utf8'));
let listed;
globalThis.bvBarHTML = (st, brs) => { listed = brs; };
globalThis.bvBody = () => {};
// close air support, at ground-battle BRs: f's stock carries nothing
const air = (id, k, bt, s, su) => ({ id, c: 'air', k, br: [4, 4, 4], bt: [bt, bt, bt], s, su });
S.vehicles = [air('a', 'assault', 4, { pay: 1000 }), air('f', 'fighter', 5, { pay: 1000 }, { pay: 0 })];
Object.assign(BV.f, { type: 'air', style: 'cas' });
console.log(JSON.stringify([true, false].map(upg => { S.upg = upg; bvRender(); return listed; })));
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class BrList(unittest.TestCase):
    def test_stock_candidates_only(self):
        run = subprocess.run(["node", "-e", BR_LIST, str(WEB / "duel.js"), str(WEB / "best.js")], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(json.loads(run.stdout), [[4, 5], [4]])  # in Stock f is no candidate: 5.0 has no row to list


if __name__ == "__main__":
    unittest.main()
