"""Guided weapon stats the Best vehicles duels read (web/duel.js): air-to-air missiles, anti-ground guided weapons, SAMs
and torpedoes, from the weapons page's items (armament.build_armament's index) and what a vehicle fires: the weapons of
its presets (aircraft, helicopters, ships) or its ammunition and the launchers that have none (ground vehicles). No file
is read or written here.

Every key is a capability (spec section 4): written only when the vehicle has it; su the stock values that differ, 0
when the stock vehicle lacks it. A missile carrier (ground_stats' gl, set here too when the main weapon is a launcher am
leaves out: the M113A1 (TOW)'s) has no shell, so it gets vel here, a measured stat: the fastest missile its main weapon
fires (su None: none in stock). Stock: the presets in details _sp (every preset
when there is no such list) and, for ground vehicles, the default ammo sets and the free ammo modifications in details
_sm, with their own fitted weapons. Ground vehicles also bring details _gw (their launchers without an ammo set, [file
key, rounds], one list per fitted set: their own, then that of each modification that replaces it, counted upgraded
only) and _ml (ammo modification -> the rounds a spawn may carry). The four keys are dropped from details, also from a
vehicle whose data fails here: that one is logged and gets no guided key."""
from __future__ import annotations

import re

from .builder import log, main_gun

KEYS = {"air": ("ir", "irq", "rm", "rmq", "rmr", "atg", "atr", "atq"), "heli": ("ir", "irq", "atg", "atr", "atp", "atq"),
        "ground": ("atg", "atr", "atp", "atq", "sam"), "boat": ("tor", "torr"), "ship": ("tor", "torr")}
REACH_CAP = 10000  # m: an item's rng is how far it flies, not how far it is launched from
GBOMB_REACH = 8000  # m: a guided bomb without a range


def _sam_reach(it: dict) -> float:
    """A SAM's range, but an IR SAM that locks on before launch reaches no farther than its seeker locks on from any side
    (most fly 10 km and lock on from behind at 11-12 km); one with inertial guidance locks on in flight (IRIS-T SLM)."""
    rng = it.get("rng") or 0
    return min(it.get("aa") or it.get("lk") or rng, rng) if it.get("g") == "ir" and not it.get("ins") else rng


VALUES = {  # stat: (kind of item, its value for one item), or a count of rounds when there is no value
    "ir": ("ir", None), "irq": ("ir", lambda i: 1 + bool(i.get("aa")) + bool(i.get("aa") and i.get("ccm"))),
    "rm": ("rm", None), "rmq": ("rm", lambda i: 2 if i.get("act") else 1),
    "rmr": ("rm", lambda i: round((i.get("rng") or 0) / 1000, 1)),
    "atg": ("ag", None), "atr": ("ag", lambda i: min(i.get("rng") or (GBOMB_REACH if i["c"] == "gbomb" else 0), REACH_CAP)),
    "atp": ("ag", lambda i: i.get("pen") or 0), "atq": ("ag", lambda i: 2 if i.get("ff") else 1),
    "sam": ("sam", _sam_reach), "tor": ("tor", None), "torr": ("tor", lambda i: i.get("rng") or 0),
}


def _kind(it: dict) -> str:
    c, g = it.get("c"), it.get("g")
    # an anti-radiation missile homes on ground radars, even one with an air-to-air bullet type (Sidearm); an AA.20 or an
    # X-4 is steered by hand, not by radar
    if g == "arm" or (c == "aam_radar" and g == "mclos"):
        return ""
    if c in ("atgm", "agm", "gbomb"):
        return "" if it.get("ship") else "ag"  # anti-ship: its seeker locks on ships only
    return {"aam_ir": "ir", "aam_radar": "rm", "sam": "sam", "torpedo": "tor"}.get(c, "")


def _best(loadouts: list) -> dict:
    """The best of each stat over loadouts, each [(rounds, [the items they can be])]: one preset, or a ground vehicle's
    whole ammunition."""
    out: dict = {}
    for loads in loadouts:
        s: dict = {}
        for n, its in loads:
            for k, (kind, value) in VALUES.items():
                mine = [i for i in its if _kind(i) == kind]
                if mine:
                    s[k] = s.get(k, 0) + n if value is None else max(s.get(k, 0), *map(value, mine))
        for k, x in s.items():
            out[k] = max(out.get(k, 0), x)
    return out


def guided_stats(vehicles: list, details: dict, items: dict, by_file: dict, pods: dict | None = None) -> None:
    """items: armament id -> item (a ground vehicle's ammo sets name them); by_file: weapon file key -> the items it
    fires, with that file's own stats; pods: a container's key -> (the key of what it holds, how many)."""
    pods = pods or {}

    def fired(key: str, n: int) -> tuple:
        key, per = pods.get(key, (key, 1))
        return n * per, by_file.get(key) or by_file.get(re.sub(r"(_default|_\d+)$", "", key)) or []

    def shot(o: dict) -> list:
        """The items an ammo set fires; a SAM fired as an ATGM (ADATS) is an ATGM too, with the set's shaped charge."""
        its = [items[b.lower()] for b in o.get("b", ()) if b.lower() in items]
        if any(t.startswith("atgm") for t in o.get("t", ())):
            pen = ((o.get("s") or {}).get("pc") or [[0, 0]])[0][1]
            its += [{**i, "c": "atgm", "pen": pen} for i in its if i["c"] == "sam"]
        return its

    def ammo(am: list, keep, limits: dict) -> list:
        """Each gun or launcher counts its rounds once, whatever it fires; its missiles no more than a spawn may carry
        (the T-90A's gun holds 43 rounds, 28 of them missiles at most)."""
        out = []
        for g in am:
            sets = [(o["id"], shot(o)) for o in g["opts"] if keep(o)]
            caps = [limits.get(m) for m, its in sets if any(_kind(i) == "ag" for i in its)]
            n = g["cap"] * g["n"]
            out.append((min(n, sum(caps)) if caps and all(caps) else n, [i for _, its in sets for i in its]))
        return out

    for v in vehicles:
        d = details.get(v["id"]) or {}
        sp, sm, ml, gw = d.pop("_sp", None), d.pop("_sm", ()), d.pop("_ml", {}), d.pop("_gw", None)
        try:
            sm, fitted = set(sm), [[fired(k, n) for k, n in ws] for ws in gw or [[]]]  # the own set first
            if v["c"] == "ground":
                official = ammo(d.get("am", []), lambda o: not o.get("x"), ml)
                up = [official + ws for ws in fitted]
                stock = [ammo(d.get("am", []), lambda o: not o["id"] or o["id"] in sm, ml) + fitted[0]]
            else:
                up = [[fired(k, n) for k, n in p["w"]] for p in d.get("pr", [])]
                stock = [lo for p, lo in zip(d.get("pr", []), up) if sp is None or p["id"] in sp]
            best, st = _best(up), _best(stock)
            s = {k: best[k] for k in KEYS.get(v["c"], ()) if best.get(k)}
            if s:
                v.setdefault("s", {}).update(s)
                su = {k: st.get(k, 0) for k in s if st.get(k, 0) != s[k]}
                if su:
                    v.setdefault("su", {}).update(su)
            if v["c"] == "ground":  # what its main weapon fires, normally and in stock
                main = main_gun(d.get("am", []))
                fire = ([[i for o in main["opts"] if keep(o) for i in shot(o)]
                         for keep in (lambda o: not o.get("x"), lambda o: not o["id"] or o["id"] in sm)] if main else
                        [[i for ws in fitted for _, its in ws for i in its], [i for _, its in fitted[0] for i in its]])
                if not main and any(map(_kind, fire[0])):  # its main weapon a launcher am leaves out: M113A1 (TOW)
                    v.setdefault("s", {})["gl"] = 1
                if (v.get("s") or {}).get("gl") and "vel" not in v["s"]:  # no shell: its fastest missile instead
                    up_v, st_v = (round(max((i.get("v") or 0 for i in its if _kind(i)), default=0)) for its in fire)
                    if up_v:
                        v["s"]["vel"] = up_v
                        if st_v != up_v:
                            v.setdefault("su", {})["vel"] = st_v or None  # None: no missile in stock, a measured stat
        except (AttributeError, TypeError, KeyError, ValueError, IndexError) as e:
            log(f"  {v['id']}: no guided weapon stats: {type(e).__name__}: {e}")
