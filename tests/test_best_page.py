"""Best vehicles: the page's wiring, its words in every language, and the page itself in node (web/best.js)."""
import json
import re
import shutil
import subprocess
import unittest

from wtftd.paths import WEB

LANGS = ("en", "fr", "de", "ru", "pl", "es", "pt", "it", "cs", "zh", "ja")
# the stats the builder adds for the duels, and the values shown as words (1 to n)
NEW_STATS = "fg vne pay ir irq rm rmq rmr rad cm rwr def atg atr atp atq pen vel dep stab rf th sam aab fm fa tor torr".split()
VALUES = {"irq": 3, "rmq": 2, "rwr": 1, "atq": 2, "stab": 2, "rf": 2, "th": 1}


def words(lang):
    return json.loads((WEB / "locales" / f"{lang}.json").read_text(encoding="utf-8"))


def marks(s):
    return set(re.findall(r"\{\w+\}", s))


class Wiring(unittest.TestCase):
    def test_page_is_wired(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        tabs = re.findall(r'data-view="(\w+)"', html)
        self.assertEqual(tabs[tabs.index("vehicles") + 1], "best")
        self.assertIn('id="view-best"', html)
        scripts = re.findall(r'<script src="([\w.]+)"></script>', html)
        self.assertLess(scripts.index("hangar.js"), scripts.index("duel.js"))
        self.assertLess(scripts.index("duel.js"), scripts.index("best.js"))
        app = (WEB / "app.js").read_text(encoding="utf-8")
        menu = re.search(r"MENUS = \{ vehicles: \[([^\]]*)\]", app)[1].replace("'", "").replace(" ", "").split(",")
        self.assertEqual(menu[menu.index("vehicles") + 1], "best")
        self.assertIn("  bindBest();\n", app)
        self.assertIn("if (name === 'best') openBestView();", app)
        hangar = (WEB / "hangar.js").read_text(encoding="utf-8")
        self.assertIn("bvRefresh", re.search(r"\nfunction hgSet\(.*?\n}\n", hangar, re.S)[0])

    def test_reasons_wrap_in_their_column(self):
        # chips don't wrap elsewhere; a reason can be wider than its column (450 px in Russian, 244 px left at 1920 px), and
        # a long name took all of a row
        css = (WEB / "app.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\n\.bv-foe-name \{[^}]*max-width: 50%;")
        self.assertRegex(css, r"\n\.bv-why \{[^}]*\bmin-width: 0;")
        self.assertRegex(css, r"\n\.bv-why \.chip \{[^}]*white-space: normal;[^}]*height: auto;")

    def test_table_wraps_to_fit_its_box(self):
        # the house table never wraps: unwrapped, names, headers and traits made it wider than its box below about 1100 px,
        # and the open row's second column of opponents was cut
        css = (WEB / "app.css").read_text(encoding="utf-8")
        self.assertIn("\n.bv-table thead th, .bv-table .bv-name, .bv-table .bv-traits { white-space: normal; }", css)
        self.assertRegex(css, r"\n\.bv-traits \.chip \{[^}]*white-space: normal;")
        self.assertIn('<td class="bv-name">', (WEB / "best.js").read_text(encoding="utf-8"))

    def test_sort_button_fills_its_header(self):
        # a wrapped header makes the row taller than a button's line: the strips above and below it showed the pointer
        # and sorted nothing (44 px cells, 28 px buttons at 900 px)
        css = (WEB / "app.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\n\.bv-table th\.sortable \{[^}]*[{;] height: 1px;")
        self.assertRegex(css, r"\n\.bv-table th\.sortable button \{[^}]*[{;] height: 100%;")


class Words(unittest.TestCase):
    def test_new_stat_labels_in_every_locale(self):
        stats = dict(re.findall(r"^  (\w+): \{ cats: (.*)$", (WEB / "stats.js").read_text(encoding="utf-8"), re.M))
        self.assertFalse(set(NEW_STATS) - set(stats), "missing in STATS")
        self.assertEqual({k for k, entry in stats.items() if "vals: true" in entry}, set(VALUES))
        keys = {f"stat.{k}" for k in NEW_STATS} | {"stat.penHint"} | {f"stat.{k}.{n}" for k, top in VALUES.items() for n in range(1, top + 1)}
        self.in_every_locale(keys)

    def test_bv_keys_in_every_locale(self):
        page = (WEB / "best.js").read_text(encoding="utf-8") + (WEB / "index.html").read_text(encoding="utf-8")
        keys = set(re.findall(r"""['"](bv\.[A-Za-z0-9_.]*[A-Za-z0-9_])['"]""", page)) | {"nav.best"}
        duel = (WEB / "duel.js").read_text(encoding="utf-8")
        styles = re.findall(r"\{ id: '(\w+)'", duel)
        self.assertTrue(styles)
        keys |= {f"bv.{x}.{s}" for s in styles for x in ("style", "styleh")}
        # the words the page builds from a name: the verdicts, the styles' gates and notes
        def ids(text, field):  # the quoted names of "field = [...]" or "field: [...]"
            return set(re.findall(r"'(\w+)'", " ".join(re.findall(field + r"(?: =|:) \[([^\]]*)\]", text))))
        keys |= {f"bv.v.{x}" for x in ids(page, "BV_VERDICTS")} | {f"bv.gate.{x}" for x in ids(duel, "gates")} | {f"bv.{x}" for x in ids(duel, "notes")}
        self.assertTrue({"bv.v.na", "bv.gate.outgun", "bv.abApprox"} <= keys)
        self.in_every_locale(keys)

    def test_armor_note_text(self):
        note = words("en")["bv.armor"]
        for part in ("BR 8.7", "Leopard 2A6", "75 mm"):
            self.assertIn(part, note)
        for lang in LANGS:  # the example stays in every language, and the Outgunned rule is named as its chip says
            note = words(lang)["bv.armor"]
            self.assertIn("Leopard 2A6", note, lang)
            self.assertRegex(note, r"8[.,]7", lang)
            self.assertRegex(note, r"\b75\b", lang)
            self.assertIn(re.split("[:：]", words(lang)["bv.gate.outgun"])[0].strip(), note, lang)
            self.assertRegex(words(lang)["bv.styleh.brawl"], r"8[.,]7", lang)  # Brawler's help says where the rule stops too

    def test_all_guns_firepower_says_guns(self):
        # fa counts every gun, machine guns too, never rockets, torpedoes or depth charges: "all weapons" put the Pr.1124
        # MLRS's 153 kg/min, its rockets left out, under their name
        guns = {"en": "guns", "fr": "mitrailleuses", "de": "Rohrwaffen", "ru": "ствольного", "pl": "lufowego", "es": "ametralladoras",
                "pt": "metralhadoras", "it": "mitragliatrici", "cs": "hlavňových", "zh": "枪炮", "ja": "機関銃"}
        for lang in LANGS:
            self.assertIn(guns[lang], words(lang)["stat.fa"], lang)

    def test_help_names_stats_as_their_labels(self):
        # the weights under a style's help name the same stats: Sniper's help kept the old words when stat.vel was renamed
        for lang in LANGS:
            d = words(lang)
            for style, k in (("snipe", "stat.vel"), ("nbrawl", "stat.fa"), ("ndd", "stat.fm"), ("hrocket", "bv.k.rkt")):
                self.assertIn(d[k].casefold(), d[f"bv.styleh.{style}"].casefold(), (lang, style))

    def in_every_locale(self, keys):
        en = words("en")
        for lang in LANGS:
            d = words(lang)
            for k in sorted(keys):
                self.assertTrue(d.get(k), (lang, k))
                self.assertEqual(marks(d[k]), marks(en[k]), (lang, k))
                self.assertFalse({chr(0x2013), chr(0x2014)} & set(d[k]), (lang, k))  # no long dashes


# stats.js, duel.js and best.js with the rest of the app stubbed: an element per selector, words as their keys (each key
# asked for is kept with the names it was given), the page driven by its own click and change handlers
PAGE = r"""
const fs = require('fs'), vm = require('vm');
const els = {}, asked = {}, calls = [], focused = [];
globalThis.$ = sel => (els[sel] ||= { innerHTML: '', hidden: false, on: {}, classList: { contains: c => c === 'hidden' && els[sel].hidden },
  addEventListener(type, fn) { this.on[type] = fn; }, focus() { focused.push(sel); }, contains: el => el?.in === sel });
globalThis.$$ = () => [];
globalThis.CSS = { escape: String };
globalThis.document = { addEventListener() {} };
globalThis.store = { get: (k, d) => (k === 'bv' ? { type: 'ground', style: 'turn', mode: 2, owned: true } : d), set() {} };  // saved by another version
globalThis.S = { f: { brMode: 1 }, vehicles: [], byId: new Map() };
// My hangar's marks come in after the page is opened
globalThis.HG = { owned: new Set(), loading: new Promise(done => setTimeout(() => { HG.owned.add('t1'); done(); })) };
globalThis.t = (k, vars) => { asked[k] = Object.keys(vars || {}); return k; };
globalThis.I18N = { num: String, unit: String, unitFull: String, code: 'en' };
globalThis.esc = s => String(s ?? '').replace(/[&<>"']/g, c => `&#${c.charCodeAt(0)};`);
globalThis.icon = globalThis.unitImgTag = globalThis.flagHTML = globalThis.rarityTag = () => '';
globalThis.className = globalThis.nationName = String;
globalThis.fmtBR = b => (b == null ? '-' : b.toFixed(1));
globalThis.ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX'];
globalThis.NATIONS = ['usa', 'germany', 'ussr'];
globalThis.openCompare = ids => calls.push(['compare', ...ids]);
globalThis.showView = name => calls.push(['view', name]);
globalThis.openVehicle = id => calls.push(['open', id]);
globalThis.hgTestDrive = id => calls.push(['test', id]);
for (const f of process.argv.slice(1)) vm.runInThisContext(fs.readFileSync(f, 'utf8'));

const v = (id, c, k, br, s, more) => ({ id, c, k, n: 'usa', r: 3, br: [br, br, br], s, ...more });
S.vehicles = [
  v('f1', 'air', 'fighter', 4, { spd: 600, climb: 15, turn: 18, roll: 100, wl: 150, pw: 400, fg: 3, ceil: 10000, vne: 750, irq: 1 }, { su: { turn: 19, fg: 2 } }),
  v('f2', 'air', 'fighter', 4.3, { spd: 650, climb: 18, turn: 22, roll: 90, wl: 180, pw: 380, fg: 2, ceil: 11000, vne: 800 }, { n: 'germany', r: 4, ra: 5 }),
  v('z1', 'air', 'fighter', 4, { fg: 0, pay: 0, spd: 0, climb: 0, turn: 0 }),
  v('b1', 'air', 'bomber', 4, { spd: 450, climb: 8, ceil: 8000, def: 3, crew: 6, pay: 2000 }),
  v('j1', 'air', 'fighter', 10, { spd: 1200, climb: 100, turn: 25, tw: .8, ir: 2, irq: 2, rm: 2, rmq: 1, rmr: 30, rad: 40, cm: 60, rwr: 1, fg: 8 }),
  v('j2', 'air', 'fighter', 10.3, { spd: 1100, climb: 90, turn: 27, tw: .7, ir: 2, irq: 1, fg: 9 }),
  v('a1', 'air', 'assault', 9.7, { spd: 900, climb: 60, turn: 30, pay: 3000, atg: 4, atr: 8000, atq: 2, fg: 4 }, { bt: [9.3, 9.3, 9.3] }),
  v('h1', 'heli', 'helicopter', 9.3, { spd: 300, climb: 12, atg: 8, atr: 8000, atp: 1200, atq: 2, ir: 2, irq: 2, pay: 800, rkt: 400, fg: 3, th: 1, cm: 60, rwr: 1 }),
  v('h2', 'heli', 'helicopter', 9.7, { spd: 280, climb: 10, atg: 4, atr: 5000, atp: 600, atq: 1, pay: 600, fg: 2 }),
  v('t1', 'ground', 'tank', 6.7, { pen: [200, 180, 150], armH: [100, 80, 40], armT: [120, 60, 50], rel: 6, trav: 20, cal: 90, stab: 1, crew: 5, pw: 15, rev: 10, spd: 50, vel: 900, dep: 8, rf: 1 }, { ro: ['medium_tank'] }),
  v('t2', 'ground', 'tank', 6.7, { pen: [150, 140, 120], armH: [80, 45, 40], rel: 4, trav: 25, cal: 76, crew: 4, pw: 20, rev: 15, spd: 55, vel: 800 }, { ro: ['light_tank'], n: 'ussr' }),
  v('t3', 'ground', 'tank_destroyer', 7, { pen: [250, 240, 220], atr: 4000, atp: 500, atg: 5, rel: 8, trav: 10, cal: 105, crew: 4, pw: 12, rev: 5, th: 1 }, { ro: ['tank_destroyer'] }),
  // t1 with thinner armor: the armor term is the only one that differs
  v('t5', 'ground', 'tank', 6.7, { pen: [200, 180, 150], armH: [40, 30, 20], rel: 6, trav: 20, cal: 90, stab: 1, crew: 5, pw: 15, rev: 10, spd: 50, vel: 900, dep: 8, rf: 1 }, { ro: ['medium_tank'] }),
  v('t4', 'ground', 'tank', 9,{ pen: [400, 390, 370], armH: [80, 65, 25], rel: 6, trav: 30, cal: 120, stab: 2, crew: 4, pw: 25, rev: 30, spd: 70, vel: 1650, th: 1, rf: 2 }, { ro: ['medium_tank'] }),
  v('z2', 'ground', 'tank', 6.7, {}, { ro: ['medium_tank'] }),
  v('s1', 'ground', 'SPAA', 9, { sam: 6000, rad: 18, aab: 4, vert: 40, trav: 60, pw: 20 }, { ro: ['spaa'] }),
  v('n1', 'boat', 'torpedo_boat', 3, { fm: 100, fa: 400, crew: 10, cal: 20, disp: 50, spd: 70, tor: 2, torr: 3000 }),
  v('n2', 'boat', 'gun_boat', 3.3, { fm: 300, fa: 900, crew: 20, cal: 40, disp: 120, spd: 50 }),
  v('n3', 'ship', 'destroyer', 4, { fm: 2700, fa: 3600, crew: 300, cal: 127, disp: 2000, spd: 65, tor: 10, torr: 5500 }, { ro: ['destroyer'] }),
  v('n4', 'ship', 'cruiser', 4.3, { fm: 4900, fa: 7000, crew: 1000, cal: 203, disp: 14000, spd: 60 }, { ro: ['heavy_cruiser'] }),
  v('x1', 'air', 'fighter', 4, { spd: 900 }, { h: 1 }),
];
S.byId = new Map(S.vehicles.map(x => [x.id, x]));

(async () => {
  bindBest();
  const view = $('#view-best'), page = () => $('#bvBar').innerHTML + $('#bvBody').innerHTML;
  const click = data => view.on.click({ target: { closest: () => ({ dataset: data }) } });
  const change = target => view.on.change({ target: { id: '', dataset: {}, ...target } });
  const ids = () => [...$('#bvBody').innerHTML.matchAll(/<tr data-bvrow="([^"]*)"/g)].map(m => m[1]);
  // an open row's verdict groups in page order, each with its opponents' D, and how many duels it has and of them unknown
  const groups = id => {
    const ms = bvMatchups(BV.ranked.rows.find(r => r.v.id === id), bvCtx()), D = new Map(ms.map(m => [m.o.id, m.res.D]));
    const by = Object.fromEntries($('#bvBody').innerHTML.split('<h4 class="ar-lbl">').slice(1)
      .map(part => [part.match(/^bv\.v\.(\w+)/)[1], [...part.matchAll(/data-bvcmp="([^"]*)"/g)].map(m => D.get(m[1]))]));
    return { heads: Object.keys(by), dis: by.dis || [], foes: ms.length, na: ms.filter(m => m.res.v === 'na').length };
  };
  await openBestView();
  const f = () => [BV.f.type, BV.f.style, BV.f.mode];
  const out = { first: ids(), saved: f(), stale: [], runs: [] };
  change({ dataset: { bvsw: 'owned' }, checked: false });
  // more choices another version could have saved: an unknown type, a style of another type, a mode the style hasn't
  for (const saved of [{ type: 'tanks', style: 'brawl', mode: 1 }, { type: 'toString', style: 'turn', mode: 1 }, { type: 'naval', style: 'ndd', mode: 2 },
    { type: 'air', style: 'ntorp', mode: 7 }]) {
    Object.assign(BV.f, saved);
    bvRender();
    out.stale.push([...f(), ids().length > 0]);
  }
  click({ bvtype: 'air' });
  click({ bvstyle: 'bnz' });
  click({ bvtype: 'air' });
  out.switch = [BV.f.style];
  click({ bvtype: 'naval' });
  out.switch.push(BV.f.style);
  click({ bvtype: 'air' });
  out.switch.push(BV.f.style);
  for (const type of Object.keys(BV_STYLES)) for (const st of BV_STYLES[type]) for (const mode of [0, 1, 2]) for (const upg of [true, false]) for (const br of ['', 'one']) {
    click({ bvtype: type });
    click({ bvstyle: st.id });
    click({ bvmode: String(mode) });
    if (S.upg !== upg) { S.upg = upg; bvRefresh(); }
    const brs = [...$('#bvBar').innerHTML.matchAll(/<option value="([\d.]+)"/g)].map(m => m[1]);
    change({ id: 'bvBr', value: br && (brs[Math.floor(brs.length / 2)] || '') });
    const rows = ids();
    if (rows.length) click({ bvrow: rows[0] });
    const html = page();
    // each chip that tells better from worse by its colour, with the first line of its title (a gate says it in its text)
    const chips = [...html.matchAll(/<span class="chip (info|warn)"(?: title="([^"]*)")?>([^<]*)/g)].filter(m => !m[3].startsWith('bv.gate.'));
    out.runs.push({ type, style: st.id, mode, upg, br, rows: rows.length, open: html.includes('ar-detail'), sb: html.includes('>bv.sb<'),
      ab: html.includes('>bv.abApprox<'), armor: html.includes('>bv.armor<'), navalArmor: html.includes('>bv.navalArmor<'), sbOff: /data-bvmode="2"[^>]*disabled/.test(html),
      chips: [...new Set(chips.map(m => `${m[1]} ${(m[2] || '').split('\n')[0]}`))],
      ...(rows.length && groups(rows[0])), odd: (html.match(/NaN|Infinity|undefined|\[object/g) || []).join() });
  }
  const key = () => focused.at(-1), thead = () => $('#bvBody').innerHTML.match(/<thead>.*<\/thead>/s)[0];
  click({ bvtype: 'air' });
  click({ bvstyle: 'turn' });
  click({ bvmode: '1' });
  // the control that changed the page keeps the keyboard once it is drawn again
  out.keys = [key()];
  change({ id: 'bvBr', value: '' });
  out.keys.push(key());
  click({ bvrank: '3' });
  out.keys.push(key());
  out.bar = $('#bvBar').innerHTML;  // rank III chosen
  click({ bvrank: '3' });
  click({ bvnation: 'usa' });
  out.keys.push(key());
  click({ bvnation: 'usa' });
  // the BR choice lists the BRs that have rows; a BR left without any moves to the nearest
  const brs = () => [...$('#bvBar').innerHTML.matchAll(/<option value="([\d.]+)"/g)].map(m => +m[1]);
  out.brs = [brs()];
  change({ dataset: { bvsw: 'removed' }, checked: true });
  out.keys.push(key());
  out.brs.push(brs());
  change({ id: 'bvBr', value: '4.3' });
  change({ dataset: { bvsw: 'removed' }, checked: false });
  out.brs.push(BV.f.br);
  change({ dataset: { bvsw: 'only' }, checked: false });
  out.brs.push(brs());
  change({ dataset: { bvsw: 'only' }, checked: true });
  click({ bvstyle: 'bomber' });
  out.brs.push(brs());
  // Owned only: none of these marked, then nothing marked at all
  const empty = () => $('#bvBody').innerHTML.match(/<div class="empty"><p>([^<]*)/)?.[1];
  change({ dataset: { bvsw: 'owned' }, checked: true });
  out.empty = [empty()];
  const marked = [...HG.owned];
  HG.owned.clear();
  bvRender();
  out.empty.push(empty());
  marked.forEach(x => HG.owned.add(x));
  change({ dataset: { bvsw: 'owned' }, checked: false });
  // rows with no verdict and no mission part: after every scored row in both score orders, without a place
  click({ bvstyle: 'bnz' });
  out.keys.push(key());
  change({ id: 'bvBr', value: '' });
  const places = () => [...$('#bvBody').innerHTML.matchAll(/<tr data-bvrow="([^"]*)"[^>]*><td class="num">(\d*)</g)].map(m => `${m[1]}#${m[2]}`);
  out.unjudged = [places()];
  out.heads = [thead()];
  click({ bvsort: 'score' });
  out.keys.push(key());
  out.unjudged.push(places());
  click({ bvsort: 'score' });
  click({ bvtype: 'air' });
  out.keys.push(key());
  click({ bvstyle: 'turn' });
  out.removed = [ids().includes('f2')];
  change({ dataset: { bvsw: 'removed' }, checked: true });
  out.removed.push(ids().includes('f2'));
  const byScore = ids();
  click({ bvsort: 'name' });
  out.byName = [ids()];
  out.heads.push(thead());
  click({ bvsort: 'name' });
  out.byName.push(ids());
  click({ bvsort: 'pos' });  // the # column: back to the ranking
  out.byPos = [ids().join() === byScore.join(), $('#bvBody').innerHTML.includes('data-bvsort="pos"')];
  click({ bvsort: 'name' });
  click({ bvtype: 'ground' });
  click({ bvstyle: 'brawl' });
  change({ id: 'bvBr', value: '6.7' });
  out.owned = [ids()];
  change({ dataset: { bvsw: 'owned' }, checked: true });
  out.owned.push(ids());
  change({ dataset: { bvsw: 'owned' }, checked: false });
  click({ bvrow: 't1' });
  out.focus = focused.at(-1);
  out.foes = [...$('#bvBody').innerHTML.matchAll(/data-bvcmp="([^"]*)"/g)].map(m => m[1]);
  out.reasons = /title="bv\.(better|worse)\nbv\.armor">[^<]*\*<\/span>/.test($('#bvBody').innerHTML);
  click({ bvcmp: 't2' });
  click({ bvopen: 't1' });
  click({ bvtest: 't1' });
  out.calls = calls;
  // one row more than a page: 95 fighters, one alone at its BR, and the fixture's 5 (f2 among them: removed vehicles are shown)
  S.vehicles.push(v('lone', 'air', 'fighter', 1, { spd: 300, turn: 15 }),
    ...Array.from({ length: 95 }, (_, i) => v(`c${i}`, 'air', 'fighter', 4, { spd: 500 + i, climb: 15, turn: 18 + i / 8, wl: 160, pw: 380, fg: 2 })));
  click({ bvtype: 'air' });
  change({ id: 'bvBr', value: '' });
  const more = () => [ids().length, $('#bvBody').innerHTML.includes('data-bvmore')];
  out.more = [more()];
  click({ bvmore: '' });
  out.more.push(more());
  out.moreKey = [key(), ids()[BV_PAGE]];
  click({ bvrow: 'lone' });
  out.lone = [groups('lone').heads, $('#bvBody').innerHTML.includes('<p class="hint">bv.noFoes</p>')];
  click({ bvrow: 'c94' });  // the slowest to turn: many losses
  out.weak = groups('c94');
  S.upg = !S.upg;
  bvRefresh();
  out.more.push(more());
  // Stock / Fully upgraded pressed (the focused element: where it is and its data): the bar's, drawn again, keeps the
  // keyboard; the drawer's keeps its own
  const upg = (where, set) => {
    const n = focused.length;
    document.activeElement = { in: where, dataset: { upgset: set } };
    S.upg = set === '1';
    bvRefresh();
    return focused.slice(n);
  };
  // with every vehicle listed, a SAM truck opened in Brawler: not made for this style, rather than no opponent
  S.vehicles.push(v('sam', 'ground', 'SPAA', 6.7, { gl: 1, sam: 6000 }));
  click({ bvtype: 'ground' });
  click({ bvstyle: 'brawl' });
  change({ id: 'bvBr', value: '6.7' });
  change({ dataset: { bvsw: 'only' }, checked: false });
  click({ bvrow: 'sam' });
  out.off = ['bv.noStyle', 'bv.noFoes'].map(k => $('#bvBody').innerHTML.includes(`<p class="hint">${k}</p>`));
  change({ dataset: { bvsw: 'only' }, checked: true });
  out.upgKeys = [upg('#bvBar', '0'), upg('#bvBar', '1'), upg('#drawer', '0')];
  view.hidden = true;
  $('#bvBody').innerHTML = 'kept';
  bvRefresh();
  out.hidden = $('#bvBody').innerHTML;
  out.asked = asked;
  console.log(JSON.stringify(out));
})();
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class ThePage(unittest.TestCase):
    """Every type, style, mode, BR and upgrade state rendered, a row opened in each, then its actions."""
    got = None

    @classmethod
    def setUpClass(cls):
        run = subprocess.run(["node", "-e", PAGE, str(WEB / "stats.js"), str(WEB / "duel.js"), str(WEB / "best.js")],
                             capture_output=True, encoding="utf-8", check=True)
        cls.got = json.loads(run.stdout)

    def test_every_style_renders_and_opens(self):
        runs = self.got["runs"]
        self.assertEqual(len({(r["type"], r["style"]) for r in runs}), 20)
        for r in runs:
            self.assertEqual(r["odd"], "", r)  # no NaN, Infinity or a missing value in the page
            self.assertEqual(r["open"], r["rows"] > 0, r)
        for type in ("air", "heli", "ground", "naval"):
            self.assertTrue(any(r["rows"] for r in runs if r["type"] == type), type)

    def test_armor_note_on_every_ground_style(self):
        for r in self.got["runs"]:
            self.assertEqual(r["armor"], r["type"] == "ground", r)
        self.assertTrue(self.got["reasons"])  # an armor reason carries the note too, and ends with an asterisk

    def test_naval_armor_note_on_gun_brawler_only(self):
        for r in self.got["runs"]:
            self.assertEqual(r["navalArmor"], r["style"] == "nbrawl", r)

    def test_mode_notes_and_naval_without_simulator(self):
        for r in self.got["runs"]:
            self.assertEqual(r["sbOff"], r["type"] == "naval", r)
            self.assertEqual(r["sb"], r["mode"] == 2 and r["type"] != "naval", r)
            self.assertEqual(r["ab"], r["mode"] == 0 and r["style"] in ("cas", "spaa"), r)

    def test_matchup_groups(self):
        # Advantage, Even and Disadvantage always, Not enough data when any, the hardest loss first; a row that meets
        # nobody says so
        opened = [r for r in self.got["runs"] if "heads" in r] + [self.got["weak"]]
        for r in opened:
            self.assertEqual(r["heads"], ["adv", "even", "dis"] + ["na"] * bool(r["na"]) if r["foes"] else [], r)
            self.assertEqual(r["dis"], sorted(r["dis"]), r)
        self.assertTrue(any(r["na"] for r in opened))
        self.assertGreater(len(set(self.got["weak"]["dis"])), 1)
        self.assertEqual(self.got["lone"], [[], True])
        self.assertEqual(self.got["off"], [True, False])

    def test_show_more_and_a_new_ranking(self):
        # a page, then the one row left; the Stock switch ranks anew and starts at one page again
        self.assertEqual(self.got["more"], [[100, True], [103, False], [100, True]])  # 96 + 5 + b1, a1

    def test_filters_hide_rows(self):
        self.assertEqual(self.got["removed"], [False, True])  # no longer available: shown on request
        by_name = self.got["byName"]
        self.assertEqual(by_name[0], sorted(by_name[0]))
        self.assertEqual(by_name[1], by_name[0][::-1])
        self.assertEqual(self.got["byPos"], [True, True])  # the # column sorts back to the ranking
        self.assertEqual([sorted(x) for x in self.got["owned"]], [["t1", "t5", "z2"], ["t1"]])  # light tanks aren't brawlers

    def test_choices_saved_by_another_version(self):
        self.assertEqual(self.got["first"], ["t1"])  # Owned only, drawn once My hangar's marks are in
        self.assertEqual(self.got["saved"], ["ground", "brawl", 2])  # ground's first style, Simulator kept
        self.assertEqual(self.got["stale"], [["air", "turn", 1, True], ["air", "turn", 1, True], ["naval", "ndd", 1, True], ["air", "turn", 1, True]])
        self.assertEqual(self.got["switch"], ["bnz", "nbrawl", "turn"])  # the same type keeps its style, another starts at its first

    def test_actions(self):
        self.assertIn("t2", self.got["foes"])  # every ground vehicle within 1.0 is met, light tanks too
        self.assertEqual(self.got["calls"], [["compare", "t1", "t2"], ["view", "vehicles"], ["open", "t1"], ["test", "t1"]])
        self.assertEqual(self.got["focus"], 'button[data-bvrow="t1"]')  # the row drawn again keeps the keyboard
        self.assertEqual(self.got["hidden"], "kept")  # a page not shown isn't rendered again

    def test_unscored_rows_last(self):
        # z1 meets the others on terms all unknown and Boom and zoom has no mission part: score 0 would rank it above
        # the others; it comes after them, highest or lowest score first, with no place (b1 and a1: every aircraft type)
        self.assertEqual(self.got["unjudged"], [["j1#1", "f1#2", "j2#3", "b1#4", "a1#5", "z1#"],
                                                ["a1#5", "b1#4", "j2#3", "f1#2", "j1#1", "z1#"]])

    def test_br_choice_lists_brs_with_rows(self):
        # every aircraft type flies the fighter styles: 4.0, 9.7 (a1), 10.0 and 10.3, the removed f2 at 4.3 once shown;
        # 4.3 hidden again moves to 4.0; with the filter off the same; bombers: b1 alone
        self.assertEqual(self.got["brs"], [[4, 9.7, 10, 10.3], [4, 4.3, 9.7, 10, 10.3], 4, [4, 9.7, 10, 10.3], [4]])

    def test_keyboard_stays_on_the_control(self):
        self.assertEqual(self.got["keys"], ['[data-bvmode="1"]', "#bvBr", '[data-bvrank="3"]', '[data-bvnation="usa"]',
                                            '[data-bvsw="removed"]', '[data-bvstyle="bnz"]', '[data-bvsort="score"]', '[data-bvtype="air"]'])
        key, first = self.got["moreKey"]
        self.assertEqual(key, f'button[data-bvrow="{first}"]')  # Show more: the first row added

    def test_keyboard_stays_on_the_upgrade_switch(self):
        self.assertEqual(self.got["upgKeys"], [['#bvBar [data-upgset="0"]'], ['#bvBar [data-upgset="1"]'], []])

    def test_owned_only_with_nothing_marked(self):
        # t1 is marked but isn't an aircraft: no match; nothing marked at all: the Vehicles page's words
        self.assertEqual(self.got["empty"], ["results.empty", "hg.emptyGrid"])

    def test_states_said_in_words(self):
        # better / worse and strongest / weakest in a title, not by colour only
        self.assertEqual({c for r in self.got["runs"] for c in r["chips"]}, {"info bv.best", "warn bv.worst", "info bv.better", "warn bv.worse"})
        buttons = re.findall(r'<button [^>]*data-bv(?:type|mode|style|rank|nation)="[^"]*"[^>]*>', self.got["bar"])
        for b in buttons:
            self.assertIn(' aria-pressed="%s"' % str(bool(re.search(r'class="[^"]*\bactive\b', b))).lower(), b)
        self.assertEqual(sum('aria-pressed="true"' in b for b in buttons), 4)  # type, mode, style, rank III
        for head, sort in zip(self.got["heads"], [("descending", "score"), ("ascending", "name")]):
            self.assertEqual(re.findall(r'<th class="sortable[^"]*"[^>]*><button type="button" data-bvsort="(\w+)"', head), ["pos", "name", "rank", "br", "score"])
            self.assertEqual(re.findall(r'aria-sort="(\w+)"><button type="button" data-bvsort="(\w+)"', head), [sort])

    def test_words_it_asks_for_are_in_every_locale(self):
        en = words("en")
        asked = {k: v for k, v in self.got["asked"].items() if k.startswith(("bv.", "nav.best"))}
        self.assertIn("bv.armor", asked)
        Words.in_every_locale(self, set(asked))
        for k, given in asked.items():
            self.assertLessEqual({m[1:-1] for m in marks(en[k])}, set(given), k)


if __name__ == "__main__":
    unittest.main()
