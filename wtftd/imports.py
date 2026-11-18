"""Game missions imported into WTFTD (My maps' Import): a War Thunder user mission as players share them, its .blk and
the texts of its .csv, in a .zip or not. Each one is read and checked (WTFTD runs nothing of it), kept in
user/imported as a scenario of its own (usr_<name>.json, its texts in usr_<name>/) and given back with the vehicle its
creator put the player in: the page makes a mission, a map and a vehicle of them."""
from __future__ import annotations

import copy
import csv
import io
import json
import re
import zipfile

from pathlib import Path

from . import blk
from .mission import IMPORTED, UNIT_DEFAULTS, _append_unit, _as_list, _find_player, _import_records

MAX_FILE = 20 << 20  # one mission or text, unpacked
MAX_TOTAL = 60 << 20  # all of an archive, unpacked: a bomb stops here
MAX_FILES = 200
LEVEL = re.compile(r"levels/([a-z0-9_]+)\.bin")
KINDS = {"armada": "air", "tankModels": "ground", "ships": "ship"}  # the player's unit block
PART = re.compile(r"UserMissions(?:[/\\][\w\- ][\w.\- ]*)+\.blk", re.I)  # a file of the player's a mission imports (a template)
USER_IMPORT = re.compile(r'(\bfile:t=")((?i:UserMissions)[/\\][^"]+)(")')
PARTS = "parts.json"  # in an imported mission's folder: {its path in the game: text}
BESIDE = "{}.imports"  # the folder in UserMissions where a mission made of it gets them: <its file name>.imports


class MissingPart(Exception):
    """A mission imports a file of UserMissions that's gone, which WTFTD has no copy of: the game would load it and go
    back to its menu."""


class ImportFailed(Exception):
    """code: what the page says (share.gameErr.<code>)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _decode(b: bytes) -> str:
    """A file's text with \\n line ends, as read_text gives them: written back, Windows ends would double (\\r\\r\\n)."""
    try:
        text = b.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = b.decode("cp1252", errors="replace")
    return text.replace("\r\n", "\n")


def files_of(name: str, data: bytes) -> dict[str, str]:
    """{file name: text} of the .blk and .csv a .zip holds, or of the one file given; folders in it are flattened."""
    if name.lower().endswith(".zip"):
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            infos = [i for i in z.infolist() if not i.is_dir()]
        except (zipfile.BadZipFile, ValueError):
            raise ImportFailed("file") from None
        if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_TOTAL:
            raise ImportFailed("size")
        out = {}
        for i in infos:
            base = i.filename.replace("\\", "/").rsplit("/", 1)[-1]
            if base.lower().endswith((".blk", ".csv")) and i.file_size <= MAX_FILE:
                try:
                    out[base] = _decode(z.read(i))
                except (zipfile.BadZipFile, ValueError, OSError, NotImplementedError):
                    raise ImportFailed("file") from None
        return out
    if name.lower().endswith((".blk", ".csv")) and len(data) <= MAX_FILE:
        return {name.replace("\\", "/").rsplit("/", 1)[-1]: _decode(data)}
    raise ImportFailed("file")


def _texts(csv_text: str) -> dict[str, str]:
    """{key: English text} of a game localization file ("<ID>";"<English>";...)."""
    out = {}
    for row in csv.reader(io.StringIO(csv_text), delimiter=";"):
        if len(row) >= 2 and row[0] and not row[0].startswith("<"):
            out[row[0]] = row[1]
    return out


def _sid(stem: str) -> str:
    return "usr_" + (re.sub(r"[^a-z0-9_]+", "_", stem.lower()).strip("_") or "mission")[:60]


def read(name: str, data: bytes, levels=None) -> list[dict]:
    """The missions of a file the player imports: [{sid, stem, mission (the scenario), texts: {csv name: text}, name,
    description, player}], one without a player given one (place). levels: the maps the game has (data/levels.json); a
    mission on another one (its own terrain) is refused."""
    return read_files(files_of(name, data), levels, place=True)


def _parts(m: dict, find, kept: dict, depth: int = 0) -> dict:
    """The files of UserMissions a mission imports, and theirs (the T-14's UserMissions/template/testflight_template.blk):
    {path as written: text}. Kept with it, the mission still loads once they're gone from the game."""
    for rec in _import_records(m):
        path = rec["file"]
        if depth > 4 or path in kept or not PART.fullmatch(path) or ".." in path:
            continue
        text = find(path)
        if text is None:
            continue
        kept[path] = text
        try:
            _parts(blk.loads(text), find, kept, depth + 1)
        except (ValueError, IndexError, KeyError, RecursionError):
            pass
    return kept


def read_files(files: dict, levels=None, find=None, place=False) -> list[dict]:
    """read, for {file name: text} already at hand. find(path): the text of a file of UserMissions a mission imports;
    by default the one of that name among files (an archive's folders are flattened). place: when none has a player,
    give one to each that isn't a part of another; else they're parts (a package's files, read one at a time)."""
    named = {k.lower(): v for k, v in files.items()}
    find = find or (lambda path: named.get(re.split(r"[/\\]", path)[-1].lower()))
    csvs = {k: v for k, v in files.items() if k.lower().endswith(".csv")}
    out, spare = [], []
    for fname, text in files.items():
        if not fname.lower().endswith(".blk"):
            continue
        stem = fname[:-4]
        try:
            m = blk.loads(text)
        except (ValueError, IndexError, KeyError, RecursionError):
            raise ImportFailed("parse") from None
        ms = m.get("mission_settings") if isinstance(m, dict) else None
        info = (ms or {}).get("mission") if isinstance(ms, dict) else None
        if not isinstance(info, dict) or not isinstance(m.get("units"), dict):
            continue  # a .blk that isn't a mission (a sight, a skin's): not one to import
        level = LEVEL.fullmatch(str(info.get("level", "")))
        if not level:
            raise ImportFailed("level")
        if levels and level.group(1) not in levels:
            raise ImportFailed("map")
        wing = str(((ms.get("player") or {}) if isinstance(ms.get("player"), dict) else {}).get("wing", ""))
        block, _, unit = _find_player(m["units"], wing)
        if unit is None or block not in KINDS:
            spare.append((fname, stem, m, info, level))  # no player of its own: a part other missions import (the T-14's templates)
            continue
        out.append(_found(stem, m, info, level, block, wing, unit, csvs, find))
    if not out and place:  # none has a player (a PvE mission where each player brings their own): one is placed, the page asks for a vehicle
        parts = {re.split(r"[/\\]", r["file"])[-1].lower() for f in spare for r in _import_records(f[2])}
        for fname, stem, m, info, level in spare:
            if fname.lower() not in parts:
                wing, unit = _place_player(m)
                out.append({**_found(stem, m, info, level, "tankModels", wing, unit, csvs, find), "placed": 1})
    if not out:
        raise ImportFailed("player" if spare else "empty")
    return out


def _found(stem, m, info, level, block, wing, unit, csvs, find) -> dict:
    own = {k: v for k, v in csvs.items() if k.lower() in (f"usr_{stem}.csv".lower(), f"{stem}.csv".lower())} or csvs
    words = {}
    for v in own.values():
        words.update(_texts(v))
    key, loc = f"missions/{info.get('name', '')}", str(info.get("locName") or "")
    title = words.get(key) or words.get(loc) or loc or stem.replace("_", " ")  # locName: a text key or the text, as the game shows it
    return {"sid": _sid(stem), "stem": stem, "mission": m, "texts": own, "map": level.group(1), "block": block,
            "wing": wing, "player": unit, "name": title.strip()[:80], "parts": _parts(m, find, {}),
            "description": " ".join(str(words.get(f"{key}/objective", "")).split())[:300]}


def _place_player(m: dict) -> tuple[str, dict]:
    """A player for a mission that has none: a tank without a vehicle (WTFTD puts the one picked in its place) in the first
    area named for a spawn, else beside the first unit of the player's side, else at the map's centre; the editor moves it."""
    ms = m["mission_settings"]
    player = ms["player"] if isinstance(ms.get("player"), dict) else {}
    army = player.get("army") if player.get("army") in (1, 2) else 1
    pos = None
    areas = m.get("areas") if isinstance(m.get("areas"), dict) else {}
    units = [u for e in m["units"].values() for u in _as_list(e) if isinstance(u, dict)]
    for tm in [a.get("tm") for n, a in areas.items() if "spawn" in n.lower() and isinstance(a, dict)] \
            + [u.get("tm") for u in units if isinstance(u.get("props"), dict) and u["props"].get("army") == army]:
        try:
            pos = [float(c) for c in tm[3]][:3]
            if len(pos) == 3:
                break
        except (TypeError, ValueError, IndexError, KeyError):
            pos = None
    names = {u.get("name") for u in units}
    wing = next(n for n in ("wtftd_player", *(f"wtftd_player_{i}" for i in range(2, 99))) if n not in names)
    unit = {"name": wing, "tm": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], pos or [0.0, 0.0, 0.0]], "unit_class": "",
            "objLayer": 1, "weapons": "", "applyAllMods": True, "props": {**copy.deepcopy(UNIT_DEFAULTS["tankModels"]), "army": army}, "way": {}}
    _append_unit(m["units"], "tankModels", unit)
    ms["player"] = {**player, "army": army, "wing": wing}
    return wing, unit


def vehicle(found: dict) -> dict:
    """The setup of the vehicle the mission's creator put the player in: its preset, its ammo slots, its upgrades. With
    the mission's ammo unlimited, the slots it sets (5 shells for WT Smart Test Drive's Leopard) would be all the vehicle
    carries on another map: it gets the game's load then."""
    unit, block = found["player"], found["block"]
    info = found["mission"]["mission_settings"]["mission"]
    ammo = []
    for i in range(6 if info.get("isLimitedAmmo", True) is not False else 0):
        sid, count = unit.get(f"bullets{i}"), unit.get(f"bulletsCount{i}")
        if not sid and not count:
            continue
        ammo.append({"id": str(sid or ""), "count": int(count) if isinstance(count, (int, float)) else 0})
    speed = (unit.get("props") or {}).get("speed") if isinstance(unit.get("props"), dict) else None
    return {"vehicle": str(unit.get("unit_class", "")), "block": block, "preset": str(unit.get("weapons") or ""),
            "ammo": ammo, "allMods": bool(unit.get("applyAllMods", True)), "start": "scenario", "altitude": 1500,
            "speed": speed if isinstance(speed, (int, float)) and speed > 0 else 450, "fuel": 0, "mods": {}, "cheats": {}}


def save(found: list[dict]) -> list[dict]:
    """Keeps each mission in user/imported, replacing one imported before under the same name; returns their
    scenario entries (as data/scenarios.json lists the game's)."""
    IMPORTED.mkdir(parents=True, exist_ok=True)
    out = []
    for f in found:
        sid, n = f["sid"], 1
        while _other(sid, f):
            n += 1
            sid = f"{f['sid']}_{n}"
        f["sid"] = sid
        (IMPORTED / f"{sid}.json").write_text(json.dumps(f["mission"], ensure_ascii=False), encoding="utf-8")
        folder = IMPORTED / sid
        folder.mkdir(exist_ok=True)
        for old in folder.glob("*.csv"):
            old.unlink()
        for name, text in f["texts"].items():
            if re.fullmatch(r"[\w.\-]+\.csv", name):
                (folder / name).write_text(text, encoding="utf-8")
        if f.get("parts"):
            (folder / PARTS).write_text(json.dumps(f["parts"], ensure_ascii=False), encoding="utf-8")
        else:
            (folder / PARTS).unlink(missing_ok=True)
        tm = f["player"].get("tm")
        pos = tm[3] if isinstance(tm, list) and len(tm) == 4 and isinstance(tm[3], list) else [0, 0, 0]
        out.append({"id": sid, "map": f["map"], "kind": KINDS[f["block"]], "nation": "", "tags": [],
                    "start": "air" if f["block"] == "armada" and float(pos[1] or 0) > 300 else "ground",
                    "block": f["block"], "wing": f["wing"], "pos": pos, "type": "singleMission", "en": {},
                    "units": sum(len(v) if isinstance(v, list) else 1 for v in f["mission"]["units"].values()),
                    "imported": 1, "title": f["name"], "name": f["name"], "description": f["description"],
                    **({"placed": 1} if f.get("placed") else {})})  # its player is WTFTD's: the page says to pick a vehicle
    index = {e["id"]: e for e in entries()}
    index.update({e["id"]: e for e in out})
    (IMPORTED / "index.json").write_text(json.dumps(list(index.values()), ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _other(sid: str, f: dict) -> bool:
    """Is another mission kept under this id (not this one imported again: same name in the game, same map)?"""
    try:
        kept = json.loads((IMPORTED / f"{sid}.json").read_text(encoding="utf-8"))["mission_settings"]["mission"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    mine = f["mission"]["mission_settings"]["mission"]
    return (kept.get("name"), kept.get("level")) != (mine.get("name"), mine.get("level"))


def remove(sid: str) -> bool:
    """Forgets an imported mission (none of its entries left in My maps or My missions): its scenario and its texts."""
    if not re.fullmatch(r"usr_[a-z0-9_]+", sid or ""):
        return False
    for csv_file in texts(sid):
        csv_file.unlink()
    for path in (IMPORTED / sid / PARTS, IMPORTED / sid, IMPORTED / f"{sid}.json"):
        try:
            path.rmdir() if path.is_dir() else path.unlink()
        except OSError:
            pass
    left = [e for e in entries() if e["id"] != sid]
    (IMPORTED / "index.json").write_text(json.dumps(left, ensure_ascii=False, indent=1), encoding="utf-8")
    return True


def entries() -> list[dict]:
    try:
        data = json.loads((IMPORTED / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [e for e in data if isinstance(e, dict) and re.fullmatch(r"usr_[a-z0-9_]+", str(e.get("id", "")))] if isinstance(data, list) else []


def texts(sid: str) -> list:
    """The .csv texts of an imported mission, to go next to the missions made of it."""
    if not re.fullmatch(r"usr_[a-z0-9_]+", sid or ""):
        return []
    return sorted((IMPORTED / sid).glob("*.csv"))


def texts_for(sid: str) -> str | None:
    """An imported mission's texts as one file, for the mission made of it: the game reads them from usr_<its file name>.csv
    beside it (wiki: CSV files for missions), so they follow the name WTFTD gives it. Several .csv: one header, all rows."""
    parts = [p.read_text(encoding="utf-8-sig", errors="replace").splitlines() for p in texts(sid)]
    if not parts:
        return None
    rows = parts[0] + [line for more in parts[1:] for line in more if not line.lstrip('"').startswith("<")]
    return "\n".join(rows) + "\n"


def parts(sid: str) -> dict:
    """The files of UserMissions an imported mission imports, kept with it: {path as written: text}."""
    if not re.fullmatch(r"usr_[a-z0-9_]+", sid or ""):
        return {}
    try:
        data = json.loads((IMPORTED / sid / PARTS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str) and PART.fullmatch(k) and ".." not in k} if isinstance(data, dict) else {}


def for_game(sid: str, stem: str, text: str, um: Path) -> tuple[str, dict]:
    """The mission made of an imported one (stem: its file name), ready for the game: the files of UserMissions it imports
    written from WTFTD's copies in UserMissions/<stem>.imports/ (BESIDE), so they go with it, its imports pointed there:
    (its text, {file name: text}). One WTFTD has no copy of must still be in um, else MissingPart."""
    kept, here = parts(sid), BESIDE.format(stem)
    names = {p: "_".join(re.split(r"[/\\]", p)[1:]) for p in kept}
    for t in [text, *kept.values()]:
        for m in USER_IMPORT.finditer(t):
            if m.group(2) not in names and not um.joinpath(*re.split(r"[/\\]", m.group(2))[1:]).is_file():
                raise MissingPart(m.group(2))

    def point(t: str) -> str:
        return USER_IMPORT.sub(lambda m: m.group(1) + (f"UserMissions/{here}/{names[m.group(2)]}" if m.group(2) in names else m.group(2)) + m.group(3), t)

    return point(text), {names[p]: point(t) for p, t in kept.items()}

