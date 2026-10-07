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

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

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
                "name": u.get("name"), "block": block, "cls": u.get("unit_class", ""),
                "x": round(x, 1), "y": round(y, 1), "z": round(z, 1), "yaw": round(math.degrees(math.atan2(fz, fx)), 1),
                "army": props.get("army", 0), "count": props.get("count", 1), "attack": props.get("attack_type", ""),
                "moves": bool(u.get("way")), "player": u.get("name") == wing,
                "edit": block in EDITABLE_BLOCKS and u.get("name") != wing,
            })
    return {"wing": wing, "units": out}


def _yaw_tm(deg: float, x: float, y: float, z: float):
    t = math.radians(deg)
    return [[math.cos(t), 0.0, math.sin(t)], [0.0, 1.0, 0.0], [-math.sin(t), 0.0, math.cos(t)], [x, y, z]]


def apply_edits(m: dict, wing: str, edits: dict):
    """Map editor changes:
    units: {name: {cls, count, attack, behavior, remove}}   existing units of the scenario
    add:   [{block, cls, x, y, z, yaw, count, attack, behavior, speed}]   new enemy units
    player: {x, y, z, yaw}   moves the player's start
    behavior: "" | "stay" (cannotMove) | "hunt" (unitAttackTarget on the player)
    attack:   "" | fire_at_will | return_fire | hold_fire (+ cannotShoot)"""
    units = m.setdefault("units", {})
    stay, hunt, passive, sleep = [], [], [], []

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
        if e.get("behavior") == "stay":
            stay.append(name)
        elif e.get("behavior") == "hunt":
            hunt.append(name)

    edits_units = edits.get("units") or {}
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
        props["army"] = 2
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

    player = edits.get("player")
    if isinstance(player, dict):
        _, _, pu = _find_player(units, wing)
        if pu:
            try:
                pu["tm"] = _yaw_tm(float(player.get("yaw", 0)), float(player["x"]), float(player["y"]), float(player["z"]))
            except (KeyError, TypeError, ValueError):
                pass

    actions: dict = {}
    if sleep:
        actions["unitPutToSleep"] = {"target": sleep}
    props_actions = []
    if stay:
        props_actions.append({"object": stay, "cannotMove": True})
    if passive:
        props_actions.append({"object": passive, "cannotShoot": True})
    if props_actions:
        actions["unitSetProperties"] = props_actions if len(props_actions) > 1 else props_actions[0]
    if hunt:
        attacks = [{"playerAttracted": True, "object": n, "target": wing, "fireRandom": False} for n in hunt]
        actions["unitAttackTarget"] = attacks if len(attacks) > 1 else attacks[0]
    if actions:
        triggers = m.setdefault("triggers", {"isCategory": True, "is_enabled": True})
        if isinstance(triggers, dict):
            triggers["wtftd_editor"] = _trigger({"initMission": {}}, actions, False)


def retarget(units: dict, wing: str, pool: dict):
    """Swaps the scenario's enemy units for vehicles of the chosen level.
    pool = {unit block: [unit_class, ...]} prepared by the server (same vehicle type, chosen BR)."""
    for block, classes in pool.items():
        if not classes:
            continue
        i = 0
        for u in _as_list(units.get(block)):
            if not isinstance(u, dict) or u.get("name") == wing or (u.get("props") or {}).get("army") != 2:
                continue
            u["unit_class"] = classes[i % len(classes)]
            u["weapons"] = ""
            for n in range(4):
                if f"bullets{n}" in u:
                    u[f"bullets{n}"] = ""
            i += 1


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


def apply_cheats(m: dict, wing: str, ch: dict):
    """Game-rule options, built only from actions the official missions use, and stacked so
    that one working mechanism is enough:
      immortal    unitSetProperties isImmortal + invulnerabilityTimer (re-applied every 1 s)
                  + unitRestore full repair / resurrect every 1 s as a fallback
      infAmmo     mission isLimitedAmmo:no + unitRestore ammoRestore every 1 s
      noReload    unitForceRearmSpeed x1000 + ammo restore every 1 s (+ gun shotFreq in custom vehicles)
      infFuel     mission isLimitedFuel:no
      repairEvery unitRestore full repair every N s
      passiveEnemies / ghost  unitSetProperties cannotShoot / ignoreCollisions
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
                                       ("infFuel", "unlimited fuel"), ("passiveEnemies", "passive targets"),
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
    if ch.get("immortal"):
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
    ammo = cfg.get("ammo") or []
    for i in range(4):
        a = ammo[i] if i < len(ammo) and isinstance(ammo[i], dict) else {}
        unit[f"bullets{i}"] = str(a.get("id", "") or "")
        unit[f"bulletsCount{i}"] = max(0, min(int(a.get("count", 0) or 0), 100000))
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
    if cfg.get("heading") not in (None, ""):
        yaw = math.radians(float(cfg["heading"]))
        x, y, z = unit["tm"][3]
        unit["tm"] = [[math.cos(yaw), 0.0, math.sin(yaw)], [0.0, 1.0, 0.0], [-math.sin(yaw), 0.0, math.cos(yaw)], [x, y, z]]

    retarget(units, wing, cfg.get("_targetPool") or {})
    apply_edits(m, wing, cfg.get("edits") or {})
    apply_cheats(m, wing, cfg.get("cheats") or {})

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
