/* WTFTD - Best vehicles, the engine: a duel compares two vehicles on the stats of a play style; a ranking counts, for each
   vehicle of a type, the duels it wins against everything it can meet at its BR (within 1.0 in that mode). Only the game's
   stats (vehicles.json s and su): no skill, team, map or spotting. No page and no words here (web/best.js shows it), so node
   can test it alone. */
'use strict';

// A duel's own directions (dir 1: higher is better) and bands: inside the even band e a stat decides nothing, from the
// decisive threshold d on it decides fully, linear between. abs compares A - B; rel compares ln(A / B), its bands logs too
// (bvPct turns a share into them), so a duel reads the same from both sides. cap: a capability, absent means 0 and 0
// against some decides. A pair kind (prop, jet or mixed aircraft, ground, naval) replaces fields; skip: not compared.
const bvPct = (e, d) => ({ kind: 'rel', e: Math.log1p(e), d: Math.log1p(d) });
const bvAbs = (e, d) => ({ kind: 'abs', e, d });
const BV_COUNT = { dir: 1, cap: true, ...bvAbs(.5, 2) }, BV_KIND = { dir: 1, cap: true, ...bvAbs(.5, 1) };
const BV_PEN = { dir: 1, ...bvPct(.1, .3) };
const BV_STATS = {
  spd: { dir: 1, ...bvAbs(10, 30), jet: bvAbs(50, 100), mixed: bvPct(.02, .06), ground: bvAbs(5, 15), naval: bvAbs(5, 10) },
  climb: { dir: 1, ...bvPct(.08, .2) },
  turn: { dir: -1, ...bvPct(.05, .1) },
  roll: { dir: 1, ...bvPct(.1, .3) },
  wl: { dir: -1, ...bvPct(.07, .2) },
  pw: { dir: 1, ...bvPct(.05, .15), ground: bvAbs(2, 5) },
  tw: { dir: 1, ...bvAbs(.05, .1) },
  pwr: { dir: 1, ...bvPct(.05, .15), jet: bvAbs(.05, .1), mixed: { skip: true } },  // pw of propeller aircraft, tw of jets
  vne: { dir: 1, ...bvAbs(30, 80) },
  ceil: { dir: 1, ...bvPct(.05, .15) },
  crew: { dir: 1, ...bvPct(.2, .5), ground: bvAbs(.5, 2) },
  fg: { dir: 1, cap: true, ...bvPct(.15, .5) },
  aab: { dir: 1, cap: true, ...bvPct(.15, .5) },
  pay: { dir: 1, cap: true, ...bvPct(.15, .5) },
  rkt: { dir: 1, cap: true, ...bvPct(.15, .5) },
  ir: BV_COUNT, rm: BV_COUNT, tor: BV_COUNT, def: BV_COUNT, atg: BV_COUNT,
  irq: BV_KIND, rmq: BV_KIND, atq: BV_KIND, stab: BV_KIND, rf: BV_KIND, th: BV_KIND, rwr: BV_KIND,
  rmr: { dir: 1, cap: true, ...bvPct(.1, .3) },
  torr: { dir: 1, cap: true, ...bvPct(.1, .3) },
  atr: { dir: 1, cap: true, ...bvPct(.1, .3) },
  atp: { dir: 1, cap: true, ...bvPct(.1, .3) },
  sam: { dir: 1, cap: true, ...bvPct(.1, .3) },
  rad: { dir: 1, cap: true, ...bvPct(.15, .5) },
  cm: { dir: 1, cap: true, ...bvPct(.2, .6) },
  rev: { dir: 1, ...bvAbs(5, 15) },
  pen500: BV_PEN, pen1000: BV_PEN, pen2000: BV_PEN, kill1000: BV_PEN, kill2000: BV_PEN,
  vel: { dir: 1, ...bvPct(.08, .2) },
  rel: { dir: -1, ...bvAbs(.5, 1.5) },
  trav: { dir: 1, ...bvPct(.2, .5) },
  vert: { dir: 1, ...bvPct(.2, .5) },
  dep: { dir: 1, ...bvAbs(1, 3) },
  cal: { dir: 1, ...bvPct(.1, .4) },
  fm: { dir: 1, ...bvPct(.2, .5) },
  fa: { dir: 1, ...bvPct(.2, .5) },
  disp: { dir: 1, ...bvPct(.2, .5) },
  // pair terms, from both vehicles: A's reach against B's (m); penetration against nominal card armor (bands already logs)
  reach: { dir: 1, ...bvAbs(300, 1500) },
  front: { dir: 1, kind: 'rel', e: .1, d: .5 },
  side: { dir: 1, kind: 'rel', e: .1, d: .3 },
};
// Arcade battles: the instructor and the markers change what decides a fight
const BV_AB = { air: { turn: 1.3, fg: 1.2, climb: .8, spd: .9 }, ground: { th: .5, rf: .5, dep: .7, pw: 1.2 }, heli: { th: .5 } };
const BV_TYPES = { air: ['air'], heli: ['heli'], ground: ['ground'], naval: ['boat', 'ship'] };
const BV_PAIRS = ['prop', 'jet', 'mixed', 'ground', 'naval'];

// matchmaking: one step is one economic rank (.3 or .4 BR), a vehicle meets those within 3 steps (1.0)
const bvSteps = (a, b) => Math.round((a - b) * 3);
const bvInWindow = (br, other) => br != null && other != null && Math.abs(bvSteps(other, br)) <= 3;
// field 'bt': an aircraft's BR in ground battles, its own BR when it has none
const bvBr = (v, mode, field) => (field && v[field]?.[mode]) ?? v.br?.[mode] ?? null;

const BV_AT = { pen500: 500, pen1000: 1000, pen2000: 2000, kill1000: 1000, kill2000: 2000 };
const bvNum = x => (typeof x === 'number' ? x : null);
// A stat as a duel reads it: stock reads the stock value first (su holds the ones that differ; null there: unknown in
// stock), a capability absent is 0, a measured stat absent is null (unknown). pen<r>: the main gun at r m; kill<r>: or its
// guided missile when it reaches r.
function bvVal(v, k, stock) {
  const at = x => (stock && v.su?.[x] !== undefined ? v.su[x] : v.s?.[x]);
  if (k === 'pwr') return bvNum(at(v.s?.tw != null ? 'tw' : 'pw'));
  const r = BV_AT[k];
  if (r) {
    const gun = bvNum(at('pen')?.[[500, 1000, 2000].indexOf(r)]), missile = k[0] === 'k' && at('atr') >= r ? bvNum(at('atp')) : null;
    return missile > 0 && (gun == null || missile > gun) ? missile : gun;
  }
  const x = bvNum(at(k));
  return x == null && BV_STATS[k]?.cap ? 0 : x;
}
// "a jet": a thrust-to-weight ratio (jet or rocket engines; propellers have a power-to-weight ratio)
const bvJet = v => v.c === 'air' && v.s?.tw != null;
// the index of the pair kind in BV_PAIRS, from A's category and whether each is a jet
const bvPair = (c, ja, jb) => (c === 'ground' ? 3 : c === 'boat' || c === 'ship' ? 4 : ja !== jb ? 2 : ja ? 1 : 0);
// nominal card armor, [front, side, rear] mm of the hull (armH) and the turret (armT): the same stock and upgraded
const bvPlates = (v, i, parts) => parts.map(p => v.s?.[p]?.[i]).filter(x => x > 0);
function bvSpec(k, pair, over) {
  const s = { ...BV_STATS[k], ...BV_STATS[k][pair], ...over?.[k] };
  return { dir: s.dir, rel: s.kind === 'rel', e: s.e, d: s.d, cap: !!s.cap, skip: !!s.skip };  // one shape keeps the duel loop fast
}

// one stat's term: 1 when it decides for A, -1 for B, 0 inside the even band; null when unknown, not compared or when
// neither has it. ld: ln(a) - ln(b) when the caller has it
function bvT(s, a, b, ld) {
  if (s.skip) return null;
  if (s.cap) {
    if (!a && !b) return null;
    if (!a || !b) return a ? s.dir : -s.dir;
  } else if (a == null || b == null) return null;
  let x;
  if (!s.rel) x = s.dir * (a - b);
  else if (a > 0 && b > 0) x = s.dir * (ld ?? (Math.log(a) - Math.log(b)));
  else return a > 0 ? s.dir : b > 0 ? -s.dir : 0;
  const m = Math.abs(x);
  if (m <= s.e + 1e-9) return 0;  // float noise at a band's edge stays on the band's side
  return Math.sign(x) * (m >= s.d - 1e-9 ? 1 : (m - s.e) / (s.d - s.e));
}
const bvTerm = (k, a, b, pair) => bvT(bvSpec(k, pair), a, b);

// How each side of a term reads its value: fa the candidate (stock or not), fb the opponent (always fully upgraded).
// undefined: not compared in this duel.
function bvSides(k, foe, mode, gun) {
  const own = (v, stock) => bvVal(v, k, stock);
  // card armor means nothing from 8.7 (first ERA; add-on armor at 9.0, composite at 9.7): only when both are below
  const armor = (v, x) => { const b = bvBr(v, mode); return b != null && b < 8.7 ? x : undefined; };
  if (k === 'reach') return foe.reach;
  if (k === 'side') {  // the gun at 500 m against the thickest side plate
    return [(v, stock) => armor(v, bvVal(v, 'pen500', stock)), v => { const p = bvPlates(v, 1, ['armH', 'armT']); return armor(v, p.length ? Math.max(...p) : null); }];
  }
  if (k === 'front') {  // the gun at the style's range and the thinnest front plate (a sniper's target is hull down: the turret)
    const f = (v, stock) => { const g = bvVal(v, gun, stock), p = bvPlates(v, 0, foe.turret ? ['armT'] : ['armH', 'armT']); return armor(v, g > 0 && p.length ? [g, Math.min(...p)] : null); };
    return [f, f];
  }
  if (k === 'rel') {  // an autocannon's reload is a per-shot or magazine time, not a gun's reload
    const f = (v, stock) => (v.s?.auto ? undefined : own(v, stock));
    return [f, f];
  }
  if (k === 'cal') {  // a guided missile's diameter is no gun's caliber
    const f = (v, stock) => (v.s?.gl ? undefined : own(v, stock));
    return [f, f];
  }
  return [own, own];
}

const bvCompiled = new WeakMap();
// a foe's terms ready for many duels: weights for the mode, bands per pair kind, how each side reads its value
function bvCompile(foe, mode, cat) {
  if (!bvCompiled.has(foe)) bvCompiled.set(foe, new Map());
  const memo = bvCompiled.get(foe), key = mode + cat;
  if (memo.has(key)) return memo.get(key);
  const ab = (mode === 0 && BV_AB[cat]) || {}, gun = foe.range && (foe.terms['kill' + foe.range] ? 'kill' : 'pen') + foe.range;
  const terms = Object.entries(foe.terms).map(([k, w]) => {
    const [fa, fb] = bvSides(k, foe, mode, gun);
    return { k, w: w * (ab[k] ?? 1), sp: BV_PAIRS.map(p => bvSpec(k, p, foe.th)), fa, fb, need: Object.keys(foe.terms).indexOf(foe.need?.[k]) };
  });
  const cf = { foe, terms, idx: Object.fromEntries(terms.map((t, i) => [t.k, i])), gun, gates: foe.gates || [] };
  memo.set(key, cf);
  return cf;
}
// what one vehicle brings to a foe's duels, read once per ranking (side 0 the candidate, side 1 the opponent): its values
// x and their logs l (a ranking would take millions)
function bvVec(cf, v, side, stock) {
  const x = cf.terms.map(t => (side ? t.fb(v, false) : t.fa(v, stock)));
  return { x, l: Float64Array.from(x, y => (typeof y === 'number' && y > 0 ? Math.log(y) : NaN)) };
}

const bvGateT = (cf, k, va, vb, pair) => { const i = cf.idx[k]; return i == null ? null : bvT(cf.terms[i].sp[pair], va.x[i], vb.x[i], va.l[i] - vb.l[i]); };
// a gate changes the verdict after the sum (the page says why)
const BV_GATES = {
  // faster by more than 4.5% and climbing 15% better: it leaves a turn fight that goes wrong for it
  refuse: (cf, { x: a }, { x: b }, pair, v) => {
    const i = cf.idx.spd, j = cf.idx.climb;
    return v === 'adv' && a[i] > 0 && a[j] > 0 && b[i] > a[i] * 1.045 + 1e-9 && b[j] > a[j] * 1.15 + 1e-9 ? 'even' : v;  // 12 x 1.15 gives 13.799999999999999
  },
  // faster and climbing better beyond the even bands: no getting above it
  above: (cf, va, vb, pair, v) => (bvGateT(cf, 'spd', va, vb, pair) < 0 && bvGateT(cf, 'climb', va, vb, pair) < 0 ? 'dis' : v),
  // less than half its penetration at the style's range, where armor counts (front compared): from 8.7 a shaped charge's
  // millimetres and a dart's don't compare
  outgun: (cf, { x: a }, { x: b }, pair, v) => {
    const g = cf.idx[cf.gun], f = cf.idx.front;
    return a[f] !== undefined && b[f] !== undefined && a[g] != null && b[g] != null && a[g] < b[g] / 2 ? 'dis' : v;
  },
};

// D: the weighted mean of the terms compared. Known: the measured stats known on both sides plus every capability; under
// 60% of the weight compared: not enough data (na). full: also the terms, the strongest first (the reasons).
function bvCore(cf, pair, va, vb, full) {
  const ts = cf.terms, terms = full ? [] : null;
  let sum = 0, sw = 0, all = 0, known = 0;
  for (let i = 0; i < ts.length; i++) {
    const tm = ts[i], sp = tm.sp[pair];
    let a = va.x[i], b = vb.x[i], ld = va.l[i] - vb.l[i];
    if (sp.skip || a === undefined || b === undefined) continue;  // not compared: out of the coverage too
    if (tm.need >= 0 && !(va.x[tm.need] > 0) && !(vb.x[tm.need] > 0)) continue;  // nothing on either side for it to act on: likewise
    if (tm.need >= 0) {  // a side's flares act on the other side's IR missiles only
      if (!(vb.x[tm.need] > 0)) a = 0;
      if (!(va.x[tm.need] > 0)) b = 0;
    }
    all += tm.w;
    if (tm.k === 'front' && a && b) {  // each gun against the other's front
      const x = a[0] / b[1];
      b = b[0] / a[1];
      a = x;
      ld = Math.log(a) - Math.log(b);
    }
    const t = bvT(sp, a, b, ld);
    if (t !== null || sp.cap) known += tm.w;
    if (t === null) continue;
    sum += tm.w * t;
    sw += tm.w;
    if (full) terms.push({ k: tm.k, w: tm.w, t, a, b });
  }
  if (full) terms.sort((x, y) => Math.abs(y.w * y.t) - Math.abs(x.w * x.t));
  if (!sw || known < .6 * all - 1e-9) return { v: 'na', D: 0, terms, gate: null };
  const D = sum / sw;
  let v = D >= .2 - 1e-9 ? 'adv' : D <= -.2 + 1e-9 ? 'dis' : 'even', gate = null;  // an exact 0.2 can add up to 0.19999999999999998
  for (const g of cf.gates) {
    const to = BV_GATES[g](cf, va, vb, pair, v);
    if (to !== v) { v = to; gate = g; }
  }
  return { v, D, terms, gate };
}

// one duel, A the candidate and B the opponent; ctx {mode: 0 AB, 1 RB, 2 SB, stock: A stock}
function bvDuel(A, B, foe, { mode = 1, stock = false } = {}) {
  const cf = bvCompile(foe, mode, A.c);
  return bvCore(cf, bvPair(A.c, bvJet(A), bvJet(B)), bvVec(cf, A, 0, stock), bvVec(cf, B, 1), true);
}

// AI support units, game-mode copies nobody owns (tutorial, race, event, missile test, arena, football, cup, snowball),
// and the launchers of a SAM system, fought through its own vehicle; "_arena_m" is the Arena-M protection system of two
// tree tanks
const BV_UNPLAYED = /killstreak|^nt_|^uav_|^ucav_|tutorial|_race|_event|missile_test|_arena$|football|yt_cup|snowball|_launcher$/;
// who can be ranked or met; removed vehicles (ra 5) stay unless removed is false: players still own them
const bvPool = (vehicles, { removed = true } = {}) =>
  vehicles.filter(v => !v.h && v.ra !== 6 && !v.mod && !BV_UNPLAYED.test(v.id) && (removed || v.ra !== 5));

const bvK = (...ks) => v => ks.includes(v.k);
const bvRo = (...rs) => v => rs.some(r => v.ro?.includes(r));
const bvHas = (...ks) => v => ks.some(k => bvVal(v, k) > 0);
const bvGround = v => v.c === 'ground', bvNaval = v => v.c === 'boat' || v.c === 'ship', bvSpaa = v => bvGround(v) && v.k === 'SPAA';
// gl: the main weapon fires guided missiles only; when none of them is anti-ground (SAMs), it fights no ground vehicle
const bvFightsGround = v => bvGround(v) && !(v.s?.gl && !(bvVal(v, 'atg') > 0));
// reach (m): a guided weapon's range, else how close guns (3000 m), bombs and rockets (2000 m) must come
const bvSpaaReach = o => bvVal(o, 'sam') || 3000;
const bvGroundReach = o => (bvSpaa(o) ? bvSpaaReach(o) : bvVal(o, 'atr') || 2000);
const BV_WIDE = { reach: { e: 500, d: 2000 } };

// The play styles: who is a candidate (cand(v, stock)), whom it meets on which stats (weights; need: a term compared only
// when either side has the stat it acts on, one of the same terms), the mission part (m: its share of the score, from
// percentiles among the style's candidates of the window), the modes it is offered in, the notes the page shows.
const BV_STYLES = {
  air: [
    { id: 'turn', cand: bvK('fighter'), foes: [{ is: bvK('fighter'), terms: { turn: 1.5, wl: 1, pwr: .6, fg: .5, climb: .4, roll: .3, irq: .3, spd: .2, cm: .2 },
      need: { cm: 'irq' }, gates: ['refuse'] }] },
    { id: 'bnz', cand: bvK('fighter'), foes: [{ is: bvK('fighter'), terms: { spd: .9, climb: .8, fg: .8, roll: .6, vne: .6, pwr: .4, ceil: .3, turn: .1, wl: .1 }, gates: ['above'] }] },
    { id: 'energy', cand: bvK('fighter'), foes: [{ is: bvK('fighter'), terms: { pwr: 1, climb: .9, spd: .6, turn: .5, roll: .4, fg: .4, wl: .3 } }] },
    // bombers, and the attack aircraft that are no strike fighters (no radar missile)
    { id: 'hunter', cand: bvK('fighter'), foes: [{ is: v => v.k === 'bomber' || (v.k === 'assault' && !(bvVal(v, 'rm') > 0)), terms: { spd: 1, climb: 1, ceil: .5 } }],
      mission: { fg: 1, roll: .2 }, m: .4 },
    // close air support, in ground battles: aircraft at their ground-battle BR; in stock, what the stock aircraft carries
    { id: 'cas', brField: 'bt', cand: (v, stock) => v.k === 'assault' || ((v.k === 'fighter' || v.k === 'bomber') && (bvVal(v, 'pay', stock) >= 500 || bvVal(v, 'atg', stock) > 0)),
      foes: [{ is: bvSpaa, terms: { reach: 1 }, reach: [(v, stock) => bvVal(v, 'atr', stock) || 2000, bvSpaaReach], th: BV_WIDE },
        { is: bvK('fighter'), brField: 'bt', terms: { spd: .8, climb: .6, turn: .4, cm: .4, roll: .3, def: .3, fg: .3 } }],
      mission: { pay: 1, atg: .5, atr: .5, atq: .3, fg: .3 }, m: .5, notes: ['abApprox'] },
    { id: 'bomber', cand: bvK('bomber'), foes: [{ is: bvK('fighter'), terms: { spd: 1, ceil: .7, def: .6, climb: .5, crew: .4 } }], mission: { pay: 1 }, m: .5 },
    { id: 'missile', cand: (v, stock) => bvJet(v) && (bvVal(v, 'ir', stock) > 0 || bvVal(v, 'rm', stock) > 0), foes: [{ is: v => bvJet(v) && v.k === 'fighter',
      terms: { tw: .8, irq: .6, rmr: .6, rad: .6, cm: .6, spd: .6, rmq: .5, rwr: .5, climb: .5, turn: .5, ir: .3, rm: .3, fg: .2 }, need: { cm: 'ir' } }] },
  ],
  // in ground battles, at the helicopter's BR (which ground vehicles share); their manoeuvre stats are placeholders
  heli: [
    { id: 'hatgm', cand: bvHas('atg'), foes: [{ is: bvGround, terms: { reach: 1 }, reach: [(v, stock) => bvVal(v, 'atr', stock), bvGroundReach], th: BV_WIDE }],
      mission: { atg: .6, atq: .6, atp: .5, th: .4, cm: .3, rwr: .3, spd: .3, climb: .2 }, m: .5 },
    // rkt: unguided rockets and bombs (pay counts the guided missiles too)
    { id: 'hrocket', cand: bvHas('rkt'), foes: [{ is: bvSpaa, terms: { reach: 1 }, reach: [() => 2500, bvSpaaReach], th: BV_WIDE }],
      mission: { rkt: .8, fg: .5, cm: .6, spd: .5 }, m: .5 },
    // no helicopter carries a radar missile: no warning receiver
    { id: 'hair', cand: bvHas('ir', 'fg'), foes: [{ is: v => v.c === 'heli', terms: { ir: 1, irq: .5, cm: .7, fg: .5, th: .4, spd: .3, climb: .2 }, need: { cm: 'ir' } }] },
  ],
  ground: [
    // missile carriers don't brawl. self: whom a style meets also duels in it (with every vehicle listed)
    { id: 'brawl', cand: bvRo('medium_tank', 'heavy_tank'), foes: [{ is: v => bvGround(v) && !v.s?.gl, self: true, range: 500, gates: ['outgun'],
      terms: { rel: .8, trav: .7, cal: .7, stab: .6, pen500: .6, crew: .4, pw: .3, rev: .3, front: .15 } }] },
    { id: 'snipe', cand: bvRo('medium_tank', 'heavy_tank', 'tank_destroyer'), foes: [{ is: bvFightsGround, self: true, range: 2000, turret: true, gates: ['outgun'],
      terms: { kill2000: 1, vel: .7, dep: .7, rev: .6, rf: .6, th: .5, rel: .5, trav: .3, front: .1 } }] },
    { id: 'flank', cand: bvRo('light_tank', 'medium_tank'), foes: [{ is: bvFightsGround, self: true, terms: { pw: 1, spd: .7, stab: .7, trav: .6, rev: .5, rel: .5, side: .4 } }] },
    { id: 'ambush', cand: bvRo('tank_destroyer'), foes: [{ is: bvFightsGround, self: true, range: 1000, gates: ['outgun'],
      terms: { kill1000: 1, cal: .8, rev: .6, atr: .6, rf: .5, th: .5, rel: .5, trav: .2, front: .1 } }] },
    // with every vehicle listed, one without AA weapons reaches no aircraft
    { id: 'spaa', cand: bvSpaa, foes: [{ is: v => v.c === 'air' || v.c === 'heli', brField: 'bt', terms: { reach: 1 },
      reach: [(v, stock) => bvVal(v, 'sam', stock) || (bvVal(v, 'aab', stock) > 0 ? 3000 : 0), o => bvVal(o, 'atr') || 2000], th: BV_WIDE }],
      mission: { rad: .8, aab: .7, sam: .6, vert: .6, trav: .4, pw: .3 }, m: .5, notes: ['armor', 'abApprox'] },
  ],
  // boats and ships share battles
  naval: [
    // fa: every gun's firepower (a boat brawls with its secondary and machine-gun groups too)
    { id: 'nbrawl', cand: v => v.c === 'boat', foes: [{ is: bvNaval, terms: { fa: 1, crew: .7, cal: .6, disp: .5, spd: .4 } }], notes: ['navalArmor'] },
    // boats and destroyers; a smaller boat is harder to hit
    { id: 'ntorp', cand: v => bvVal(v, 'tor') > 0 && (v.c === 'boat' || !!v.ro?.includes('destroyer')),
      foes: [{ is: bvNaval, terms: { spd: .9, tor: .8, torr: .8, disp: .5, fm: .3, crew: .3 }, th: { disp: { dir: -1 } } }] },
    { id: 'ndd', cand: bvRo('destroyer'), foes: [{ is: bvNaval, terms: { fm: .9, spd: .7, crew: .6, tor: .4 } }] },
    { id: 'nrange', cand: v => v.c === 'ship' && !v.ro?.includes('destroyer'), foes: [{ is: bvNaval, terms: { cal: 1, fm: .8, crew: .7, disp: .5, spd: .3 } }] },
  ],
};
for (const [type, list] of Object.entries(BV_STYLES)) for (const s of list) {
  s.modes ||= type === 'naval' ? ['ab', 'rb'] : ['ab', 'rb', 'sb'];  // no Simulator naval battles
  s.notes ||= type === 'ground' ? ['armor'] : [];
  for (const f of s.foes) f.gates ||= [];
}
const bvStyleOf = (type, id) => BV_STYLES[type].find(s => s.id === id);

// the candidate's percentile among the population for each mission stat (ties count half, unknown ones are dropped),
// weighted, -1..1; null when nothing could be measured
function bvMission(x, popx, mw) {
  let sum = 0, sw = 0;
  x.forEach((xi, i) => {
    if (xi == null) return;
    let n = 0, below = 0, same = 0;
    for (const p of popx) {
      const y = p.x[i];
      if (y == null) continue;
      n++;
      if (y < xi) below++; else if (y === xi) same++;
    }
    if (n) { sum += mw[i] * (below + same / 2) / n; sw += mw[i]; }
  });
  return sw ? 2 * sum / sw - 1 : null;
}

const BV_NEAR = [-3, -2, -1, 0, 1, 2, 3];
// The ranking of a style (type, style: ids; br: one BR, null: every BR, each vehicle in its own window). net = (wins -
// losses) / duels with a verdict, the mean over the opponent groups that have one (close air support's few SPAA weigh
// as much as its many fighters); score = (1 - m) x net + m x mission. Rows of removed vehicles stay: the page's
// switches hide rows, they never change a score. Highest score first, then the larger mean D.
function bvRank({ vehicles, type, style, mode = 1, br = null, stock = false, onlyStyle = true }) {
  const st = bvStyleOf(type, style), cats = BV_TYPES[type], pool = bvPool(vehicles);
  const step = (v, field) => { const b = bvBr(v, mode, field); return b == null ? null : Math.round(b * 3); };
  // items by BR step; a window is the 7 steps around one, gathered once per step
  const windows = (items, field) => {
    const by = new Map(), near = new Map();
    for (const x of items) {
      const s = step(x.o, field);
      if (s == null) continue;
      if (!by.has(s)) by.set(s, []);
      by.get(s).push(x);
    }
    return s => near.get(s) || near.set(s, BV_NEAR.flatMap(d => by.get(s + d) || [])).get(s);
  };
  const foes = st.foes.map(foe => {
    const cf = bvCompile(foe, mode, cats[0]);
    return { foe, cf, near: windows(pool.filter(foe.is).map(o => ({ o, vb: bvVec(cf, o, 1), jet: bvJet(o) })), foe.brField) };
  });
  const keys = Object.keys(st.mission || {}), ab = (mode === 0 && BV_AB[cats[0]]) || {}, mw = keys.map(k => st.mission[k] * (ab[k] ?? 1));
  const pop = windows(pool.filter(v => cats.includes(v.c) && st.cand(v, stock)).map(o => ({ o, x: keys.map(k => bvVal(o, k, stock)) })), st.brField);
  const at = br == null ? null : Math.round(br * 3), rows = [];
  for (const v of pool) {
    const s = cats.includes(v.c) && (!onlyStyle || st.cand(v, stock)) ? step(v, st.brField) : null;
    if (s == null || (at != null && s !== at)) continue;
    let w = 0, e = 0, l = 0, na = 0, sumD = 0, nets = 0, groups = 0, off = false;
    const jet = bvJet(v);
    for (const { foe, cf, near } of foes) {
      if (foe.self && !foe.is(v)) { off = true; continue; }
      const va = bvVec(cf, v, 0, stock), w0 = w, e0 = e, l0 = l;
      for (const x of near(s)) {
        if (x.o === v) continue;
        const r = bvCore(cf, bvPair(v.c, jet, x.jet), va, x.vb, false);
        if (r.v === 'na') { na++; continue; }
        if (r.v === 'adv') w++; else if (r.v === 'dis') l++; else e++;
        sumD += r.D;
      }
      const n = w - w0 + e - e0 + l - l0;
      if (n) { nets += (w - w0 - (l - l0)) / n; groups++; }
    }
    const k = w + e + l, net = groups ? nets / groups : 0, mission = keys.length ? bvMission(keys.map(key => bvVal(v, key, stock)), pop(s), mw) : null;
    // a part with nothing to measure leaves the whole score to the other
    const score = k && mission != null ? (1 - st.m) * net + st.m * mission : k ? net : mission ?? 0;
    rows.push({ v, score, net, mission, w, e, l, na, meanD: k ? sumD / k : 0, n: k + na, ...(off && { off }) });
  }
  return rows.sort((a, b) => (Math.abs(a.score - b.score) > 1e-12 ? b.score - a.score : b.meanD - a.meanD));
}

// a row's opponents, each with its duel (the best for the row first): computed when the row opens. ctx: bvRank's arguments
function bvMatchups(row, { vehicles, type, style, mode = 1, stock = false }) {
  const st = bvStyleOf(type, style), br = bvBr(row.v, mode, st.brField), pool = bvPool(vehicles), out = [];
  for (const foe of st.foes) for (const o of pool) {
    if (o !== row.v && foe.is(o) && (!foe.self || foe.is(row.v)) && bvInWindow(br, bvBr(o, mode, foe.brField))) out.push({ o, res: bvDuel(row.v, o, foe, { mode, stock }) });
  }
  return out.sort((a, b) => b.res.D - a.res.D);
}
