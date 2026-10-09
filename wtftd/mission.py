"""Builds a user mission from an official test drive / test flight scenario.

The official mission is kept as-is (targets, triggers, imports of in-game templates);
only the player unit, its loadout and a few mission settings are changed.
"""
from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path

from . import blk

from .paths import DATA

ENVIRONMENTS = ["Day", "Morning", "Noon", "Evening", "Dusk", "Dawn", "Night"]
WEATHERS = ["clear", "good", "hazy", "thin_clouds", "cloudy", "cloudy_windy", "overcast", "poor", "rain", "thunder", "blind"]
MISSION_TYPES = ["singleMission", "testFlight"]

UNIT_DEFAULTS = {
    "tankModels": {"army": 1, "count": 1, "formation_type": "rows", "formation_div": 3,
                   "formation_step": [2.5, 2.0], "formation_noise": [0.1, 0.1], "uniqueName": "",
                   "attack_type": "fire_at_will"},
    "ships": {"army": 1, "count": 1, "formation_type": "rows", "formation_div": 3,
              "formation_step": [2.5, 2.0], "formation_noise": [0.1, 0.1], "uniqueName": "",
              "attack_type": "fire_at_will"},
    "armada": {"army": 1, "count": 1, "free_distance": 70.0, "floating_distance": 50.0,
               "minimum_distance_to_earth": 20.0, "altLimit": 6000.0, "attack_type": "fire_at_will",
               "skill": 4, "plane": {"wing_formation": "Diamond", "row_distances": 3.0, "col_distances": 3.0,
                                     "super_formation": "Diamond", "super_row_distances": 1.5,
                                     "super_col_distances": 1.5, "ai_skill": "NORMAL", "task": "FLY_WAYPOINT"}},
}


class MissionError(Exception):
    pass


def load_scenario(sid: str) -> dict:
    if not re.fullmatch(r"[a-z0-9_]+", sid or ""):
        raise MissionError("Invalid scenario id")
    path = DATA / "scenarios" / f"{sid}.json"
    if not path.exists():
        raise MissionError(f"Unknown scenario: {sid}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _as_list(v):
    return v if isinstance(v, list) else ([] if v is None else [v])


def _find_player(units: dict, wing: str):
    for block, entries in units.items():
        lst = _as_list(entries)
        for i, u in enumerate(lst):
            if isinstance(u, dict) and u.get("name") == wing:
                return block, i, u
    return None, None, None


def _remove_unit(units: dict, block: str, index: int):
    entries = units[block]
    if isinstance(entries, list):
        entries.pop(index)
        if not entries:
            del units[block]
    else:
        del units[block]


def _append_unit(units: dict, block: str, unit: dict):
    if block not in units:
        units[block] = unit
    elif isinstance(units[block], list):
        units[block].append(unit)
    else:
        units[block] = [units[block], unit]


def _strip_airfield_spawn(node, wing: str):
    """Removes spawnOnAirfield actions for the player (used for air starts)."""
    if isinstance(node, dict):
        for k in list(node):
            v = node[k]
            if k == "spawnOnAirfield":
                kept = [a for a in _as_list(v) if not (isinstance(a, dict) and wing in _as_list(a.get("objects")))]
                if not kept:
                    del node[k]
                else:
                    node[k] = kept if len(kept) > 1 else kept[0]
            else:
                _strip_airfield_spawn(v, wing)
    elif isinstance(node, list):
        for x in node:
            _strip_airfield_spawn(x, wing)


EDITABLE_BLOCKS = ("tankModels", "armada", "ships")
ATTACK_TYPES = ("fire_at_will", "return_fire", "hold_fire", "dont_aim")
_CLASS = re.compile(r"^[A-Za-z0-9_\-.]{1,120}$")


def _area_pos(m: dict, name) -> dict | None:
    a = (m.get("areas") or {}).get(name) if isinstance(name, str) else None
    try:
        x, y, z = (float(c) for c in a["tm"][3])
        return {"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)}
    except (TypeError, KeyError, IndexError, ValueError):
        return None


def _is_start_trigger(t: dict) -> bool:
    """Runs once when the mission starts, whatever the player does."""
    ev = t.get("events") or {}
    return not (t.get("conditions") or {}) and (not ev or "initMission" in ev) and "periodicEvent" not in ev


def _trigger_actions(m: dict):
    for name, t in (m.get("triggers") or {}).items():
        if isinstance(t, dict) and isinstance(t.get("actions"), dict):
            yield name, t, t["actions"]


def player_spawn(m: dict, wing: str) -> dict | None:
    """Where the player really appears when the scenario spawns them on a runway (spawnOnAirfield):
    the airfield's spawn point, heading down the runway."""
    airfields = {}
    for _, _, a in _trigger_actions(m):
        for af in _as_list(a.get("addAirfield")):
            if isinstance(af, dict) and af.get("runwayStart"):
                airfields[af["runwayStart"]] = af
    for _, t, a in _trigger_actions(m):
        if not _is_start_trigger(t):
            continue
        for sp in _as_list(a.get("spawnOnAirfield")):
            if not isinstance(sp, dict) or wing not in _as_list(sp.get("objects")):
                continue
            af = airfields.get(sp.get("runwayName"))
            start, end = _area_pos(m, (af or {}).get("runwayStart")), _area_pos(m, (af or {}).get("runwayEnd"))
            pos = _area_pos(m, (af or {}).get("spawnPoint")) or start
            if not pos:
                return None
            out = {**pos, "airfield": sp.get("runwayName")}
            if start and end:
                out["yaw"] = round(math.degrees(math.atan2(end["z"] - start["z"], end["x"] - start["x"])), 1)
                out["runway"] = [[start["x"], start["z"]], [end["x"], end["z"]]]
            return out
    return None


def teleports(m: dict) -> dict:
    """Units the scenario's triggers move to an area: {unit: {x, y, z, area, start}} where start
    means it happens as soon as the mission starts (else later, e.g. a periodic respawn)."""
    out = {}
    for _, t, a in _trigger_actions(m):
        start = _is_start_trigger(t)
        moves = [x for x in _as_list(a.get("unitMoveTo")) if isinstance(x, dict) and x.get("move_type") == "teleport"]
        moves += [x for x in _as_list(a.get("unitRespawn")) if isinstance(x, dict)]
        for mv in moves:
            pos = _area_pos(m, mv.get("target"))
            if not pos:
                continue
            for obj in _as_list(mv.get("object")):
                if isinstance(obj, str) and (obj not in out or start and not out[obj]["start"]):
                    out[obj] = {**pos, "area": mv.get("target"), "start": start}
    return out


def _strip_unit_moves(node, names: set):
    """Removes the given units from the scenario's teleports / respawns (they were moved in the editor)."""
    if isinstance(node, dict):
        for k in list(node):
            v = node[k]
            if k in ("unitMoveTo", "unitRespawn"):
                kept = []
                for a in _as_list(v):
                    if isinstance(a, dict) and (k == "unitRespawn" or a.get("move_type") == "teleport"):
                        objs = [o for o in _as_list(a.get("object")) if o not in names]
                        if not objs:
                            continue
                        a["object"] = objs if len(objs) > 1 else objs[0]
                    kept.append(a)
                if not kept:
                    del node[k]
                else:
                    node[k] = kept if len(kept) > 1 else kept[0]
            else:
                _strip_unit_moves(v, names)
    elif isinstance(node, list):
        for x in node:
            _strip_unit_moves(x, names)


def scenario_units(sid: str) -> dict:
    """Units of a scenario for the map editor (only those defined in the mission itself)."""
    m = load_scenario(sid)
    wing = ((m.get("mission_settings") or {}).get("player") or {}).get("wing")
    out = []
    for block, entries in (m.get("units") or {}).items():
        if block == "squad":
            continue
        for u in _as_list(entries):
            if not isinstance(u, dict) or not isinstance(u.get("tm"), list):
                continue
            try:
                x, y, z = (float(c) for c in u["tm"][3])
                fx, fz = float(u["tm"][0][0]), float(u["tm"][0][2])
            except (TypeError, ValueError, IndexError):
                continue
            props = u.get("props") or {}
            out.append({
                "name": u.get("name"), "block": block, "cls": u.get("unit_class", ""), "tpl": False,
                "x": round(x, 1), "y": round(y, 1), "z": round(z, 1), "yaw": round(math.degrees(math.atan2(fz, fx)), 1),
                "army": props.get("army", 0), "count": props.get("count", 1), "attack": props.get("attack_type", ""),
                "moves": bool(u.get("way")), "player": u.get("name") == wing,
                "edit": block in EDITABLE_BLOCKS and u.get("name") != wing,
                # delayed: not there at start, the scripts bring it in (or not) while the mission runs
                **({"runtime": 1} if props.get("isDelayed") and u.get("name") != wing else {}),
            })
    # units of the game templates the mission imports: can be removed / frozen / made passive or hunting
    tpl_path = DATA / "scenarios" / f"{sid}.units.json"
    level = (((m.get("mission_settings") or {}).get("mission") or {}).get("level") or "")
    level = level.replace("\\", "/").rsplit("/", 1)[-1].replace(".bin", "").lower()
    try:
        water = set(json.loads((DATA / "water.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        water = None  # unknown: keep every unit
    if tpl_path.exists():
        names = {u["name"] for u in out}
        try:
            tpl = json.loads(tpl_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            tpl = []
        for u in tpl:
            if water is not None and level not in water and u.get("block") == "ships" and u.get("runtime"):
                continue  # template ships the scenario only brings in on maps with water
            if isinstance(u, dict) and u.get("name") and u["name"] not in names:
                out.append({**u, "tpl": True, "moves": False, "player": False,
                            # real vehicles only (bombing targets / dummies stay scenery)
                            "edit": u.get("block") in EDITABLE_BLOCKS + ("air_defence", "tracked_vehicles", "wheeled_vehicles")
                            and u.get("army") == 2 and not str(u.get("cls", "")).startswith("dummy")})
    level = (((m.get("mission_settings") or {}).get("mission") or {}).get("level") or "")
    level = level.replace("\\", "/").rsplit("/", 1)[-1].replace(".bin", "").lower()
    me = next((u for u in out if u["player"]), None)
    tp = teleports(m)
    for u in out:
        if u["name"] in tp and not u["player"]:
            u["tp"] = tp[u["name"]]
    spawn = player_spawn(m, wing) if wing else None
    if not spawn and wing in tp and tp[wing]["start"]:
        spawn = {k: tp[wing][k] for k in ("x", "y", "z", "area")}
    return {"wing": wing, "units": out, "level": level, "army": (me or {}).get("army") or 1, "spawn": spawn,
            "areas": scenario_zones(sid, m)}


def scenario_zones(sid: str, m: dict) -> list:
    """The mission's areas for the editor: centre, size, heading, shape, and whether its scripts use it
    (where they spawn / respawn / send units)."""
    try:
        used = set(json.loads((DATA / "scenarios" / f"{sid}.zones.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        used = set()
    out = []
    for name, a in (m.get("areas") or {}).items():
        try:
            tm = a["tm"]
            x, y, z = (float(c) for c in tm[3])
            sx = math.hypot(float(tm[0][0]), float(tm[0][2]))
            sz = math.hypot(float(tm[2][0]), float(tm[2][2]))
            yaw = math.degrees(math.atan2(float(tm[0][2]), float(tm[0][0])))
        except (TypeError, KeyError, IndexError, ValueError):
            continue
        out.append({"name": name, "type": str(a.get("type", "")), "x": round(x, 1), "y": round(y, 1), "z": round(z, 1),
                    "sx": round(sx, 1), "sz": round(sz, 1), "yaw": round(yaw, 1), "used": name in used or name == "wtftd_spawn"})
    return out


def _yaw_tm(deg: float, x: float, y: float, z: float):
    t = math.radians(deg)
    return [[math.cos(t), 0.0, math.sin(t)], [0.0, 1.0, 0.0], [-math.sin(t), 0.0, math.cos(t)], [x, y, z]]


def apply_edits(m: dict, wing: str, edits: dict):
    """Map editor changes:
    units: {name: {cls, count, attack, behavior, remove, side, x, y, z}}   existing units of the scenario
    add:   [{block, cls, x, y, z, yaw, count, attack, behavior, speed, side}]   new units
    player: {x, y, z, yaw}   moves the player's start
    side:     "ally" | "enemy" (default for added units: enemy)
    behavior: "" | "stay" (cannotMove) | "hunt" (unitAttackTarget on the player)
              | "follow" (unitMoveTo following the player: escort)
    attack:   "" | fire_at_will | return_fire | hold_fire (+ cannotShoot)"""
    units = m.setdefault("units", {})
    stay, hunt, passive, sleep, follow, shoot = [], [], [], [], [], []
    _, _, pu = _find_player(units, wing)
    my_army = (pu.get("props") or {}).get("army", 1) if pu else 1
    enemy_army = 2 if my_army == 1 else 1

    def apply(u: dict, e: dict):
        name = u["name"]
        cls = e.get("cls")
        if cls and _CLASS.match(str(cls)) and cls != u.get("unit_class"):
            u["unit_class"] = cls
            u["weapons"] = ""
            for n in range(4):
                if f"bullets{n}" in u:
                    u[f"bullets{n}"] = ""
        props = u.setdefault("props", {})
        if e.get("count"):
            props["count"] = max(1, min(int(e["count"]), 12))
        attack = e.get("attack")
        if attack in ATTACK_TYPES:
            props["attack_type"] = attack
            if attack == "hold_fire":
                passive.append(name)
        if e.get("side") in ("ally", "enemy"):
            props["army"] = my_army if e["side"] == "ally" else enemy_army
        if "x" in e and "z" in e and isinstance(u.get("tm"), list) and len(u["tm"]) == 4:
            try:
                pos = u["tm"][3]
                u["tm"][3] = [float(e["x"]), float(e.get("y", pos[1])), float(e["z"])]
            except (TypeError, ValueError, IndexError):
                pass
        behavior(name, e)

    def behavior(name: str, e: dict):
        b = e.get("behavior")
        if b == "stay":
            stay.append(name)
        elif b == "hunt":
            hunt.append(name)
        elif b == "follow":
            follow.append(name)

    edits_units = edits.get("units") or {}
    own = {u.get("name") for entries in units.values() for u in _as_list(entries) if isinstance(u, dict)}
    for name, e in edits_units.items():
        if name in own or not isinstance(e, dict) or not _CLASS.match(str(name).replace(" ", "_")):
            continue
        if e.get("remove"):  # unit from an imported game template
            sleep.append(name)
            continue
        behavior(name, e)
        if e.get("attack") == "hold_fire":
            passive.append(name)
        elif e.get("attack") == "fire_at_will":  # a template unit: made to fire by a start trigger
            shoot.append(name)
    for block, entries in units.items():
        if block not in EDITABLE_BLOCKS:
            continue
        for u in _as_list(entries):
            if not isinstance(u, dict) or u.get("name") == wing:
                continue
            e = edits_units.get(u.get("name"))
            if not isinstance(e, dict):
                continue
            if e.get("remove"):
                sleep.append(u["name"])
                continue
            apply(u, e)

    moved = {n for n, e in edits_units.items() if isinstance(e, dict) and "x" in e and "z" in e and not e.get("remove")}
    if isinstance(edits.get("player"), dict):
        moved.add(wing)
    if moved:  # placed on the map: drop the scenario's teleports at mission start (respawns later are kept)
        for _, t, a in _trigger_actions(m):
            if _is_start_trigger(t):
                _strip_unit_moves(a, moved)

    for i, a in enumerate((edits.get("add") or [])[:40]):
        if not isinstance(a, dict) or a.get("block") not in EDITABLE_BLOCKS or not _CLASS.match(str(a.get("cls", ""))):
            continue
        block = a["block"]
        try:
            x, y, z = float(a.get("x", 0)), float(a.get("y", 0)), float(a.get("z", 0))
            yaw = float(a.get("yaw", 0))
        except (TypeError, ValueError):
            continue
        props = copy.deepcopy(UNIT_DEFAULTS[block])
        props["army"] = my_army if a.get("side") == "ally" else enemy_army
        props["attack_type"] = "fire_at_will"
        u = {"name": f"wtftd_unit_{i + 1:02d}", "tm": _yaw_tm(yaw, x, y, z), "unit_class": a["cls"], "objLayer": 1,
             "closed_waypoints": False, "isShipSpline": False, "shipTurnRadius": 100.0,
             "weapons": "", "bullets0": "", "bullets1": "", "bullets2": "", "bullets3": "",
             "bulletsCount0": 0, "bulletsCount1": 0, "bulletsCount2": 0, "bulletsCount3": 0,
             "crewSkillK": 0.0, "applyAllMods": False, "props": props, "way": {}}
        if block == "armada":
            try:
                props["speed"] = float(a.get("speed", 400))
            except (TypeError, ValueError):
                props["speed"] = 400.0
        _append_unit(units, block, u)
        apply(u, a)

    for name, e in (edits.get("areas") or {}).items():  # zones moved in the editor
        a = (m.get("areas") or {}).get(name)
        try:
            pos = a["tm"][3]
            a["tm"][3] = [float(e["x"]), float(e.get("y", pos[1])), float(e["z"])]
        except (TypeError, KeyError, IndexError, ValueError):
            continue
    player = edits.get("player")
    if isinstance(player, dict):
        _strip_airfield_spawn(m.get("triggers"), wing)  # the start was placed on the map: no runway spawn
        if pu:
            try:
                pu["tm"] = _yaw_tm(float(player.get("yaw", 0)), float(player["x"]), float(player["y"]), float(player["z"]))
            except (KeyError, TypeError, ValueError):
                pass
            else:
                _hold_start(m, wing, pu["tm"], player)

    actions: dict = {}
    if sleep:
        actions["unitPutToSleep"] = {"target": sleep}
    props_actions = []
    if stay:
        props_actions.append({"object": stay, "cannotMove": True})
    if passive:
        props_actions.append({"object": passive, "cannotShoot": True})
    if shoot:
        props_actions.append({"object": shoot, "attack_type": "fire_at_will", "cannotShoot": False})
    if props_actions:
        actions["unitSetProperties"] = props_actions if len(props_actions) > 1 else props_actions[0]
    if hunt:
        attacks = [{"playerAttracted": True, "object": n, "target": wing, "fireRandom": False} for n in hunt]
        actions["unitAttackTarget"] = attacks if len(attacks) > 1 else attacks[0]
    if follow:
        actions["unitMoveTo"] = {"target": wing, "follow_target": True, "object": follow, "shouldKeepFormation": False,
                                 "teleportHeightType": "absolute", "useUnitHeightForTele": True, "teleportHeightValue": 0.0,
                                 "horizontalDirectionForTeleport": True, "object_marking": 0, "target_marking": 0,
                                 "waypointReachedDist": 10.0, "recalculatePathDist": -1.0, "follow_radius": 60.0,
                                 "follow_offset": [-60.0, 0.0, 40.0]}
    if actions:
        triggers = m.setdefault("triggers", {"isCategory": True, "is_enabled": True})
        if isinstance(triggers, dict):
            triggers["wtftd_editor"] = _trigger({"initMission": {}}, actions, False)


def _hold_start(m: dict, wing: str, tm: list, player: dict):
    """The game templates a scenario imports may respawn the player in a zone of their own as the mission
    starts (test flights: @player -> @air_spawn, with that zone's height, heading and their speed; checked in
    game 2026-10-09). A WTFTD zone at the start set in the editor, and a respawn into it once their scripts
    have run (1 s in), keep that start; an air start then gets its speed."""
    if not m.get("imports"):
        return  # nothing else places the player: the unit's own position is the start
    x, y, z = tm[3]
    m.setdefault("areas", {})["wtftd_start"] = {
        "type": "Sphere", "tm": [[c * 10.0 for c in tm[0]], [0.0, 10.0, 0.0], [c * 10.0 for c in tm[2]], [x, y, z]],
        "objLayer": 0, "props": {}}
    actions = {"unitRespawn": {"delay": 0.0, "offset": [0.0, 0.0, 0.0], "object": wing, "target": "wtftd_start",
                               "resetFormation": True}}
    if player.get("mode") == "air":
        try:
            speed = max(0.0, min(float(player.get("speed") or 450), 3000.0))
        except (TypeError, ValueError):
            speed = 450.0
        actions["unitSetProperties"] = {"object": wing, "speed": speed}
    triggers = m.setdefault("triggers", {"isCategory": True, "is_enabled": True})
    if not isinstance(triggers, dict):
        return
    triggers["wtftd_start"] = _trigger({"periodicEvent": {"time": 1.0}}, actions, False)
    # after a crash the scripts respawn the player in their zone again: once back alive (and placed by them,
    # 1 s), back to the WTFTD start
    if isinstance(m.setdefault("variables", {}), dict):
        m["variables"]["wtftd_dead"] = False
    triggers["wtftd_start_killed"] = _trigger(
        {"periodicEvent": {"time": 0.5}}, {"varSetBool": {"value": True, "var": "wtftd_dead"}}, True)
    triggers["wtftd_start_killed"]["conditions"] = {"playersWhenStatus": {"players": "isKilled", "check_players": "any"}}
    triggers["wtftd_start_back"] = _trigger(
        {"periodicEvent": {"time": 0.5}}, {"varSetBool": {"value": False, "var": "wtftd_dead"}, "wait": {"time": 1.0}, **actions}, True)
    triggers["wtftd_start_back"]["conditions"] = {
        "playersWhenStatus": {"players": "isAlive", "check_players": "any"},
        "varCompareBool": {"var_value": "wtftd_dead", "value": True, "comparasion_func": "equal"}}


def retarget(units: dict, wing: str, pool: dict):
    """Swaps the scenario's enemy units for vehicles of the chosen level.
    pool = {unit block: [unit_class, ...]} prepared by the server (same vehicle type, chosen BR)."""
    swaps = retarget_map(units, wing, pool)
    for block in pool:
        for u in _as_list(units.get(block)):
            if isinstance(u, dict) and u.get("name") in swaps:
                u["unit_class"] = swaps[u["name"]]
                u["weapons"] = ""
                for n in range(4):
                    if f"bullets{n}" in u:
                        u[f"bullets{n}"] = ""


def retarget_map(units: dict, wing: str, pool: dict) -> dict:
    """{unit name: new unit_class} for retarget()."""
    out = {}
    for block, classes in pool.items():
        if not classes:
            continue
        i = 0
        for u in _as_list(units.get(block)):
            if not isinstance(u, dict) or u.get("name") == wing or (u.get("props") or {}).get("army") != 2:
                continue
            out[u["name"]] = classes[i % len(classes)]
            i += 1
    return out


def _trigger(event: dict, actions: dict, repeat: bool) -> dict:
    return {
        "is_enabled": True, "comments": "WTFTD",
        "props": {"actionsType": "PERFORM_ONE_BY_ONE", "conditionsType": "ALL", "enableAfterComplete": repeat},
        "events": event, "conditions": {}, "actions": actions, "else_actions": {},
    }


def _enemy_units(units: dict) -> list[str]:
    names = []
    for block, entries in units.items():
        if block == "squad":
            continue
        for u in _as_list(entries):
            if isinstance(u, dict) and (u.get("props") or {}).get("army") == 2 and u.get("name"):
                names.append(u["name"])
    return names


def make_hostile(m: dict, edits: dict) -> list[str]:
    """"Targets shoot": the scenario's enemies set to hold fire (the test-drive targets) fire at will,
    except units whose fire setting was chosen in the map editor. Returns the units changed."""
    chosen = {n for n, e in (edits.get("units") or {}).items() if isinstance(e, dict) and e.get("attack")}
    changed = []
    for block, entries in (m.get("units") or {}).items():
        if block not in EDITABLE_BLOCKS:
            continue
        for u in _as_list(entries):
            if not isinstance(u, dict) or u.get("name") in chosen:
                continue
            props = u.get("props")
            if isinstance(props, dict) and props.get("army") == 2 and props.get("attack_type") in ("hold_fire", "dont_aim"):
                props["attack_type"] = "fire_at_will"
                changed.append(u["name"])
    return changed


def apply_cheats(m: dict, wing: str, ch: dict, air: bool = False):
    """Game-rule options, built only from actions the official missions use, and stacked so
    that one working mechanism is enough:
      immortal    unitSetProperties isImmortal + invulnerabilityTimer (re-applied every 1 s)
                  + unitRestore full repair / resurrect every 1 s as a fallback (not for aircraft /
                  helicopters: the repair restarts the engines, the MiG-29SMT's never got going; checked
                  in game 2026-10-08. Custom aircraft also get raised hit points.)
      infAmmo     mission isLimitedAmmo:no + unitRestore ammoRestore every 1 s
      noReload    unitForceRearmSpeed x1000 + ammo restore every 1 s (+ gun shotFreq in custom vehicles)
      infFuel     mission isLimitedFuel:no
      repairEvery unitRestore full repair every N s
      passiveEnemies / ghost  unitSetProperties cannotShoot / ignoreCollisions
      hostileEnemies  enemies on hold fire set to fire at will (make_hostile) + cannotShoot:no
    A hint shows the active options when the mission starts, to confirm the triggers run."""
    mission = m["mission_settings"]["mission"]
    if ch.get("infAmmo"):
        mission["isLimitedAmmo"] = False
    if ch.get("infFuel"):
        mission["isLimitedFuel"] = False

    props = {"object": wing}
    if ch.get("immortal"):
        props["isImmortal"] = True
        # spawn-protection timer (seconds), re-applied every second: stops damage instead of resurrecting
        props["invulnerabilityTimer"] = 3600.0
    if ch.get("ghost"):
        props["ignoreCollisions"] = True

    active = [label for key, label in (("immortal", "invulnerable"), ("infAmmo", "unlimited ammo"), ("noReload", "no reload"),
                                       ("infFuel", "unlimited fuel"), ("passiveEnemies", "passive targets"), ("hostileEnemies", "targets shoot"),
                                       ("ghost", "no collisions")) if ch.get(key)]
    every = float(ch.get("repairEvery") or 0)
    if every > 0:
        active.append(f"repair every {int(every)} s")

    init: dict = {}
    if len(props) > 1:
        init["unitSetProperties"] = [dict(props)]
    if ch.get("noReload") or float(ch.get("rearmSpeed") or 0) > 0:
        rearm = 1000.0 if ch.get("noReload") else float(ch.get("rearmSpeed"))
        init["unitForceRearmSpeed"] = {"rearmSpeedK": min(rearm, 1000.0), "target": wing}
    if ch.get("passiveEnemies"):
        enemies = _enemy_units(m.get("units") or {})
        if enemies:
            init.setdefault("unitSetProperties", []).append({"object": enemies, "cannotShoot": True})
    elif ch.get("_hostile"):  # undo a cannotShoot the scenario may set on them
        init.setdefault("unitSetProperties", []).append({"object": ch["_hostile"], "cannotShoot": False})
    if "unitSetProperties" in init and len(init["unitSetProperties"]) == 1:
        init["unitSetProperties"] = init["unitSetProperties"][0]
    if active:
        init["playHint"] = {"hintType": "standard", "name": "WTFTD cheats: " + ", ".join(active), "action": "show",
                            "shouldFadeOut": True, "time": 8.0, "priority": 0, "isOverFade": False, "target_marking": 0,
                            "object_var_name": "", "object_var_comp_op": "equal", "object_var_value": 0, "team": "Both"}

    triggers = m.setdefault("triggers", {"isCategory": True, "is_enabled": True})
    if not isinstance(triggers, dict):
        return
    if init:
        triggers["wtftd_rules_init"] = _trigger({"initMission": {}}, init, False)

    # every second: keep the player immortal / topped up
    fast: dict = {}
    restore = {}
    if ch.get("immortal") and not air:
        restore.update({"fullRestore": True, "ressurectIfDead": True, "partRestore": True})
    if ch.get("infAmmo") or ch.get("noReload"):
        restore["ammoRestore"] = True
    if restore:
        fast["unitRestore"] = {"target": wing, "fullRestore": restore.get("fullRestore", False),
                               "ressurectIfDead": restore.get("ressurectIfDead", False), **restore}
    if len(props) > 1:
        fast["unitSetProperties"] = dict(props)  # re-apply after the scenario respawns the player
    if fast:
        triggers["wtftd_rules_fast"] = _trigger({"periodicEvent": {"time": 1.0}}, fast, True)

    if every > 0 and not ch.get("immortal"):
        repair = {"unitRestore": {"target": wing, "fullRestore": True, "ammoRestore": True, "ressurectIfDead": False}}
        triggers["wtftd_rules_repair"] = _trigger({"periodicEvent": {"time": max(1.0, every)}}, repair, True)


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", s).strip("_")[:80] or "mission"


def _count(v) -> int:
    try:
        return max(0, min(int(v or 0), 100000))
    except (TypeError, ValueError):
        return 0


def write_bullets(unit: dict, ammo: list, groups: list | None = None):
    """The player's bullet slots: belt / shell set id and count per slot.

    groups: the vehicle's ammo groups (details.json "am", same order as ammo). For aircraft and
    helicopters, slots are written the way the game itself spawns them (respawn.nut): one after the other,
    each tagged with its weapon (bulletsWeapon<i> = weapon blk name), a countermeasure launcher as two sets
    (flares, then chaff), counts per launcher. Without the weapon tag the game binds slots in an order of its
    own that differs between aircraft (checked in game, 2026-10-08).
    Without groups (tanks, ships): 4 slots, slot = ammo index, chaff in the first slot no weapon uses."""
    groups = [g if isinstance(g, dict) else {} for g in groups or []]
    tagged = any(g.get("p") for g in groups)
    for i in range(6 if tagged else 4):
        unit[f"bullets{i}"] = ""
        unit[f"bulletsCount{i}"] = 0
        if tagged:
            unit[f"bulletsWeapon{i}"] = ""
    sets = []  # (slot index or None, id, count, weapon)
    for i, a in enumerate(ammo):
        a = a if isinstance(a, dict) else {}
        g = groups[i] if i < len(groups) else {}
        # countermeasures: the mission gives each launcher its count (n launchers share the total)
        n = max(1, int(g.get("n", 1) or 1)) if g.get("trig") == "countermeasures" else 1
        weapon = re.sub(r"\.blk$", "", str(g.get("p", "")).rsplit("/", 1)[-1], flags=re.I)
        count = _count(a.get("count"))
        ch = a.get("chaff")
        cid = str(ch.get("id", "")) if isinstance(ch, dict) else ""
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", cid):
            sets.append((i, str(a.get("id", "") or ""), -(-count // n), weapon))
            continue
        # flares + chaff on one launcher: two linked sets; a set left at 0 is not written (as the game does)
        if count:
            sets.append((i if not tagged else None, "", count // n, weapon))
        sets.append((None, cid, _count(ch.get("count")) // n, weapon))
    if tagged:
        for s, (_, sid, cnt, weapon) in enumerate(sets[:6]):
            unit[f"bullets{s}"] = sid
            unit[f"bulletsCount{s}"] = cnt
            unit[f"bulletsWeapon{s}"] = weapon
        return
    free = list(range(len(ammo), 4))
    for slot, sid, cnt, _ in sets:
        if slot is None:
            if not free:
                continue
            slot = free.pop(0)
        if slot < 4:
            unit[f"bullets{slot}"] = sid
            unit[f"bulletsCount{slot}"] = cnt


def build(cfg: dict) -> tuple[str, str]:
    """Returns (file_name, blk_text)."""
    sid = cfg.get("scenario", "")
    vid = cfg.get("vehicle", "")
    block = cfg.get("block", "")
    if not vid or not re.fullmatch(r"[A-Za-z0-9_\-.]+", vid):
        raise MissionError("Invalid vehicle id")
    if block not in UNIT_DEFAULTS:
        raise MissionError("Invalid unit block")

    m = copy.deepcopy(load_scenario(sid))
    ms = m.setdefault("mission_settings", {})
    mission = ms.setdefault("mission", {})
    wing = (ms.get("player") or {}).get("wing")
    units = m.setdefault("units", {})
    old_block, idx, unit = _find_player(units, wing)
    if unit is None:
        raise MissionError("Scenario has no player unit")

    # ---- player unit
    if old_block != block:
        _remove_unit(units, old_block, idx)
        props = copy.deepcopy(UNIT_DEFAULTS[block])
        props["army"] = (unit.get("props") or {}).get("army", 1)
        unit = {
            "name": wing, "tm": unit["tm"], "unit_class": vid, "objLayer": 1,
            "closed_waypoints": False, "isShipSpline": False, "shipTurnRadius": 100.0,
            "weapons": "", "bullets0": "", "bullets1": "", "bullets2": "", "bullets3": "",
            "bulletsCount0": 0, "bulletsCount1": 0, "bulletsCount2": 0, "bulletsCount3": 0,
            "crewSkillK": 0.0, "applyAllMods": False, "props": props, "way": {},
        }
        _append_unit(units, block, unit)

    unit_class = cfg.get("unitClass") or vid
    if not re.fullmatch(r"(userVehicles/)?[A-Za-z0-9_\-.]+", unit_class):
        raise MissionError("Invalid unit class")
    unit["unit_class"] = unit_class
    unit["weapons"] = cfg.get("preset", "") or ""
    write_bullets(unit, cfg.get("ammo") or [], cfg.get("_ammoGroups"))
    unit["applyAllMods"] = bool(cfg.get("allMods", True))
    ch = cfg.get("cheats") or {}
    crew = ch.get("crew") or ("expert" if ch.get("expertCrew") else "")
    if crew in ("expert", "ace"):
        unit["crewSkillK"] = 1.0  # 0..1, 1 = fully trained crew
        # same block official event missions use to hand out fully trained crews (2 = ace, 1 = expert)
        slot = {"crewSkillsPercent": 100, "crewSpecialization": 2 if crew == "ace" else 1}
        edit = {"keepOwnUnits": True}
        for country, unit_ids in (cfg.get("_crewUnits") or {}).items():
            if re.fullmatch(r"country_[a-z]+", country):
                edit[country] = {uid: dict(slot) for uid in unit_ids if re.fullmatch(r"[A-Za-z0-9_\-.]+", uid)}
        if len(edit) > 1:
            mission["editSlotbar"] = edit

    # ---- start position
    start = cfg.get("start", "scenario")
    if start == "air" and block == "armada":
        tm = unit["tm"]
        alt = float(cfg.get("altitude", 1500))
        speed = float(cfg.get("speed", 450))
        start_y = float(tm[3][1])
        # absolute altitude (ASL); keep a margin above ground starts on high airfields
        tm[3][1] = alt if start_y >= 300 else max(alt, start_y + 100.0)
        unit.setdefault("props", {})["speed"] = speed
        _strip_airfield_spawn(m.get("triggers"), wing)
    fuel = cfg.get("fuel")
    if block == "armada" and fuel not in (None, ""):
        pct = max(1.0, min(float(fuel), 100.0))
        unit.setdefault("props", {})["fuel"] = pct  # % of the tanks, as official missions set it on AI aircraft
        mission["fuelAmount"] = round(pct / 100.0, 3)
        if not (cfg.get("cheats") or {}).get("infFuel"):
            mission["isLimitedFuel"] = True
    if cfg.get("heading") not in (None, ""):
        yaw = math.radians(float(cfg["heading"]))
        x, y, z = unit["tm"][3]
        unit["tm"] = [[math.cos(yaw), 0.0, math.sin(yaw)], [0.0, 1.0, 0.0], [-math.sin(yaw), 0.0, math.cos(yaw)], [x, y, z]]

    retarget(units, wing, cfg.get("_targetPool") or {})
    start_y = float(unit["tm"][3][1])
    apply_edits(m, wing, cfg.get("edits") or {})
    pl = (cfg.get("edits") or {}).get("player")
    if block == "armada" and isinstance(pl, dict):
        # the start set in the editor: in the air at its speed, or parked on the ground
        mode = pl.get("mode") or ("air" if float(unit["tm"][3][1]) > start_y + 50 else "")
        if mode == "air":
            try:
                speed = float(pl.get("speed") or cfg.get("speed") or 450)
            except (TypeError, ValueError):
                speed = 450.0
            unit.setdefault("props", {})["speed"] = max(0.0, min(speed, 3000.0))
        elif mode == "ground":
            unit.setdefault("props", {})["speed"] = 0.0
    cheats = dict(cfg.get("cheats") or {})
    if cheats.get("hostileEnemies") and not cheats.get("passiveEnemies"):
        cheats["_hostile"] = make_hostile(m, cfg.get("edits") or {})
    else:
        cheats.pop("hostileEnemies", None)
    apply_cheats(m, wing, cheats, air=block == "armada")

    # ---- mission settings
    mtype = cfg.get("missionType") or "singleMission"
    if mtype in MISSION_TYPES:
        mission["type"] = mtype
    title = (cfg.get("title") or f"Test Drive: {vid}")[:120]
    mission["locName"] = title
    if cfg.get("environment") in ENVIRONMENTS:
        mission["environment"] = cfg["environment"]
    if cfg.get("weather") in WEATHERS:
        mission["weather"] = cfg["weather"]
    if cfg.get("difficulty") in ("arcade", "realistic", "simulation"):
        mission["difficulty"] = cfg["difficulty"]

    header = {"selected_tag": "", "bin_dump_file": ""}
    body = {k: v for k, v in m.items() if k not in header}
    text = blk.dumps({**header, **body})
    fname = cfg.get("fileName") or f"wtftd_{vid}"
    return safe_name(fname) + ".blk", text
