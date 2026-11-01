"""Challenges: scored missions on the game's bare maps. mission.apply_challenge writes the rules, this says what's where,
and keeps the results in user/challenges.json.

Every challenge ends in a win or a failure, and the score is the time: that's all the game lets the app read.
  - /mission.json (the game's local API, read by its own web page) gives the objective's text and state, while WTFTD is open;
  - a replay gives the time played and, unchecked on a mission that really ends, the result. A mission can't write a file, and
    the counters of a replay's player line are all 0 in user missions (28 of 28 files, game 2.59): no score from there.
So a mission is known by its objective, a text with the vehicle in it, and a replay by its file name.

Sites are checked on the game's heightmaps, which not every PC can read (they need an Oodle library): the heights are written here,
every 200 m along the line of fire."""
from __future__ import annotations

import json
import math
import re

from .mission import CH_END_WAIT, MissionError, _clean_text, safe_name

DIFFICULTIES = ("easy", "normal", "hard")
MAX_RESULTS = 2000
NEAR_S = 120  # s between a result seen live and the end of its replay
TRUCK = "ussr_zis5"
BOAT = "germ_ls_class"
MISSILES = ("mig_29_9_12", "mig_29_9_12_r60m_default")  # the game's own training on flares: an AI that fires missiles when told to

LAND = ({"level": "avg_training_ground", "start": [1469.9, 217.2, 1626.8], "yaw": 0.0,
         "ground": [217.2, 217.2, 216.8, 217.2, 217.4, 217.2, 217.2, 217.2, 245.3, 274.0, 295.7, 294.3]},
        {"level": "air_grand_canyon", "start": [8428.4, 2293.8, 1036.0], "yaw": 30.0,
         "ground": [2293.8, 2294.3, 2294.9, 2295.3, 2295.7, 2296.1, 2296.3, 2296.3, 2296.2, 2295.9, 2295.5, 2295.1]},
        {"level": "air_falklands", "start": [10443.1, 156.2, -9551.8], "yaw": 60.0,
         "ground": [156.4, 153.5, 151.7, 148.2, 145.5, 144.8, 145.2, 146.3, 148.0, 150.2, 153.3, 158.1]})
SKY = ({"level": "air_africa_desert", "start": [-310.1, 1000.0, -3273.6], "yaw": 225.0, "floor": 11.0},
       {"level": "air_falklands", "start": [-26168.1, 1200.0, 3480.7], "yaw": 0.0, "floor": 222.0},
       {"level": "air_grand_canyon", "start": [2404.4, 2500.0, -16953.2], "yaw": 225.0, "floor": 1637.0})
SEA = ({"level": "avn_ice_port", "start": [-1877.1, 0.0, -1220.1], "yaw": 315.0, "floor": 0.0, "reach": 3000},
       {"level": "avn_alps_fjord", "start": [5130.2, 0.0, 3211.4], "yaw": 120.0, "floor": 0.0, "reach": 1700})


def _at(site: dict, far: float, side: float = 0.0) -> dict:
    """A point of a site: far along its line of fire, side to the right of it, on the ground or at the site's height floor."""
    t = math.radians(site["yaw"])
    x, _, z = site["start"]
    ys = site.get("ground")
    if ys:
        k = min(max(far, 0.0) / 200, len(ys) - 1.001)
        y = ys[int(k)] + (ys[int(k) + 1] - ys[int(k)]) * (k - int(k)) + 0.5  # + 0.5: as the map editor, so the vehicle settles
    else:
        y = site["floor"]
    return {"x": round(x + math.cos(t) * far - math.sin(t) * side, 1), "y": round(y, 1), "z": round(z + math.sin(t) * far + math.cos(t) * side, 1)}


def _foes(vehicles: dict, v: dict, kinds: tuple, n: int) -> list:
    """Vehicles of the player's battle rating that fire on their own (not a battery's radar or launcher)."""
    same = [x for x in vehicles.values() if x["c"] == v["c"] and x.get("k") in kinds and not x.get("h") and x.get("br") and x["id"] != v["id"]
            and (x.get("wg") or x.get("wp")) and not re.search(r"_(launcher|fcs)$", x["id"])]
    mine = (v.get("br") or [0, 5.0])[1]
    same.sort(key=lambda x: (abs(x["br"][1] - mine), x["id"]))
    return [x["id"] for x in same[:n]] or [v["id"]]


def _names(add: list) -> list:
    return [f"wtftd_unit_{i + 1:02d}" for i in range(len(add))]  # as mission.apply_edits names what it adds


def _targets(add: list, icon: str = "truck") -> tuple:
    return add, {"rule": "destroy", "targets": _names(add), "icon": icon}


def _truck(site: dict, far: float, side: float, **more) -> dict:
    return {"block": "wheeled_vehicles", "cls": TRUCK, **_at(site, far, side), "yaw": site["yaw"] + 90, "attack": "hold_fire", **more}


def _range(site, p, v, vehicles):
    return _targets([_truck(site, far, (-1) ** i * (15 + far * 0.08), behavior="stay") for i, far in enumerate(p["far"])])


def _moving(site, p, v, vehicles):
    return _targets([_truck(site, far, -300, behavior="route", routeSpeed=p["speed"], routeLoop=True,
                            route=[_at(site, far, 300), _at(site, far, -300)]) for far in p["far"]])


def _defence(site, p, v, vehicles):
    foes = _foes(vehicles, v, ("tank", "heavy_tank", "tank_destroyer"), 3)
    return [{"block": "tankModels", "cls": foes[(w + s) % len(foes)], **_at(site, 1400, (s - p["size"] / 2) * 60), "yaw": site["yaw"] + 180,
             "attack": "fire_at_will", "wave": w + 1, "behavior": "route", "routeSpeed": 25, "route": [_at(site, 300, (s - p["size"] / 2) * 60)]}
            for w in range(p["waves"]) for s in range(p["size"])], {"rule": "waves"}


def _gates(site, p, v, vehicles):
    y = site["start"][1]
    gates = [[(c := _at(site, 3000 * (k + 1), (-1) ** k * 1000))["x"], y + (-1) ** k * p["climb"], c["z"]] for k in range(p["n"])]
    length = sum(math.dist(a, b) for a, b in zip([site["start"]] + gates, gates))
    speed = (v.get("s") or {}).get("spd") or 500
    return [], {"rule": "gates", "gates": gates, "radius": p["radius"], "limit": max(120, min(1200, math.ceil(length / (speed / 3.6 * p["pace"]) / 10) * 10))}


def _bombing(site, p, v, vehicles):
    return _targets([_truck(site, 8000 + 150 * (i // 2), (-1) ** i * 100, behavior="stay") for i in range(p["n"])])


def _sky(site: dict, far: float, side: float) -> dict:
    return {**_at(site, far, side), "y": site["start"][1]}


def _dogfight(site, p, v, vehicles):
    foes = _foes(vehicles, v, ("fighter",), 3)
    return [{"block": "armada", "cls": foes[(w + s) % len(foes)], **_sky(site, 6000, 300 * s), "yaw": site["yaw"] + 180, "speed": 500,
             "attack": "fire_at_will", "wave": w + 1, "behavior": "hunt"} for w in range(p["waves"]) for s in range(p["size"])], {"rule": "waves"}


def _evasion(site, p, v, vehicles):
    add = [{"block": "armada", "cls": MISSILES[0], **_sky(site, 5000, 400 * i), "yaw": site["yaw"] + 180, "speed": 700, "attack": "fire_at_will",
            "loadout": {"vehicle": MISSILES[0], "preset": MISSILES[1], "ammo": []}} for i in range(p["n"])]
    return add, {"rule": "survive", "attackers": _names(add)}


def _gunnery(site, p, v, vehicles):
    return _targets([{"block": "ships", "cls": BOAT, **_at(site, site["reach"] * (i + 2) / (p["n"] + 1), (-1) ** i * 120), "yaw": site["yaw"] + 90,
                      "attack": "hold_fire", "behavior": "stay"} for i in range(p["n"])], "ship")


CHALLENGES = {  # far: distances of the targets in m, limit: s
    "range": {"cats": ("ground",), "sites": LAND, "make": _range, "easy": {"far": (300, 600, 900), "limit": 180},
              "normal": {"far": (400, 700, 1000, 1400), "limit": 150}, "hard": {"far": (500, 800, 1100, 1250, 1400), "limit": 120}},
    "moving": {"cats": ("ground",), "sites": LAND, "make": _moving, "easy": {"far": (400, 600), "speed": 20, "limit": 180},
               "normal": {"far": (500, 800, 1000), "speed": 30, "limit": 180}, "hard": {"far": (500, 800, 1100, 1400), "speed": 40, "limit": 180}},
    "defence": {"cats": ("ground",), "sites": LAND, "make": _defence, "easy": {"waves": 2, "size": 2, "limit": 300},
                "normal": {"waves": 3, "size": 2, "limit": 420}, "hard": {"waves": 4, "size": 3, "limit": 600}},
    "gates": {"cats": ("air",), "sites": SKY, "make": _gates, "easy": {"n": 6, "radius": 400, "pace": 0.45, "climb": 0},
              "normal": {"n": 8, "radius": 300, "pace": 0.55, "climb": 100}, "hard": {"n": 10, "radius": 200, "pace": 0.65, "climb": 200}},
    "bombing": {"cats": ("air",), "sites": SKY, "make": _bombing, "easy": {"n": 4, "limit": 300}, "normal": {"n": 6, "limit": 240}, "hard": {"n": 8, "limit": 180}},
    "dogfight": {"cats": ("air",), "sites": SKY, "make": _dogfight, "easy": {"waves": 2, "size": 1, "limit": 300},
                 "normal": {"waves": 3, "size": 2, "limit": 420}, "hard": {"waves": 4, "size": 2, "limit": 600}},
    "evasion": {"cats": ("air",), "sites": SKY, "make": _evasion, "easy": {"n": 1, "limit": 60}, "normal": {"n": 2, "limit": 90}, "hard": {"n": 3, "limit": 120}},
    "heli": {"cats": ("heli",), "sites": LAND, "make": _range, "easy": {"far": (800, 1100, 1400), "limit": 240},
             "normal": {"far": (800, 1000, 1200, 1400), "limit": 210}, "hard": {"far": (800, 1000, 1200, 1300, 1400), "limit": 180}},
    "naval": {"cats": ("ship", "boat"), "sites": SEA, "make": _gunnery, "easy": {"n": 2, "limit": 300}, "normal": {"n": 3, "limit": 240}, "hard": {"n": 4, "limit": 180}},
}


def catalog() -> list:
    """What the page needs to list them; the words are the page's."""
    def brief(p: dict) -> dict:
        far = p.get("far") or ()
        return {"n": p.get("waves") or len(far) or p.get("n"), "limit": p.get("limit"), **({"near": far[0], "far": far[-1]} if far else {})}
    return [{"id": k, "cats": c["cats"], "levels": [s["level"] for s in c["sites"]], "diffs": {d: brief(c[d]) for d in DIFFICULTIES}} for k, c in CHALLENGES.items()]


def file_name(cid: str, diff: str, vehicle: str) -> str:
    return safe_name(f"wtftd_ch-{cid}-{diff}-{vehicle}")


def plan(body: dict, vehicles: dict) -> dict:
    """The page's request -> mission.build's: the challenge's map, units and rules on the player's own setup, without cheats."""
    ask = body.get("challenge") or {}
    c, diff, v = CHALLENGES.get(ask.get("id")), ask.get("diff"), vehicles.get(body.get("vehicle"))
    site = next((s for s in c["sites"] if s["level"] == ask.get("level")), None) if c else None
    if not site or diff not in DIFFICULTIES or not v or v["c"] not in c["cats"]:
        raise MissionError("This challenge doesn't fit this vehicle or map")
    p = c[diff]
    add, spec = c["make"](site, p, v, vehicles)
    texts = ask.get("texts") if isinstance(ask.get("texts"), dict) else {}
    x, y, z = site["start"]
    player = {"x": x, "y": y, "z": z, "yaw": site["yaw"], **({"mode": "air"} if v["c"] == "air" else {})}
    cheats = {k: x for k, x in (body.get("cheats") or {}).items() if k in ("crew", "expertCrew")}  # the crew is the player's, not a cheat
    return {**body, "scenario": f"free_{site['level']}_{v['c']}", "edits": {"add": add, "player": player, "waveText": texts.get("wave")}, "cheats": cheats,
            "hotkeyTexts": None, "missionType": "singleMission", "start": "scenario", "heading": None, "environment": "", "weather": "",
            "fileName": file_name(ask["id"], diff, v["id"]), "_challenge": {"limit": p.get("limit"), **spec, "texts": texts}}


# ---------------------------------------------------------------------------- results
def clean(data) -> dict:
    """user/challenges.json as this code wants it, whatever the file holds."""
    data = data if isinstance(data, dict) else {}
    made, results = data.get("made"), data.get("results")
    return {"made": made if isinstance(made, dict) else {},
            "results": [x for x in results if isinstance(x, dict) and {"id", "diff", "vehicle", "result", "time", "at"} <= set(x)] if isinstance(results, list) else []}


def remember(data: dict, body: dict):
    """A created mission, under the text of its objective: how the game's API will name it."""
    ask = body["challenge"]
    data["made"][_clean_text((ask.get("texts") or {}).get("goal"), "Challenge")] = {"id": ask["id"], "diff": ask["diff"], "level": ask["level"], "vehicle": body["vehicle"]}


class Live:
    """What's being played, from /mission.json. shortcut: its time is this PC's clock, a pause in the mission counts; a replay corrects it."""

    def __init__(self):
        self.goal, self.since = None, 0.0

    def tick(self, raw: bytes | None, made: dict, now: float) -> dict | None:
        """A result when the objective of a known mission just ended."""
        try:
            objectives = json.loads(raw).get("objectives") or []
        except (AttributeError, TypeError, ValueError):
            objectives = []
        mine = next((o for o in objectives if isinstance(o, dict) and o.get("text") in made), None)
        if not mine:
            self.goal = None
            return None
        goal, state = mine["text"], mine.get("status")
        if state == "in_progress" and goal != self.goal:
            self.goal, self.since = goal, now
        if state not in ("completed", "failed") or goal != self.goal:
            return None
        self.goal = None
        return {**made[goal], "result": "win" if state == "completed" else "loss", "time": round(now - self.since), "at": int(now)}


def add_result(data: dict, result: dict):
    data["results"] = (data["results"] + [result])[-MAX_RESULTS:]


def merge(data: dict, rows: list) -> bool:
    """Replays against results: a replay gives its result's exact time, or the result itself if the game wrote one and WTFTD
    wasn't open. A row takes its result, for My battles. True when data changed."""
    changed = False
    for r in rows:
        made = r.get("challenge")
        if not made or not r["vehicles"]:
            continue
        cid, diff, vehicle, end = *made, r["vehicles"][0], r["start"] + r["played"]
        known = next((x for x in data["results"] if x.get("file") == r["file"]), None) or next(
            (x for x in data["results"] if not x.get("file") and (x["id"], x["diff"], x["vehicle"]) == (cid, diff, vehicle) and abs(x["at"] - end) < NEAR_S), None)
        if known and known.get("file") != r["file"]:
            known.update(file=r["file"], time=max(r["played"] - round(CH_END_WAIT), 0))
            changed = True
        elif not known and r["result"] != "left" and cid in CHALLENGES:
            known = {"id": cid, "diff": diff, "vehicle": vehicle, "level": r["level"], "result": r["result"], "time": max(r["played"] - round(CH_END_WAIT), 0), "at": end, "file": r["file"]}
            add_result(data, known)
            changed = True
        if known:
            r["result"] = known["result"]
    return changed

