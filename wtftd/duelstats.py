"""Stats the Best vehicles duels read (web/duel.js), derived from what build_vehicles has already loaded: a vehicle's
ammo groups (details am), its systems (details sy; sy.su: what a stock vehicle has instead), its modifications in the
economy table (wpcost) and its unit file. Files are only read, through the builder (guns, presets, containers and
radars by its WeaponCache); none is written here.

Each *_stats function returns (s, su) additions for the vehicle's record: a key only when the vehicle has the thing,
su the stock values that differ: 0 when a stock vehicle lacks a capability the upgraded one has, None (unknown) when it
lacks a measured stat (spec section 4)."""
from __future__ import annotations

import re

from .builder import (_NO_PEN, _children, _linear, _mod_effects, _numval, _weapons, aslist, basename, br_from, bullet_mods,
                      first_str, gun_rounds, main_gun, num)

NO_VEL = ("atgm", "sam") + _NO_PEN  # bullet types: guided missiles (their reach is atr or sam), rounds that pierce nothing
PEN_AT = (500, 1000, 2000)  # m: the three values of pen
FORWARD = ("machine gun", "cannon", "additional gun")  # triggers of forward guns: fitted, gondolas, gun pods
PAYLOAD = ("bombs", "guided_bombs", "rockets", "torpedoes", "mines", "nuke", "agm", "atgm")  # weapons.json categories


def stock_shell(mod_id: str, wp_mods: dict) -> bool:
    """A shell a stock vehicle has: its default set, or an ammo modification that is free and needs nothing first (tier
    0, no cost, no reqModification). A researched shell needs its "<shell>_ammo_pack"."""
    m = wp_mods.get(mod_id) if mod_id else {}
    return isinstance(m, dict) and not any(m.get(k) for k in ("tier", "value", "costGold", "reqExp", "reqModification"))


def search_radar_km(sy: dict) -> float | None:
    """The longest range of the radars that search (radar_summary's ro s, or st: search and track), km; not an IRST, a
    TV sight or a radar warning receiver (esm)."""
    r = max((e[2].get("r") or 0 for e in sy.get("se") or () if e[1] == "radar" and e[2].get("ro") in ("s", "st")
             and e[2].get("k", "radar").startswith("radar")), default=0)
    return round(r / 1000, 1) if r else None


def gun_burst(weapons: list, wc) -> float:
    """kg/s the guns among these weapons fire, one barrel per Weapon block: shots/s (the Weapon's own shotFreq, else its
    gun file's) x the mean projectile mass of the gun's default belt. Dummies and missile or rocket launchers: none."""
    kg = 0.0
    for w in weapons:
        gun = (wc.get(first_str(w.get("blk"))) if first_str(w.get("blk")) and not w.get("dummy") else None) or {}
        masses = [_numval(b.get("mass")) or 0 for b in aslist(gun.get("bullet")) if isinstance(b, dict)]
        if gun_rounds(gun) and masses:
            kg += (_numval(w.get("shotFreq")) or _numval(gun.get("shotFreq")) or 0) * sum(masses) / len(masses)
    return kg


def preset_is_stock(preset: dict, udata: dict, wp_mods: dict | None = None) -> bool:
    """A weapon preset (build_vehicles' pr) a stock vehicle has: neither it (req) nor a slot preset it uses (s, the
    unit's WeaponSlots) needs a modification but free ones (stock_shell on the vehicle's wpcost modifications wp_mods:
    the hidden ship_torpedoes every naval torpedo preset needs). Official presets only: free slot presets that only
    presets needing a modification use are not counted (spec section 10, call 14)."""
    ws = udata.get("WeaponSlots") if isinstance(udata.get("WeaponSlots"), dict) else {}
    slots = {str(sl.get("index")): aslist(sl.get("WeaponPreset")) for sl in aslist(ws.get("WeaponSlot"))
             if isinstance(sl, dict)}
    used = [p for k, name in (preset.get("s") or {}).items() for p in slots.get(k, ())
            if isinstance(p, dict) and p.get("name") == name]
    reqs = aslist(preset.get("req")) + [r for p in used for r in aslist(p.get("reqModification"))]
    return all(stock_shell(r, wp_mods or {}) for r in reqs)


def _store(blk: str, wc, catalog: dict) -> tuple[str, float]:
    """(weapons.json category, kg) of what one weapon holds: its catalog entry (a pod with its rounds), else a rack of
    pods: its own mass and theirs."""
    e = catalog.get(basename(blk))
    if e:
        return e.get("c", ""), e.get("m") or 0
    d = wc.get(blk) or {}
    if not d.get("container") or not first_str(d.get("blk")):
        return "", 0
    c, kg = _store(first_str(d["blk"]), wc, catalog)
    return c, (_numval(d.get("mass")) or 0) + (num(d.get("bullets"), 1) or 1) * kg


def _loadout(weapons: list, wc, catalog: dict, forward: tuple) -> tuple[float, float, int, float]:
    """(forward guns' kg/s, kg of ground ordnance, countermeasure charges, kg of unguided rockets and bombs) of these
    weapons."""
    pay = rkt = 0.0
    for w in weapons:
        blk = first_str(w.get("blk"))
        c, kg = _store(blk, wc, catalog) if blk and not w.get("dummy") else ("", 0)
        if c in PAYLOAD:
            kg = kg if "container" in blk.lower() else kg * (num(w.get("bullets"), 1) or 1)  # a pod or a rack: one
            pay += kg
            if c in ("bombs", "rockets"):
                rkt += kg
    return (gun_burst([w for w in weapons if first_str(w.get("trigger")) in forward and not w.get("schraegeMusikAngle")], wc),
            pay, sum(num(w.get("bullets")) for w in weapons if first_str(w.get("trigger")) == "countermeasures"), rkt)


def fitted_sets(udata: dict, mods) -> list:
    """The vehicle's fitted weapons (builder._weapons), its own first, then those of each modification it can research
    (mods) that replaces them (effects commonWeapons: the Yak-9UT's N-37, the Eurofighter's flares, a boat's gun)."""
    return [_weapons(udata)] + [_weapons({**udata, "commonWeapons": e["commonWeapons"]}) for e in _mod_effects(udata, mods)
                                if isinstance(e.get("commonWeapons"), dict)]


def _fsm_pairs(node):
    """(transceiver, signal) of each block of a radar's fsms that sets both, at any depth."""
    for b in _children(node):
        t, s = b.get("setTransiver"), b.get("setSignal")
        if isinstance(t, dict) and isinstance(s, dict):
            yield first_str(t.get("transiver")), first_str(s.get("signal"))
        yield from _fsm_pairs(b)


def air_range(d: dict | None, r: float) -> float:
    """A radar's range against aircraft, m (without its file: r, its summary's): its longest transceiver but those its
    fsm sets only with signals that cannot see aircraft (aircraftAsTarget false: sea or ground search); 0 when none of
    its signals can (the Buccaneer's)."""
    if not isinstance(d, dict):
        return r
    sig = d.get("signals") if isinstance(d.get("signals"), dict) else {}
    air = {k for k, s in sig.items() if isinstance(s, dict) and s.get("aircraftAsTarget", True) is not False}
    if sig and not air:
        return 0
    pairs = list(_fsm_pairs(d.get("fsms")))
    surface = {t for t, _ in pairs} - {t for t, s in pairs if s in air}
    tr = d.get("transivers") if isinstance(d.get("transivers"), dict) else {}
    return max((_numval(t.get("range")) or 0 for k, t in tr.items() if isinstance(t, dict) and k not in surface), default=0)


def _air(cat: str, loads: list, sy: dict, wc) -> dict:
    fg, pay, cm, rkt = (max(x) for x in zip(*loads))
    nv = sy.get("nv") or {}
    se = [[k, kind, {**sm, "r": air_range(wc.get(f"gameData/sensors/{k}.blk"), sm.get("r") or 0)} if kind == "radar" else sm]
          for k, kind, sm in sy.get("se") or ()]  # an aircraft's radar file is gameData/sensors/<its key>.blk
    out = {"fg": round(fg, 1), "pay": round(pay, 1), "cm": cm, "rad": search_radar_km({"se": se}) or 0,
           "rwr": int(any(e[1] == "rwr" for e in sy.get("se") or ()))}
    if cat == "heli":
        out["th"] = int("t" in ((nv.get("g") or [""])[0], (nv.get("s") or [""])[0]))
        out["rkt"] = round(rkt, 1)
    return out


def air_stats(cat: str, udata: dict, wc, presets: list, catalog: dict, sy: dict, lim: dict, mods=(),
              wp_mods: dict | None = None) -> tuple[dict, dict]:
    """An aircraft's or a helicopter's: fg  forward guns' burst mass with its best preset, kg/s (fitted guns, guns in
    presets, gun pods; a helicopter's chin gun and flexible forward guns, gunner0 to gunner2, too: no helicopter has
    door guns); pay  its heaviest preset of ground ordnance, kg (bombs, rockets and their pods, torpedoes, mines,
    air-to-ground missiles; not air-to-air missiles, fuel tanks, targeting or gun pods); rkt  (helicopters, internal)
    its heaviest preset of unguided rockets and bombs, kg (pay without the guided weapons, which atg and the others
    count); cm  countermeasure charges, fitted and the most in pods; rwr  a radar warning receiver; rad  search radar
    range against aircraft (km, air_range); th  (helicopters) a thermal gunner's or targeting sight; vne  (aircraft)
    dive limit, km/h indicated (swept-back wings'); def  (aircraft) defensive turrets. Upgraded: the best of
    its fitted sets (fitted_sets, mods: the modifications it can research) with each preset. Stock: its own fitted
    weapons, its stock presets (preset_is_stock, wp_mods: its wpcost modifications) and systems (sy.su). A preset's
    weapons are read from its file through wc."""
    sets = fitted_sets(udata, mods)
    forward = FORWARD + (("gunner0", "gunner1", "gunner2") if cat == "heli" else ())
    files = {p.get("name"): first_str(p.get("blk")) for p in aslist((udata.get("weapon_presets") or {}).get("preset"))
             if isinstance(p, dict)}
    carried = [(True, [])]  # (stock, weapons): nothing more, then each preset
    for p in presets:
        pdata = (wc.get(files[p["id"]]) if files.get(p["id"]) else None) or {}
        weapons = _weapons({"commonWeapons": pdata, "WeaponSlots": udata.get("WeaponSlots")})  # slot presets resolved
        carried.append((preset_is_stock(p, udata, wp_mods), weapons))
    loads = [(ok and not i, _loadout(fitted + weapons, wc, catalog, forward)) for i, fitted in enumerate(sets)
             for ok, weapons in carried]
    s = _air(cat, [lo for _, lo in loads], sy, wc)
    stock = _air(cat, [lo for ok, lo in loads if ok], {**sy, **(sy.get("su") or {})}, wc)
    su = {k: v for k, v in stock.items() if v != s[k]}
    if cat == "air":
        triggers = {first_str(w.get("trigger")) for w in sets[0] if not w.get("dummy")}
        s["def"] = sum(bool(re.fullmatch(r"gunner\d+", t)) for t in triggers)
        s["vne"] = round(_numval(lim.get("v")) or 0)
    return {k: v for k, v in s.items() if v}, su


def spaa_stats(udata: dict, wc, mods=()) -> tuple[dict, dict]:
    """An SPAA's aab: the burst mass of all its guns (gun_burst), kg/s, with the best of its fitted sets (fitted_sets);
    stock: its own."""
    aab = [round(gun_burst(ws, wc), 1) for ws in fitted_sets(udata, mods)]
    return ({"aab": max(aab)} if max(aab) else {}), ({"aab": aab[0]} if aab[0] != max(aab) else {})


def naval_stats(udata: dict, wc, sy: dict, mods=()) -> tuple[dict, dict]:
    """A boat's or a ship's: fm  its main battery's (trigger group primary) shell mass a minute, kg; fa  the same of all
    its guns (Gun brawler: a boat's 40 and 20 mm secondary and machine-gun groups do most of a brawl); both with the
    best of its fitted sets (fitted_sets); rad  search radar range (km). Stock: fm and fa with its own weapons (None:
    none fire); no modification changes a ship's radar."""
    sets = fitted_sets(udata, mods)
    fm = [round(60 * gun_burst([w for w in ws if first_str(w.get("triggerGroup")) == "primary"], wc)) for ws in sets]
    fa = [round(60 * gun_burst(ws, wc)) for ws in sets]
    s = {k: v for k, v in (("fm", max(fm)), ("fa", max(fa)), ("rad", search_radar_km(sy))) if v}
    return s, {k: x[0] or None for k, x in (("fm", fm), ("fa", fa)) if x[0] != max(x)}


def _rounds(o: dict, gun: dict | None) -> list:
    """An ammo option's rounds in its gun's file: every round of a belt, a rocket's flight in its "rocket" block (an
    option's s is its first round's shell); else that first round's type and speed (s.v), with the rocket of a
    launcher's file that has no ammo set (builder.unguided_launcher)."""
    block = (gun or {}).get(o["id"]) if o.get("id") else gun
    own = [b for b in aslist((block or {}).get("bullet")) if isinstance(b, dict)]
    return own or [{"bulletType": first_str(o.get("t")), "speed": (o.get("s") or {}).get("v"),
                    "rocket": (block or {}).get("rocket")}]


def _round_speed(b: dict) -> float | None:
    """A round's speed as the game's bullet card gives it, m/s: an unguided rocket's top speed (maxSpeed, else
    endSpeed), else the shell's muzzle velocity; None for the NO_VEL types."""
    if first_str(b.get("bulletType")).startswith(NO_VEL):
        return None
    r = b.get("rocket") if isinstance(b.get("rocket"), dict) else {}
    return _numval(r.get("maxSpeed")) or _numval(r.get("endSpeed")) or _numval(b.get("speed"))


def _ground(main: dict, sy: dict, keep, gun: dict | None) -> dict:
    out = {}
    shells = [o for o in main.get("opts", []) if keep(o)]
    curves = [o["s"]["pc"] for o in shells if (o.get("s") or {}).get("pc")]
    if curves:  # a shaped charge's or a missile's curve is flat; past a curve's last distance, its last value
        out["pen"] = [round(max(_linear(c, d) for c in curves)) for d in PEN_AT]
    vel = [v for o in shells for b in _rounds(o, gun) if (v := _round_speed(b))]
    if vel:
        out["vel"] = round(max(vel))
    if sy.get("el") and any(sy["el"]):  # [0, 0]: a fixed launcher (Swingfire, Striker) whose missile steers after launch
        out["dep"] = max(0, -sy["el"][0])  # BM-13N's rails rise 7 degrees at least: no depression
    if sy.get("stab"):
        out["stab"] = sum(sy["stab"][:2])  # vertical, horizontal
    if sy.get("rf"):
        out["rf"] = 2 if sy["rf"] == "laser" else 1
    if (sy.get("nv") or {}).get("g", [""])[0] == "t":
        out["th"] = 1
    rad = search_radar_km(sy)
    if rad:
        out["rad"] = rad
    return out


def ground_stats(am: list, sy: dict, wp_mods: dict, wc) -> tuple[dict, dict]:
    """A ground vehicle's main gun (builder.main_gun) and fire control: pen  best penetration at 500 / 1000 / 2000 m
    (mm, flat plate) of the shells it normally has (not the x ones), gun-launched missiles included; vel  the fastest
    of their rounds but guided missiles and rounds that pierce nothing (m/s, _round_speed; every round of a belt, in
    the gun's file p); dep  gun depression (deg); stab  stabilizer, 1 vertical, 2 two-plane; rf  rangefinder,
    1 optical, 2 laser; th  gunner's thermal sight; rad  search radar range (km). Internal, of the vehicle, never in
    su: gl  a missile carrier, every round its main gun normally has a guided missile (guided_stats gives its vel, and
    gl when the main weapon is a launcher am leaves out); else auto  an automatic gun, one barrel (Weapon block tube)
    firing a shot a second or more. Stock: the stock shells (stock_shell, bullet_mods) and the stock systems (sy.su)."""
    main = main_gun(am) or {}
    gun = wc.get(main["p"]) if main.get("p") else None
    s = _ground(main, sy, lambda o: not o.get("x"), gun)
    given = bullet_mods(wp_mods)  # a set its modification gives under another name is stock when that one is free
    free = lambda o: stock_shell(given.get(o["id"], o["id"]), wp_mods)
    stock = _ground(main, {**sy, **(sy.get("su") or {})}, free, gun)
    su = {k: stock.get(k, None if k in ("pen", "vel", "dep") else 0) for k in s}  # pen, vel, dep: measured stats
    rounds = [t for o in main.get("opts", []) if not o.get("x") for t in o.get("t") or [""]]
    if rounds and all(t.startswith(("atgm", "sam")) for t in rounds):
        s["gl"] = 1
    elif (main.get("sf") or 0) / (main.get("tubes") or 1) >= 1:  # no loader's pace: rel is a per-shot or magazine time
        s["auto"] = 1
    return s, {k: v for k, v in su.items() if v != s[k]}


def ground_battle_br(wp_entry: dict, br: list) -> list | None:
    """bt: an aircraft's BR in ground battles [AB, RB, SB]: RB and SB from the economy table's tank-battle ranks, each the
    aircraft's own when it has none; AB its own (the table has no such rank). None when it is br."""
    ranks = ("economicRankTankHistorical", "economicRankTankSimulation")
    bt = [br[0], *(br_from(wp_entry.get(k)) or b for k, b in zip(ranks, br[1:]))]
    return None if bt == br else bt
