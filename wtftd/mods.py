"""Mods (skins, sounds, vehicles of their own): the one page that writes into the game on purpose, and only when the player asks.

  <game>/UserSkins/<skin>/  skins: where the game exports its templates and reads them (the Saves folder has sights, not skins)
  <game>/sound/mod/         sound mods, which the game loads with enable_mod:b=yes in the sound block of <game>/config.blk
  <game>/content/pkg_local/ vehicles of their own (a CDK package: its files, its 3D model under res/), with their test
  <game>/UserMissions/      missions: what the package's README says to copy into the game; WTFTD then offers them as vehicles

What comes in is untrusted, a .zip above all: nothing is written until the whole archive has passed, and nothing is written outside
those two folders. user/mods_manifest.json lists what WTFTD installed and only that is ever removed: what the player put there by hand
is shown and left alone. config.blk changes by that one line, the rest stays byte for byte: user/config.blk.bak keeps it as it was,
and that file's presence says the line is ours. UI in web/mods.js."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import struct
import zipfile
from pathlib import Path

from .paths import CACHE, USER

MANIFEST = USER / "mods_manifest.json"
BACKUP = USER / "config.blk.bak"
STAGING = CACHE / "mods_staging"  # what's being installed: it goes with the cache
SKINS, SOUNDS = "UserSkins", ("sound", "mod")
KINDS = ("skin", "sound", "vehicle", "hangar")
ALLOWED = {"skin": {".blk", ".tga", ".dds", ".png", ".jpg", ".jpeg", ".txt"}, "sound": {".bank", ".txt"},
           "vehicle": {".blk", ".csv", ".txt", ".grp", ".bin", ".png"},  # where each may go: see _vehicle_files
           "hangar": {".blk", ".txt", ".bin", ".grp", ".jpg", ".jpeg", ".png", ".tga", ".dds"}}  # see _hangar_files
PACKAGES = ("pkg_local", "pkg_user")
VEHICLE_DIRS = {("flightmodels",): "air", ("units", "tankmodels"): "ground", ("units", "ships"): "ship"}
GAME_DIRS = {("flightmodels",): "flightModels", ("units", "tankmodels"): "units/tankModels", ("units", "ships"): "units/ships"}  # as the game writes them
BLOCKS = {"air": "armada", "ground": "tankModels", "ship": "ships"}
JUNK = {"thumbs.db", "desktop.ini", ".ds_store"}  # what an archiver leaves: dropped, not refused
TEXTURES = (".tga", ".dds")
MAX_FILE = 2 << 30  # a sound mod's banks can be large: a skin's textures are about 64 MB each
MAX_TOTAL = 4 << 30
MAX_FILES = 3000
MAX_DEPTH = 9  # a vehicle package's gameData/units/tankModels/weaponPresets/... in a folder of its own
MAX_NAME = 120
MAX_RATIO, RATIO_FROM = 100, 256 << 20  # a whole archive: real ones pack 5 to 20 times (one flat texture alone, 1000 times)
CHUNK = 1 << 20
TOKEN = re.compile(r"[a-z0-9]{6,40}")
BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
TEMP = ".wtftd_tmp"
REPLACE = re.compile(r'replace_tex\s*\{[^}]*?from\s*:\s*t\s*=\s*"([^"]+)"[^}]*?to\s*:\s*t\s*=\s*"([^"]+)"', re.S)
ENABLE = re.compile(rb"^[ \t]*enable_mod[ \t]*:[ \t]*b[ \t]*=[ \t]*(yes|no|true|false|1|0)[ \t]*(?:\r?\n|$)", re.M | re.I)
HINT = re.compile(r"[\w\-. ]{1,120}")  # a hangar's name for config.blk, as its post gives it
HANGAR_LINE = re.compile(r'hangarBlk\s*:\s*t\s*=\s*"([^"\r\n]{1,120})"')  # what a hangar's README says config.blk needs
SOUND_BLOCK = re.compile(rb"^[ \t]*sound[ \t]*\{[ \t]*\r?\n", re.M)


class ModsError(Exception):
    """A refusal the page words for the player: code = mo.err.<code>, name = what it's about (data, not markup)."""

    def __init__(self, code: str, name: str = ""):
        super().__init__(code)
        self.code, self.name = code, name


def safe_path(name: str) -> tuple:
    """The parts of a relative path from an archive or a picked folder, refused unless it stays where it's put on any system."""
    if not isinstance(name, str) or not name or name.startswith(("/", "\\")):
        raise ModsError("path", str(name))
    parts = tuple(name.replace("\\", "/").split("/"))
    if len(parts) > MAX_DEPTH:
        raise ModsError("path", name)
    for p in parts:
        if p in ("", ".", "..") or len(p) > MAX_NAME or BAD_CHARS.search(p) or p.endswith((" ", ".")) or p.split(".")[0].lower() in RESERVED:
            raise ModsError("path", name)
    return parts


def _junk(parts: tuple) -> bool:
    return parts[-1].lower() in JUNK or parts[0].lower() == "__macosx"


def _inside(root: Path, *parts: str) -> Path:
    """A path under root, wherever links would take it."""
    target = root.joinpath(*parts).resolve()
    if root.resolve() not in target.parents:
        raise ModsError("path", "/".join(parts))
    return target


def _staging(token: str) -> Path:
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise ModsError("path", str(token))
    return STAGING / token


def forget(token: str) -> None:
    shutil.rmtree(_staging(token), ignore_errors=True)


def receive(token: str, rel: str, stream, length: int, kind: str) -> None:
    """One picked file, into the staging folder: a .zip, or a file of a picked folder under the same rules as a file of an archive."""
    if kind not in (*KINDS, "auto"):  # auto: a .zip whose kind detect() tells
        raise ModsError("path", str(kind))
    root, parts = _staging(token), safe_path(rel)
    if _junk(parts):
        return
    suffix = Path(parts[-1]).suffix.lower()
    if suffix != ".zip" and suffix not in ALLOWED.get(kind, ()) or suffix == ".zip" and len(parts) > 1:
        raise ModsError("type", rel)
    have = [p.stat().st_size for p in root.rglob("*") if p.is_file()] if root.exists() else []
    if not 0 <= length <= MAX_FILE or sum(have) + length > MAX_TOTAL or len(have) >= MAX_FILES:
        raise ModsError("size", rel)
    out = root.joinpath(*parts)
    out.parent.mkdir(parents=True, exist_ok=True)
    left = length
    with open(out, "wb") as f:
        while left:
            chunk = stream.read(min(CHUNK, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    if left:
        out.unlink()
        raise ModsError("size", rel)


def check_archive(z: zipfile.ZipFile, kind: str) -> list:
    """Every entry of an archive, before anything is written: -> [(info, parts)] to extract. One bad entry refuses the whole."""
    infos, total, packed, seen = z.infolist(), 0, 0, set()
    if len(infos) > MAX_FILES:
        raise ModsError("count")
    kept = []
    for i in infos:
        parts = safe_path(i.filename.rstrip("/\\") if i.is_dir() else i.filename)
        kind_bits = stat.S_IFMT(i.external_attr >> 16)
        if kind_bits not in (0, stat.S_IFREG, stat.S_IFDIR):  # a link, a device: only a Unix archive can say so
            raise ModsError("link", i.filename)
        if i.is_dir() or _junk(parts):
            continue
        if i.flag_bits & 1:
            raise ModsError("locked", i.filename)
        if Path(parts[-1]).suffix.lower() not in ALLOWED[kind]:
            raise ModsError("type", i.filename)
        total += i.file_size
        if i.file_size > MAX_FILE or total > MAX_TOTAL:
            raise ModsError("size", i.filename)
        packed += i.compress_size
        key = "/".join(parts).lower()
        if key in seen:  # one would replace the other on Windows
            raise ModsError("path", i.filename)
        seen.add(key)
        kept.append((i, parts))
    if total > RATIO_FROM and total > MAX_RATIO * max(packed, 1):  # what a bomb does, not a skin
        raise ModsError("ratio", kept[0][0].filename if kept else "")
    return kept


def unpack(archive: Path, dest: Path, kind: str) -> None:
    """An archive into dest, checked first. A file that gives more than its header said stops there."""
    try:
        with zipfile.ZipFile(archive) as z:
            for i, parts in check_archive(z, kind):
                out = dest.joinpath(*parts)
                out.parent.mkdir(parents=True, exist_ok=True)
                left = i.file_size
                with z.open(i) as src, open(out, "wb") as f:
                    while chunk := src.read(CHUNK):
                        left -= len(chunk)
                        if left < 0:
                            raise ModsError("size", i.filename)
                        f.write(chunk)
    except (zipfile.BadZipFile, EOFError, NotImplementedError, RuntimeError, OSError) as e:  # damaged, or an unknown compression
        raise ModsError("zip", archive.name) from e


def _files(root: Path) -> list:
    return sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def _replacements(folder: Path, files: list) -> list:
    """What a skin's .blk replaces: [{from: start of a texture's name, to: a texture of the skin}]. A file of any kind: only strings are kept."""
    out = []
    for p in files:
        if p.suffix.lower() == ".blk" and p.stat().st_size < 1 << 20:
            for src, to in REPLACE.findall(p.read_text(encoding="utf-8", errors="replace")):
                if Path(to).suffix.lower() in TEXTURES and (folder / to).is_file():
                    out.append({"from": src.rstrip("*").lower(), "to": to})
    return out


def guess_vehicle(folder: str, names: list, replaced: list, ids) -> dict:
    """Which vehicle a skin is for: the game goes by the .blk named after the vehicle, as its own export does. Otherwise a guess the player
    confirms, from the folder or the textures: {vehicle, sure, candidates}."""
    by = {i.lower(): i for i in ids}
    named = sorted({by[Path(n).stem.lower()] for n in names if n.lower().endswith(".blk") and Path(n).stem.lower() in by})
    if named:  # one .blk a vehicle, several when it fits several (the F-4 MECHA's twelve)
        return {"vehicle": named[0], "vehicles": named, "sure": True, "candidates": named}
    found = list(named)
    stem = folder.lower().removeprefix("template_")
    if stem in by:
        found.append(by[stem])
    found += sorted((v for k, v in by.items() if stem.startswith((k + "_", k + "-", k + " "))), key=len, reverse=True)
    for r in replaced:
        base = re.sub(r"_(c|n|ao|camo)$", "", r["from"])
        if base in by:
            found.append(by[base])
    found = list(dict.fromkeys(found))
    return {"vehicle": found[0] if found else "", "sure": False, "candidates": found[:8]}


def _skin_roots(root: Path) -> list:
    """The folders of what was staged that are skins: those with a .blk, else with a texture. A pack can hold several, at any depth."""
    def holding(*suffixes):
        return sorted({p.parent for p in _files(root) if p.suffix.lower() in suffixes}, key=lambda d: len(d.parts))
    found: list = []
    for d in holding(".blk") or holding(*TEXTURES):
        if not any(top in d.parents for top in found):
            found.append(d)
    return found


def _copies(vehicles: list, plan: dict) -> dict:
    """What the player is told of the copies made: the vehicles, models and textures the game keeps as they are."""
    out = {"vehicles": [v["copy"] for v in vehicles if v.get("copy")],
           "models": sorted(n for n in plan["models"] if not any(n != b and n.startswith(b + "_") for b in plan["models"])),  # not their skeletons
           "textures": sorted(plan["textures"])}
    return {k: v for k, v in out.items() if v}


def _folder(name: str) -> str:
    """The folder a package's copies go in, from its name (FA-22+(2): fa_22_2)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "mod"


def detect(token: str) -> str:
    """What the archives picked hold, from their files' names, nothing unpacked yet (several picked at once, each goes
    where it belongs): a vehicle package (content/, pkg_local, UserMissions/, 3D packs), a sound mod (banks), else skins."""
    names = []
    for z in _staging(token).glob("*.zip"):
        try:
            with zipfile.ZipFile(z) as a:
                names += [n.lower().replace("\\", "/") for n in a.namelist()]
        except (zipfile.BadZipFile, OSError):
            pass  # inspect says what's wrong with it
    folders = {p for n in names for p in n.split("/")[:-1]}
    if folders & {"content", "usermissions", *PACKAGES} or any(n.endswith((".grp", ".dxp.bin")) for n in names):
        return "vehicle"
    return "sound" if any(n.endswith(".bank") for n in names) else "skin"


def inspect(token: str, kind: str, ids=(), game: Path | None = None, hint: str = "") -> dict:
    """What was staged, a .zip unpacked once it has passed: {skins: [...]} or {sound: {...}}, for the player to confirm."""
    root = _staging(token)
    if kind not in KINDS or not root.is_dir():
        raise ModsError("empty")
    for z in list(root.glob("*.zip")):
        unpack(z, root / safe_path(z.stem)[0], kind)
        z.unlink()
    files = _files(root)
    if not files:
        raise ModsError("empty")
    if kind == "vehicle":
        pkg = _package_root(root)
        found = _vehicle_files(pkg)
        missing = missing_with_options(found)  # the player picks a stand-in for each (a package for an older game)
        if any(x["fatal"] and not x["options"] for x in missing):  # nothing in the game to stand in: it would stop it
            raise ModsError("oldGame", next(x["ref"] for x in missing if x["fatal"] and not x["options"]))
        name = pkg.name if pkg != root else "vehicle"
        plan = _plan(found, ids, game, _folder(name))
        vehicles = _vehicles(found, ids, plan)
        return {"vehicle": {"name": name, "vehicles": vehicles, "files": len(found), "copies": _copies(vehicles, plan), "missing": missing,
                            "missions": [t[-1] for t in _missions(found)],
                            "bytes": sum(f.stat().st_size for f, _ in found)}}
    if kind == "hangar":
        found, line = _hangar_files(root, hint)
        return {"hangar": {"name": _top_name(root), "files": len(found), "bytes": sum(f.stat().st_size for f, _ in found), "line": line}}
    if kind == "sound":
        rels = _sound_paths(root, files)
        if not any(p.suffix.lower() == ".bank" for p in files):
            raise ModsError("noBank")
        return {"sound": {"name": files[0].relative_to(root).parts[0] if len(files[0].relative_to(root).parts) > 1 else "sound", "files": len(rels), "bytes": sum(p.stat().st_size for p in files)}}
    skins = []
    for d in _skin_roots(root):
        inner = _files(d)
        replaced = _replacements(d, inner)
        skins.append({"folder": d.name if d != root else "skin", **guess_vehicle(d.name, [p.name for p in inner], replaced, ids), "files": len(inner),
                      "bytes": sum(p.stat().st_size for p in inner)})
    if not skins:
        raise ModsError("noSkin")
    return {"skins": skins}


def _sound_paths(root: Path, files: list) -> dict:
    """Staged file -> its path under sound/mod: what stands before the banks is the archive's own. A folder named mod starts it."""
    rels = {p: p.relative_to(root).parts for p in files}
    for p, parts in rels.items():
        low = [x.lower() for x in parts[:-1]]
        if "mod" in low:
            rels[p] = parts[len(low) - low[::-1].index("mod"):]
    while len({r[0] for r in rels.values()}) == 1 and all(len(r) > 1 for r in rels.values()):
        rels = {p: r[1:] for p, r in rels.items()}
    return {p: "/".join(r) for p, r in rels.items()}


def _top_name(root: Path) -> str:
    """A package's name: the archive's (its folder in staging)."""
    tops = [p.name for p in root.iterdir() if p.is_dir()] if root.is_dir() else []
    return tops[0] if len(tops) == 1 else "hangar"


def _hangar_files(root: Path, hint: str = "") -> tuple[list, str]:
    """[(file, its place in the game)] of a custom hangar, and the line config.blk needs for it (which the player adds:
    WTFTD leaves config.blk alone): its terrain and textures under content/pkg_local|pkg_user (levels/, res/) and its
    hangar file at the game's root, as its README says (block_island_v2: content/pkg_local/levels/..., island_block_v2.blk;
    Norway: nhg_mission.blk alone, on one of the game's maps). The line from its README, else hint (what its WT Live post
    says: Norway's "nhg_mission"), else its hangar file's name."""
    rels = {f: f.relative_to(root).parts for f in _files(root)}
    while rels and len({r[0].lower() for r in rels.values()}) == 1 and all(len(r) > 1 for r in rels.values()) \
            and next(iter(rels.values()))[0].lower() != "content":
        rels = {f: r[1:] for f, r in rels.items()}  # the archive's own folders
    out, line, blks = [], "", []
    for f, parts in sorted(rels.items(), key=lambda x: x[1]):
        low, suffix = [x.lower() for x in parts], f.suffix.lower()
        if suffix == ".txt":
            found = HANGAR_LINE.search(f.read_text(encoding="utf-8-sig", errors="replace")[:200_000])
            line = line or (found.group(1) if found else "")
        elif len(parts) == 1 and suffix == ".blk":
            out.append((f, parts))
            blks.append(parts[0])
        elif len(parts) > 3 and low[0] == "content" and low[1] in PACKAGES and low[2] in ("levels", "res"):
            out.append((f, ("content", low[1], low[2], *parts[3:])))
        else:
            raise ModsError("hangarPlace", "/".join(parts))
    if not blks:
        raise ModsError("noHangar")
    return out, line or (hint if HINT.fullmatch(hint or "") else "") or blks[0]


def hangars(game: Path) -> list:
    """The hangars WTFTD installed: their line for config.blk and the files still there."""
    out = []
    for name, m in sorted(read_manifest()["hangars"].items()):
        there = [game / rel for rel in m["files"] if (game / rel).is_file()]
        out.append({"name": name, "line": str(m.get("line") or ""), "files": len(there), "bytes": sum(p.stat().st_size for p in there)})
    return out


def _package_root(root: Path) -> Path:
    """The folder holding a vehicle package's content/ and UserMissions/: the staging folder, or the archive's own below it."""
    tops = sorted({d.parent for d in root.rglob("*") if d.is_dir() and d.name.lower() in ("content", "usermissions", *PACKAGES)},
                  key=lambda d: len(d.parts))
    if not tops or any(d != tops[0] for d in tops if len(d.parts) == len(tops[0].parts)):
        raise ModsError("noVehicle")
    return tops[0]


def _vehicle_files(pkg: Path) -> list:
    """[(file, its path in the game folder)]: content/pkg_local|pkg_user/... (the 3D model's .grp and .bin under res/ only)
    and UserMissions/...; gameData written gamedata, as WTFTD writes its own (the Linux client tells cases apart). The
    package's README stays out; anything else refuses the whole."""
    out = []
    for f in _files(pkg):
        parts = f.relative_to(pkg).parts
        if parts[0].lower() in PACKAGES:  # pkg_local without its content/ (the FA-22's): its README says it goes into content/
            parts = ("content", *parts)
        low, suffix = [x.lower() for x in parts], f.suffix.lower()
        if len(parts) == 1 and suffix == ".txt":
            continue
        if low[0] == "usermissions" and len(parts) > 1 and suffix in (".blk", ".csv"):
            out.append((f, ("UserMissions", *parts[1:])))
        elif low[0] == "content" and len(parts) > 3 and low[1] in PACKAGES and suffix in ((".grp", ".bin") if low[2] == "res" else (".blk", ".csv", ".png")):
            out.append((f, ("content", low[1], "gamedata" if low[2] == "gamedata" else parts[2], *parts[3:])))
        else:
            raise ModsError("place", "/".join(parts))
    return out


def _vehicles(found: list, ids=(), plan: dict | None = None) -> list:
    """The vehicles a package declares (flightModels/<id>.blk, units/tankModels/<id>.blk, units/ships/<id>.blk): their name
    from its texts, their first weapon preset, an aircraft's limits from its flight model. One named like the game's
    goes in as a copy with plan (see _plan): the game's would otherwise be replaced in every user mission."""
    from . import blk, builder, models
    from .imports import _texts
    words, by_path = {}, {"/".join(t).lower(): f for f, t in found}
    old = {n for f, t in found if t[-1].lower().endswith(".grp") for n in models.old_models(f)}
    shells = _mission_shells(found)
    for f, t in found:
        if t[-1].lower().endswith(".csv"):
            words.update(_texts(f.read_text(encoding="utf-8-sig", errors="replace")))
    out = []
    for f, t in found:
        dirs = tuple(x.lower() for x in t[3:-1]) if t[0] == "content" and t[2] == "gamedata" else ()
        kind, sub = VEHICLE_DIRS.get(dirs), ""
        if not kind and len(dirs) > 1 and dirs[:-1] in VEHICLE_DIRS:
            kind, sub = VEHICLE_DIRS[dirs[:-1]], t[-2]
        if not kind or not t[-1].lower().endswith(".blk"):
            continue
        stem = t[-1][:-4]
        vid = f"{sub}.{stem}" if sub else stem  # in a folder of its own: not the game's vehicle of that name
        if not re.fullmatch(r"[A-Za-z0-9_\-.]+", vid):
            if sub:
                continue  # in a folder, a file of another kind (the F-22's mig_19.blk.blk is an FM)
            raise ModsError("place", "/".join(t))
        copy = bool(plan) and not sub and vid in set(ids)
        if copy:  # the game's own of that name stays: this one goes in a folder of its own (_copy_pairs)
            sub, vid = plan["folder"], f"{plan['folder']}.{stem}"
        try:
            data = _read_blk(f, t, by_path)
        except (ValueError, IndexError, KeyError, RecursionError):
            if sub:
                continue
            raise ModsError("place", "/".join(t)) from None
        if not data.get("model") or any(v["id"] == vid for v in out):
            continue  # names no model (an empty file, the T-14's flightModels one): not a vehicle; or one already found
        presets = ((data.get("weapon_presets") or {}).get("preset")) if isinstance(data.get("weapon_presets"), dict) else None
        presets = presets if isinstance(presets, list) else [presets] if isinstance(presets, dict) else []
        unit = f"{sub}/{stem}" if sub else stem
        name = words.get(unit) or words.get(f"{unit}_shop") or (stem if copy else sub or stem)  # the Ratte: its folder
        v = {"id": vid, "name": name[:60], "kind": kind, "block": BLOCKS[kind],
             "preset": next((str(x.get("name")) for x in presets if isinstance(x, dict) and x.get("name")), ""),
             "model": str((plan or {}).get("models", {}).get(data["model"], data["model"]))[:120]}  # for the 3D view, its picture
        if sub:
            v["unit"] = unit  # what missions name it
        if copy:
            v["copy"] = stem
        if str(data["model"]).lower() in old:
            v["invisible"] = True  # an old modding kit's model: the game draws an empty stub instead (models.old_layout)
        if kind == "ground":  # its shells when none are picked: empty slots give a mod's tank one round, no reload
            v["ammo"] = shells.get(stem.lower()) or _gun_rounds(data)
        fm_t = tuple("/".join((*t[:4], str(data.get("fmFile") or ""))).split("/"))
        fm = by_path.get("/".join(fm_t).lower()) if kind == "air" and data.get("fmFile") else None
        if kind == "air" and data.get("fmFile"):  # its own, or one of the game's (the CL-1201's turrets fly the A-10C's)
            try:
                found_fm = _read_blk(fm, fm_t, by_path) if fm else _game_blk(fm_t)
                v["lim"] = builder.flight_limits(found_fm, "air") or None if found_fm else None
            except (ValueError, IndexError, KeyError, TypeError, AttributeError, RecursionError):
                pass  # no limits: its alarms and overlay say N/A
        out.append(v)
    if not out:
        raise ModsError("noVehicle")
    names = [v["name"] for v in out]
    for v in out:  # two of the same name (the T-14's Armata and its draft): told apart in WTFTD's lists
        if names.count(v["name"]) > 1:
            v["name"] = f'{v["name"]} ({v["id"]})'[:90]
    return out


# a game file a package's .blk names (its damage model's parts, its weapons, presets, flight model...): the key, the path
GAME_REF = re.compile(r'(?im)^\s*([\w.]+)\s*:\s*t\s*=\s*"((?i:gamedata)[/\\][^"]+?\.blk)"')
FATAL = {"metapartsblk"}  # read for every vehicle as the game starts: one it lacks stops it ("BLK not found", the T-65)
OPTIONS = 40  # stand-ins offered for one file, the closest first


def missing_game_files(found: list) -> list:
    """[(path, fatal)]: the game's files a package's .blk name that the game no longer has (renamed or gone since the
    package was made). The damage model's (MetaPartsBlk) stop the game at its start: the T-65's
    gameData/FlightModels/dm/metaparts/jet_fighter_metaparts.blk, gone by 2.61. The others fail when used (a weapon, a
    preset: the CL-1201's flare_launcher, the FA-22+'s us_aim9jl_sidewinder). Told only where WTFTD has the game's
    folder unpacked and that folder is there: a file of another pack isn't taken for a missing one."""
    from . import builder
    root = builder.DM / "aces.vromfs.bin_u"
    if not root.is_dir():
        return []
    ours = {"/".join(t[2:]).lower() for _, t in found if t[0] == "content"}  # gamedata/... the package brings itself
    out = {}
    for f, t in found:
        if t[0] != "content" or not t[-1].lower().endswith(".blk"):
            continue
        try:
            text = f.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for key, ref in GAME_REF.findall(text):
            parts = ref.replace("\\", "/").lower().split("/")
            if "/".join(parts) in ours or any(x in ("", ".", "..") for x in parts):
                continue
            folder = root.joinpath(*parts[:-1])
            if folder.is_dir() and not (folder / (parts[-1] + "x")).exists() and not (folder / parts[-1]).exists():
                out[ref] = out.get(ref, False) or key.lower() in FATAL
    return sorted(out.items(), key=lambda x: (not x[1], x[0]))


def _engines(found: list, ref: str) -> int | None:
    """How many engines the vehicles naming ref have (their damage model's engineN_dm parts), to rank its stand-ins."""
    n = set()
    for f, t in found:
        if t[-1].lower().endswith(".blk"):
            try:
                text = f.read_text(encoding="utf-8-sig", errors="replace") if isinstance(f, Path) else f
            except OSError:
                continue
            if ref in text:
                n |= set(re.findall(r"\bengine(\d+)_dm\b", text))
    return len(n) or None


_NAMES: dict = {}  # a game folder's file names, kept while it doesn't change: the presets' holds thousands (0.3 s to list)


def _names(folder: Path) -> tuple:
    try:
        mtime = folder.stat().st_mtime
    except OSError:
        return ()
    got = _NAMES.get(str(folder))
    if not got or got[0] != mtime:
        got = _NAMES[str(folder)] = (mtime, tuple(q.name[:-5] for q in folder.glob("*.blkx")))
    return got[1]


def _ranked(ref: str, engines: int | None = None) -> list:
    """[(game path, score)] of the files of ref's folder, the closest first: the most words of the missing name, the
    same number of engines (the T-65's jet_fighter_metaparts, one engine: 1x_engine_jet_fighter_metaparts first)."""
    from . import builder
    parts = ref.replace("\\", "/").split("/")
    names = _names((builder.DM / "aces.vromfs.bin_u").joinpath(*[x.lower() for x in parts[:-1]]))
    want = [w for w in re.split(r"[_\-]+", parts[-1].lower().removesuffix(".blk")) if w and w != "metaparts"]

    def score(name):
        words, count = re.split(r"[_\-]+", name), re.match(r"(\d+)x_engine", name)
        s = 10 * sum(w in words for w in want)
        if engines and count:
            s += 5 if int(count.group(1)) == engines else -3
        return s

    scored = sorted(((score(n), n) for n in names), key=lambda x: (-x[0], len(x[1]), x[1]))
    return [(f"{'/'.join(parts[:-1])}/{n}.blk", sum(w in re.split(r"[_\-]+", n) for w in want) / max(1, len(want))) for s, n in scored]


def replacement_options(ref: str, engines: int | None = None) -> list:
    """The game's files that can stand in for one it no longer has, the closest first (as game paths)."""
    return [path for path, _ in _ranked(ref, engines)]


def _item(found: list, ref: str, fatal: bool, current: str = "") -> dict:
    """One file to stand in for, as the dialog shows it: {ref, fatal, current, best, options}. best: the closest when it
    shares at least half the words of the missing name, else "" (leave it: a mod's own preset has no counterpart in the
    game, and old_jet_mothership isn't alpha_jet_a_m116 for a shared "jet"), which only a file that doesn't stop the
    game may stay."""
    ranked = _ranked(ref, _engines(found, current or ref))
    options = [path for path, _ in ranked[:OPTIONS]]
    if current and current not in options:
        options.insert(0, current)  # the one picked before, whatever its rank
    return {"ref": ref, "fatal": fatal, "current": current, "options": options,
            "best": ranked[0][0] if ranked and (fatal or ranked[0][1] >= 0.5) else ""}


def missing_with_options(found: list) -> list:
    """[{ref, fatal, current, best, options}]: what a package names that the game no longer has, and what may stand in."""
    return [_item(found, ref, fatal) for ref, fatal in missing_game_files(found)]


def _fix_text(text: str, fixes: dict) -> str:
    """A vehicle file with the stand-ins the player picked for the game files the game no longer has (from its original:
    each missing name is replaced, never a stand-in, which two files may share)."""
    for ref, pick in fixes.items():
        if pick:
            text = text.replace(f'"{ref}"', f'"{pick}"')
    return text


def _checked(items: list, fixes) -> dict:
    """{ref: pick or ""}: the player's picks, each one of its file's stand-ins; "" leaves a file that doesn't stop the
    game as it is; a file left out of fixes keeps what it has. A damage model file without one refuses the change:
    installed as it is, it would stop the game at its start."""
    fixes = fixes if isinstance(fixes, dict) else {}
    out = {}
    for it in items:
        pick = str(fixes[it["ref"]] or "") if it["ref"] in fixes else it["current"]
        if pick and pick not in replacement_options(it["ref"]) or not pick and it["fatal"]:
            raise ModsError("oldGame", it["ref"])
        out[it["ref"]] = pick
    return out


def _checked_fixes(found: list, fixes) -> dict:
    """The install's picks (see _checked), the files left as they are included ("")."""
    return _checked([{"ref": ref, "fatal": fatal, "current": ""} for ref, fatal in missing_game_files(found)], fixes)


def repairs(game: Path, name: str) -> list:
    """A package's files to stand in for, for its dialog: those the game no longer has, and those given a stand-in
    before (at install or a Repair), which can be changed again any time. [{ref, fatal, current, best, options}]."""
    m = read_manifest()["vehicles"].get(str(name))
    if not m:
        raise ModsError("notOurs", str(name))
    found, _ = _package_files(game, m)
    record = m.get("fixes") if isinstance(m.get("fixes"), dict) else {}
    # decided: picked before (a file left as it is stays so when the dialog opens again), else the closest shows picked
    out = {x["ref"]: {**x, "decided": x["ref"] in record} for x in missing_with_options(found)}
    for ref, r in record.items():
        if ref not in out and isinstance(r, dict):
            out[ref] = {**_item(found, ref, bool(r.get("fatal")), str(r.get("pick") or "")), "decided": True}
    return sorted(out.values(), key=lambda x: (not x["fatal"], x["ref"]))


def repair(game: Path, name: str, fixes, running: bool = False) -> None:
    """A package's stand-ins changed (Repair, any time, with the game closed): its vehicle files are made again from
    their originals as installed, which the manifest keeps, with the player's picks."""
    if running:
        raise ModsError("running")
    data = read_manifest()
    m = data["vehicles"].get(str(name))
    if not m:
        raise ModsError("notOurs", str(name))
    items = repairs(game, name)
    picks = _checked(items, fixes)
    found, _ = _package_files(game, m)
    originals = dict(m.get("originals") or {})
    for f, t in found:  # a file not yet changed is its own original
        rel = "/".join(t)
        if rel not in originals and t[-1].lower().endswith(".blk") and f.is_file():
            text = f.read_text(encoding="utf-8-sig", errors="replace")
            if any(f'"{ref}"' in text for ref in picks):
                originals[rel] = text
    for rel, text in originals.items():
        target = game.joinpath(*rel.split("/"))
        if target.is_file():
            target.write_text(_fix_text(text, picks), encoding="utf-8")
            if isinstance(m.get("stamps"), dict):  # made again by WTFTD: still its own
                m["stamps"][rel] = _stamp(target)
    m["originals"] = originals
    m["fixes"] = {it["ref"]: {"pick": picks[it["ref"]], "fatal": it["fatal"]} for it in items}
    _write_manifest(data)


def _mission_shells(found: list) -> dict:
    """{vehicle's file name: the four ammo slots the package's missions give it as the player}: the shells its maker
    loads it with (the T-14's 20 3BM42, 10 of its gun's own, 5 ATGM, 10 HE-VT)."""
    from .imports import ImportFailed, read_files
    out = {}
    for f, t in found:
        if t[0] != "UserMissions" or not t[-1].lower().endswith(".blk"):
            continue
        try:
            missions = read_files({t[-1]: f.read_text(encoding="utf-8-sig", errors="replace")})
        except ImportFailed:
            continue
        for m in missions:
            p, count = m["player"], lambda x: x if isinstance(x, int) and not isinstance(x, bool) and x > 0 else 0
            slots = [{"id": str(p.get(f"bullets{i}") or "")[:120], "count": count(p.get(f"bulletsCount{i}"))} for i in range(4)]
            if any(s["count"] for s in slots):
                out.setdefault(str(p.get("unit_class", "")).split("/")[-1].lower(), slots)
    return out


def _gun_rounds(data: dict) -> list:
    """A tank no mission of its package loads: its first gun full of the gun's own shell (an empty name), as many as its
    unit file says it carries."""
    cw = data.get("commonWeapons")
    cw = cw[0] if isinstance(cw, list) and cw else cw
    weapons = cw.get("Weapon") if isinstance(cw, dict) else None
    for w in weapons if isinstance(weapons, list) else [weapons]:
        n = w.get("bullets") if isinstance(w, dict) else None
        if isinstance(n, int) and not isinstance(n, bool) and n > 0:
            return [{"id": "", "count": n}]
    return []


def _game_blk(t: tuple) -> dict:
    """The game's own file at that place of a package (content/pkg_local/gamedata/flightModels/b_52h.blk), as the app
    unpacked it; {} when it hasn't."""
    from . import builder
    if not re.fullmatch(r"[A-Za-z0-9_\-. ]+\.blk", t[-1]) or any(x in ("", ".", "..") for x in t[3:]):
        return {}
    got = builder.load(builder.DM.joinpath("aces.vromfs.bin_u", "gamedata", *[x.lower() for x in t[3:-1]], t[-1].lower() + "x"))
    return got if isinstance(got, dict) else {}


def _merged(data: dict, base) -> dict:
    """A blk as the game reads it after its `include "other.blk"`: the other's entries, then this one's: "@override:x"
    replaces a value or changes a block, "@delete:x" takes it out, the rest is set (what WTFTD reads of it, as the
    CL-1201's weapon presets, is the mod's own)."""
    out = dict(base) if isinstance(base, dict) else {}
    for k, v in data.items():
        if k == "@include":
            continue
        if k.startswith("@delete:"):
            out.pop(k[8:], None)
        elif k.startswith("@override:"):
            out[k[10:]] = _merged(v, out.get(k[10:])) if isinstance(v, dict) else v
        else:
            out[k] = _merged(v, None) if isinstance(v, dict) else v
    return out


def _read_blk(f: Path, t: tuple, by_path: dict, depth: int = 0) -> dict:
    """A package's blk with what it includes: a file of the package next to it, else the game's (the CL-1201 is the
    game's B-52H with its own model, flight model and weapons)."""
    from . import blk
    data = blk.loads(f.read_text(encoding="utf-8-sig", errors="replace"))  # the Ratte's starts with a byte order mark
    inc = data.get("@include")
    if inc is None:
        return data
    if depth > 3:
        raise ValueError("includes too deep")
    for name in inc if isinstance(inc, list) else [inc]:
        at = (*t[:-1], str(name))
        own = by_path.get("/".join(at).lower())
        data = _merged(data, _read_blk(own, at, by_path, depth + 1) if own else _game_blk(at))
    return data


INCLUDE_ROOT = "#/develop/gameBase/"  # an include from anywhere, as WTFTD's own custom vehicles write theirs (cdk.py)
DYNMODEL = 0xB4B7D9C4


def _game_names(game: Path | None) -> tuple[set, set]:
    """The models (and skeletons) and the textures in the game folder now, the game's and mods': a package's of the same
    name would replace them."""
    if game is None:
        return set(), set()
    from . import models
    return {n for _, n in models.index(game)}, set(models.textures(game))


def _cstr(b: bytes, at: int) -> str:
    return bytes(b[at:b.index(b"\0", at)]).decode("utf-8", "replace")


def _grp_names(data: bytes) -> list:
    """(where, name) of each name in a pack's table: its models, skeletons, collisions..."""
    ofs, n = struct.unpack_from("<II", data, 16)
    return [(at, _cstr(data, at)) for at in (struct.unpack_from("<i", data, ofs + 4 * i)[0] for i in range(n))]


def _grp_textures(data: bytes) -> list:
    """(where, name) of the texture names its models carry (a mod's do: the game's are in dynModelDesc.bin)."""
    res, n, out = *struct.unpack_from("<II", data, 32), []
    for i in range(n):
        cid, ofs = struct.unpack_from("<II", data, res + 12 * i)
        if cid != DYNMODEL or struct.unpack_from("<I", data, ofs + 4)[0] == 0xFFFFFFFF:
            continue
        nofs, count = struct.unpack_from("<II", data, ofs + 24)
        out += [(at, _cstr(data, at)) for at in (ofs + 24 + struct.unpack_from("<I", data, ofs + 24 + nofs + 4 * k)[0] for k in range(count))]
    return out


def _dxp_names(data: bytes) -> list:
    """(where, name) of each texture of a texture pack."""
    names_at, n = struct.unpack_from("<II", data, 16)
    return [(at, _cstr(data, at)) for at in (16 + struct.unpack_from("<Q", data, 16 + names_at + 8 * i)[0] for i in range(n))]


def _pack_head(f: Path) -> bytes:
    """The part of a pack its names are in."""
    with f.open("rb") as h:
        head = h.read(16)
        size = struct.unpack_from("<I", head, 12 if head[:4] == b"DxP2" else 4)[0] if len(head) == 16 else 0
        return head + h.read(size + 64)


def _fresh(name: str, taken: set, tails=("",)) -> str:
    """Another name of the same length (a pack keeps its names in place) and the same end (_n, _ao, _skeleton tell what a
    name is), free with each of tails after it: its first two letters changed."""
    for a in "zyxwvutsrq":
        for b in "0123456789":
            new = a + b + name[2:]
            if len(name) > 2 and all(new + t not in taken for t in tails):
                return new
    raise ModsError("place", name)


def _plan(found: list, ids, game: Path | None, folder: str) -> dict:
    """What a package would replace of what's in the game, installed as copies instead: its vehicles named like the game's
    in a folder of their own (as the Ratte is), its models and textures named like ones there renamed (same length)."""
    models_there, textures_there = _game_names(game)
    names, textures = [], []
    for f, t in found:
        try:
            if t[-1].lower().endswith(".grp") and f.stat().st_size > 16:
                head = _pack_head(f)
                if head[:4] in (b"GRP2", b"GRP3"):
                    names += [n for _, n in _grp_names(head)]
            elif t[-1].lower().endswith(".dxp.bin") and f.stat().st_size > 16:
                head = _pack_head(f)
                if head[:4] == b"DxP2":
                    textures += [n.split("*")[0].lower() for _, n in _dxp_names(head)]
        except (struct.error, ValueError, IndexError):
            continue  # a pack WTFTD can't read: copied as it is
    renames, taken = {}, models_there | set(names)
    for base in sorted({n for n in names if n.lower() in models_there and not n.lower().endswith("_skeleton")}):
        family = [n for n in names if n == base or n.startswith(base + "_")]
        new = _fresh(base, taken, [n[len(base):] for n in family])
        renames.update({n: new + n[len(base):] for n in family})
        taken |= set(renames.values())
    tex_renames, taken = {}, textures_there | set(textures)
    for n in sorted(set(textures) & textures_there):
        tex_renames[n] = _fresh(n, taken)
        taken.add(tex_renames[n])
    units = sorted({t[-1][:-4] for f, t in found if t[-1][:-4] in set(ids) and t[-1].lower().endswith(".blk")
                    and t[0] == "content" and tuple(x.lower() for x in t[3:-1]) in VEHICLE_DIRS})
    return {"folder": folder, "units": units, "models": renames, "textures": tex_renames}


def _renamed(data: bytes, places: list, renames: dict) -> bytes:
    """The pack with those names changed in place (same length; a texture name keeps what follows its *)."""
    out = bytearray(data)
    for at, name in places:
        base = name.split("*")[0]
        new = renames.get(base) or renames.get(base.lower())
        if new and len(new) == len(base):
            out[at:at + len(base)] = new.encode()
    return bytes(out)


def _copy_pairs(found: list, vehicles: list, plan: dict) -> list:
    """[(file or bytes, its place in the game)]: the package as it goes in, its copies made (see _plan)."""
    from .cdk import game_data_root
    folder, moved = plan["folder"], {v["unit"].split("/")[-1]: v for v in vehicles if v.get("copy")}
    quoted = [(f'"{a}"', f'"{b}"') for a, b in plan["models"].items()]
    out, places = [], {"/".join(t).lower() for _, t in found}
    for f, t in found:
        low = t[-1].lower()
        if low.endswith(".grp") and (plan["models"] or plan["textures"]):
            data = f.read_bytes()
            try:
                data = _renamed(_renamed(data, _grp_names(data), plan["models"]), _grp_textures(data), plan["textures"])
            except (struct.error, ValueError, IndexError):
                pass
            out.append((data, t))
        elif low.endswith(".dxp.bin") and plan["textures"]:
            data = f.read_bytes()
            try:
                data = _renamed(data, _dxp_names(data), plan["textures"])
            except (struct.error, ValueError, IndexError):
                pass
            out.append((data, t))
        elif low.endswith(".blk") and (t[0] == "content" and (quoted or t[-1][:-4] in moved) or t[0] == "UserMissions" and moved):
            text = f.read_text(encoding="utf-8-sig", errors="replace")
            if t[0] == "UserMissions":  # its missions fly the copy
                for stem, v in moved.items():
                    text = text.replace(f'unit_class:t="{stem}"', f'unit_class:t="{v["unit"]}"')
                out.append((text.encode(), t))
                continue
            for a, b in quoted:
                text = text.replace(a, b)
            v = moved.get(t[-1][:-4]) if tuple(x.lower() for x in t[3:-1]) in VEHICLE_DIRS else None
            if v is None:
                out.append((text.encode(), t))
                continue
            here = f"{game_data_root()}/{GAME_DIRS[tuple(x.lower() for x in t[3:-1])]}/"  # what it includes next to it, from its folder
            text = re.sub(r'(?m)^(\s*include\s+")(?![#/])', lambda m: m.group(1) + INCLUDE_ROOT + here, text)
            at = (*t[:-1], folder, t[-1])
            out.append((text.encode(), at))
            fm = re.search(r'(?m)^\s*fmFile:t="([^"#]+)"', text)
            try:  # a .blk below the vehicle's folder only: ".." passed the name check and reached anywhere in the game
                fm_at = (*t[:-1], folder, *safe_path(fm.group(1))) if fm and fm.group(1).lower().endswith(".blk") else None
            except ModsError:
                fm_at = None
            if fm_at and "/".join(fm_at).lower() not in places and all(re.fullmatch(r"[A-Za-z0-9_\-. ]+", x) for x in fm.group(1).split("/")):
                # its flight model may be looked up next to it (cdk.py writes both for its own): one that includes it
                out.append((f'include "{INCLUDE_ROOT}{here}{fm.group(1)}"\n'.encode(), fm_at))
        else:
            out.append((f, t))
    return out


def _missions(found: list) -> list:
    """The test missions of a package: its UserMissions .blk files that are missions with a player of their own (not a
    template, nor a part other missions include)."""
    from .imports import ImportFailed, read_files
    out = []
    for f, t in found:
        if t[0] == "UserMissions" and t[-1].lower().endswith(".blk"):
            try:
                if read_files({t[-1]: f.read_text(encoding="utf-8-sig", errors="replace")}):
                    out.append(t)
            except ImportFailed:
                pass
    return out


def read_manifest() -> dict:
    try:
        raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    keep = lambda v: {k: x for k, x in v.items() if isinstance(x, dict) and isinstance(x.get("files"), list)} if isinstance(v, dict) else {}  # noqa: E731
    return {"skins": keep(raw.get("skins")), "sounds": keep(raw.get("sounds")), "vehicles": keep(raw.get("vehicles")),
            "hangars": keep(raw.get("hangars"))}


def _write_manifest(data: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(MANIFEST)


def _copy_all(pairs: list) -> None:
    """Each (source, target), nothing left of them if one fails."""
    done = []
    try:
        for src, target in pairs:
            target.parent.mkdir(parents=True, exist_ok=True)
            done.append(target)
            if isinstance(src, bytes):
                target.write_bytes(src)  # a copy WTFTD made (_copy_pairs)
            else:
                shutil.copyfile(src, target)
    except OSError:
        for target in done:
            target.unlink(missing_ok=True)
        raise


def install(game: Path, token: str, kind: str, vehicles: dict | None = None, ids=(), running: bool = False, hint: str = "",
            fixes: dict | None = None) -> dict:
    """Puts what was staged in the game, refusing rather than replacing anything already there, and lists it in the manifest."""
    root = _staging(token)
    if kind not in KINDS or not root.is_dir():
        raise ModsError("empty")
    data = read_manifest()
    if kind == "skin":
        dest = game / SKINS
        dest.mkdir(exist_ok=True)
        roots = _skin_roots(root)
        names = [d.name if d != root else "skin" for d in roots]
        for name in names:
            safe_path(name)
            if _inside(dest, name).exists() or names.count(name) > 1:
                raise ModsError("exists", name)
        pairs = [(p, _inside(dest, name, *p.relative_to(d).parts)) for d, name in zip(roots, names) for p in _files(d)]
        _copy_all(pairs)
        for d, name in zip(roots, names):
            inner = _files(d)
            wanted = (vehicles or {}).get(name)
            guess = guess_vehicle(name, [p.name for p in inner], _replacements(d, inner), ids)
            files = [p.relative_to(d).as_posix() for p in inner]
            data["skins"][name] = {"vehicle": wanted if wanted in set(ids) else guess["vehicle"], "files": files, "stamps": _stamps(dest / name, files)}
    elif kind == "vehicle":  # new files only, the game running or not: it reads them at its next start (the page says so)
        pkg = _package_root(root)
        found = _vehicle_files(pkg)
        picks = _checked_fixes(found, fixes)  # a damage model file the game no longer has: the player's stand-in
        name = pkg.name if pkg != root else "vehicle"
        if name in data["vehicles"]:
            raise ModsError("exists", name)
        plan = _plan(found, ids, game, _folder(name))  # what's named like something in the game goes in as a copy
        vehicles = _vehicles(found, ids, plan)
        placed = _copy_pairs(found, vehicles, plan)
        originals = {}  # the vehicle files as they came: a Repair later makes them again with other picks
        if picks:
            texts = {"/".join(t): (src.decode("utf-8", "replace") if isinstance(src, bytes) else src.read_text(encoding="utf-8-sig", errors="replace"))
                     for src, t in placed if t[-1].lower().endswith(".blk") and t[0] == "content"}
            originals = {rel: text for rel, text in texts.items() if any(f'"{ref}"' in text for ref in picks)}
            placed = [(_fix_text(originals["/".join(t)], picks).encode() if "/".join(t) in originals else src, t) for src, t in placed]
        pairs = [(src, _inside(game, *target)) for src, target in placed]
        for (_, target), (_, path) in zip(placed, pairs):
            if path.exists():
                raise ModsError("exists", "/".join(target))
        _copy_all(pairs)
        data["vehicles"][name] = {"files": ["/".join(t) for _, t in placed], "stamps": _stamps(game, ["/".join(t) for _, t in placed]), "vehicles": vehicles,
                                  "missions": ["/".join(t) for t in _missions(found)], "copies": _copies(vehicles, plan)}
        if picks:
            fatal = dict(missing_game_files(found))
            data["vehicles"][name] |= {"originals": originals, "fixes": {ref: {"pick": pick, "fatal": fatal.get(ref, False)} for ref, pick in picks.items()}}
    elif kind == "hangar":  # new files only (never one of the game's: config.blk is there); config.blk is the player's to change
        found, line = _hangar_files(root, hint)
        name = _top_name(root)
        if name in data["hangars"]:
            raise ModsError("exists", name)
        pairs = [(f, _inside(game, *t)) for f, t in found]
        for (_, t), (_, path) in zip(found, pairs):
            if path.exists():
                raise ModsError("exists", "/".join(t))
        _copy_all(pairs)
        data["hangars"][name] = {"files": ["/".join(t) for _, t in found], "stamps": _stamps(game, ["/".join(t) for _, t in found]), "line": line}
    else:  # new banks only, the game running or not: heard from its next start (the switch, config.blk, waits for it closed)
        dest = game.joinpath(*SOUNDS)
        dest.mkdir(parents=True, exist_ok=True)
        paths = _sound_paths(root, _files(root))
        pairs = [(p, _inside(dest, *safe_path(rel))) for p, rel in paths.items()]
        for _, target in pairs:
            if target.exists():
                raise ModsError("exists", target.name)
        _copy_all(pairs)
        name = inspect(token, "sound")["sound"]["name"]
        while name in data["sounds"]:
            name += "+"
        data["sounds"][name] = {"files": sorted(paths.values()), "stamps": _stamps(dest, paths.values())}
    _write_manifest(data)
    forget(token)
    return data


def _stamp(p: Path) -> list | None:
    try:
        st = p.stat()
        return [st.st_size, st.st_mtime_ns]
    except OSError:
        return None


def _stamps(root: Path, rels) -> dict:
    """Each file as WTFTD put it in place (size, time): one changed since is someone else's, never removed as WTFTD's."""
    return {rel: _stamp(_inside(root, *safe_path(rel))) for rel in rels}


def _remove_files(root: Path, files: list, stamps: dict | None = None) -> int:
    """Only the listed files, then the folders that leaves empty; not one changed since WTFTD put it there (stamps: the
    manifest's, none before 0.33: listed is enough)."""
    n = 0
    stamps = stamps if isinstance(stamps, dict) else {}
    for rel in files:
        try:
            target = _inside(root, *safe_path(rel))
            if stamps.get(rel) and _stamp(target) != stamps[rel]:  # another mod copied over it by hand: theirs now
                continue
            target.unlink()
            n += 1
        except (ModsError, OSError):
            continue
        for d in target.parents:
            if d == root.resolve():
                break
            try:
                d.rmdir()
            except OSError:
                break
    return n


def remove(game: Path, kind: str, name: str, running: bool = False) -> None:
    data = read_manifest()
    if kind == "skin" and name in data["skins"]:
        m = data["skins"].pop(name)
        _remove_files(game / SKINS / safe_path(name)[0], m["files"], m.get("stamps"))
        try:
            (game / SKINS / name).rmdir()
        except OSError:
            pass
    elif kind == "vehicle" and name in data["vehicles"]:
        if running:
            raise ModsError("running")  # the game may hold its files open: half removed, the rest would be nobody's
        m = data["vehicles"].pop(name)
        _remove_files(game, m["files"], m.get("stamps"))
    elif kind == "sound" and name in data["sounds"]:
        if running:
            raise ModsError("running")  # its banks may be open in the game
        m = data["sounds"].pop(name)
        _remove_files(game.joinpath(*SOUNDS), m["files"], m.get("stamps"))
    elif kind == "hangar" and name in data["hangars"]:
        if running:
            raise ModsError("running")  # its terrain may be the hangar the game shows
        m = data["hangars"].pop(name)
        _remove_files(game, m["files"], m.get("stamps"))
    else:
        raise ModsError("notOurs", str(name))
    _write_manifest(data)


# ------------------------------------------------------------------ config.blk
def _enable_line(raw: bytes):
    """The sound block's enable_mod line: (block found, match or None). Only that block: its nested ones and the others don't count."""
    open_ = SOUND_BLOCK.search(raw)
    if not open_:
        return False, None
    depth, i = 1, open_.end()
    while i < len(raw) and depth:
        depth += (raw[i] == 123) - (raw[i] == 125)
        i += 1
    if depth:
        return False, None
    return True, ENABLE.search(raw, open_.end(), i)


def _is_on(line) -> bool:
    return bool(line) and line.group(1).lower() in (b"yes", b"true", b"1")


def _write_config(game: Path, raw: bytes) -> None:
    tmp = game / "config.blk.wtftd"
    tmp.write_bytes(raw)
    tmp.replace(game / "config.blk")


def sound_state(game: Path) -> dict:
    """on: the game loads sound mods; ours: by WTFTD's own line (else the player's, left alone); block: the file can take the line."""
    try:
        block, line = _enable_line((game / "config.blk").read_bytes())
    except OSError:
        return {"on": False, "ours": False, "block": False}
    return {"on": _is_on(line), "ours": BACKUP.exists(), "block": block}


def set_sound(game: Path, on: bool, running: bool) -> None:
    """The switch. On: a copy of the file, then the one line. Off: that line goes, whatever the game saved around it since."""
    if running:
        raise ModsError("running")  # it may write the file back as it exits
    path = game / "config.blk"
    raw = path.read_bytes()
    block, line = _enable_line(raw)
    if not block:
        raise ModsError("noBlock")
    if on:
        if _is_on(line):
            if not BACKUP.exists():
                raise ModsError("byHand")
            return
        BACKUP.parent.mkdir(parents=True, exist_ok=True)
        tmp = BACKUP.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(BACKUP)
        if line:  # the player's own enable_mod:b=no
            _write_config(game, raw[:line.start(1)] + b"yes" + raw[line.end(1):])
        else:
            at = SOUND_BLOCK.search(raw).end()
            eol = b"\r\n" if raw[at - 2:at] == b"\r\n" else b"\n"
            _write_config(game, raw[:at] + b"  enable_mod:b=yes" + eol + raw[at:])
        return
    if not BACKUP.exists():
        if _is_on(line):
            raise ModsError("byHand")
        return
    if _is_on(line):
        was = _enable_line(BACKUP.read_bytes())[1]
        _write_config(game, raw[:line.start(1)] + was.group(1) + raw[line.end(1):] if was else raw[:line.start()] + raw[line.end():])
    BACKUP.unlink()


# ------------------------------------------------------------------ what's there
def skins(game: Path, ids=()) -> list:
    root, ours = game / SKINS, read_manifest()["skins"]
    out = []
    for d in sorted(root.iterdir(), key=lambda p: p.name.lower()) if root.is_dir() else ():
        if not d.is_dir() or d.is_symlink() or d.name == TEMP:
            continue
        files = _files(d)
        replaced = _replacements(d, files)
        guess = guess_vehicle(d.name, [p.name for p in files], replaced, ids)
        mine = ours.get(d.name)
        vehicle = (mine or {}).get("vehicle") or guess["vehicle"]
        out.append({"name": d.name, "vehicle": vehicle, "vehicles": list(dict.fromkeys(v for v in (vehicle, *guess.get("vehicles", ())) if v)),
                    "sure": bool(mine) or guess["sure"], "ours": bool(mine),
                    "files": len(files), "bytes": sum(p.stat().st_size for p in files), "replace": replaced})
    return out


def vehicle_packages(game: Path) -> list:
    """The vehicle packages WTFTD installed: their vehicles, test missions and the files still there."""
    out = []
    for name, m in sorted(read_manifest()["vehicles"].items()):
        there = [game / rel for rel in m["files"] if (game / rel).is_file()]
        out.append({"name": name, "vehicles": m.get("vehicles") or [], "missions": [Path(x).name for x in m.get("missions") or []],
                    "files": len(there), "bytes": sum(p.stat().st_size for p in there),
                    "stops": [{"ref": ref, "fatal": fatal} for ref, fatal in missing_game_files(_package_files(game, m)[0])],
                    "fixed": len(m.get("fixes") or {})})  # what Repair offers (its stand-ins come with mods/repairs, when asked)
    return out


def remove_mission(game: Path, rel: str) -> bool:
    """One of a package's missions out of the game (UserMissions/<rel>), its vehicle staying: the file, and the texts
    of its folder once no mission of the package is left there. False for a file no package put there."""
    data, full = read_manifest(), f"UserMissions/{rel}"
    for m in data["vehicles"].values():
        if full not in m["files"]:
            continue
        folder = full.rsplit("/", 1)[0] + "/"
        beside = [f for f in m["files"] if f.startswith(folder) and "/" not in f[len(folder):] and f != full]
        gone = [full, *([f for f in beside if f.lower().endswith(".csv")] if not any(f.lower().endswith(".blk") for f in beside) else [])]
        _remove_files(game, gone, m.get("stamps"))
        m["files"] = [f for f in m["files"] if f not in gone]
        m["missions"] = [f for f in m.get("missions") or [] if f != full]
        _write_manifest(data)
        return True
    return False


def mod_vehicles() -> dict:
    """{id: vehicle} of the packages installed, for WTFTD's lists: see server.STATE."""
    return {v["id"]: {**v, "package": name} for name, m in read_manifest()["vehicles"].items() for v in m.get("vehicles") or []
            if isinstance(v, dict) and isinstance(v.get("id"), str)}


def _package_files(game: Path, m: dict) -> tuple[list, dict]:
    """A package's files in the game as _vehicle_files found them: [(path, its place)], and the places' index."""
    found = [(game.joinpath(*rel.split("/")), tuple(rel.split("/"))) for rel in m["files"] if isinstance(rel, str)]
    return found, {"/".join(t).lower(): f for f, t in found}


def package_weapons(game: Path, known: dict) -> dict:
    """The weapons an aircraft can carry that the vehicle packages brought (the J-50's PL-15 and PL-10, the F-22 free
    flight's missiles, the CL-1201's bomb), as the pylon catalog has the game's (builder.air_weapon_entry): {file name:
    entry, its package, its name from the package's texts, its model}. Not their containers (the J-50's bays), nor the
    tanks' and ships' weapons; nor one named like the game's (known), which the game lists already."""
    from . import builder
    from .imports import _texts
    out: dict = {}
    icons = {w.get("ic") for w in known.values() if isinstance(w, dict)}
    for pkg, m in sorted(read_manifest()["vehicles"].items()):
        found, by_path = _package_files(game, m)
        words: dict = {}
        for f, t in found:
            if t[-1].lower().endswith(".csv") and f.is_file():
                words.update(_texts(f.read_text(encoding="utf-8-sig", errors="replace")))
        for f, t in found:
            low = [x.lower() for x in t]
            folder = low[4] if len(t) == 6 else ""
            if (len(t) not in (5, 6) or low[:1] + low[2:4] != ["content", "gamedata", "weapons"] or not low[-1].endswith(".blk")
                    or folder not in ("", *builder.CATALOG_FOLDERS) or folder == "containers"):
                continue
            key = low[-1][:-4]
            if key in known or key in out or not re.fullmatch(r"[a-z0-9_\-.]+", key):
                continue
            try:
                d = _read_blk(f, t, by_path)
            except (OSError, ValueError, IndexError, KeyError, RecursionError):
                continue  # a file gone, or one WTFTD can't read: not offered
            entry = builder.air_weapon_entry(d, folder, "/".join(("gamedata", *t[3:])))  # as it lies in the game, cases kept
            if not entry:
                continue
            payload = builder._payload(d)[1] or {}
            ic = builder.first_str(payload.get("iconType"))  # the game's icon it names, if the game has it
            name = words.get(f"weapons/{key}/short") or words.get(f"weapons/{key}") or builder.humanize(key)
            out[key] = {**entry, "ic": ic if ic in icons else builder.CATEGORY_ICONS.get(entry["c"], "bombs_middle"),
                        "pkg": pkg, "name": name[:80], "md": str(d.get("mesh") or payload.get("mesh") or "")[:120],
                        "f": "/".join(t)}
    return out


def package_weapon(game: Path, rel: str) -> dict:
    """A package's weapon file as the game reads it (with what it includes), {} for one no package put there."""
    for m in read_manifest()["vehicles"].values():
        if rel in m["files"]:
            _, by_path = _package_files(game, m)
            try:
                return _read_blk(game.joinpath(*rel.split("/")), tuple(rel.split("/")), by_path)
            except (OSError, ValueError, IndexError, KeyError, RecursionError):
                return {}
    return {}


def sounds(game: Path) -> list:
    root, ours = game.joinpath(*SOUNDS), read_manifest()["sounds"]
    listed = {rel for m in ours.values() for rel in m["files"]}
    size = lambda rel: (root / rel).stat().st_size if (root / rel).is_file() else 0  # noqa: E731
    out = [{"name": n, "ours": True, "files": len(m["files"]), "bytes": sum(map(size, m["files"]))} for n, m in sorted(ours.items())]
    if root.is_dir():
        for p in _files(root):
            rel = p.relative_to(root).as_posix()
            if rel not in listed:
                out.append({"name": rel, "ours": False, "files": 1, "bytes": p.stat().st_size})
    return out


def skin_file(game: Path, folder: str, file: str) -> Path | None:
    """A skin's texture for the 3D view."""
    try:
        target = _inside(game / SKINS, *safe_path(folder), *safe_path(file))
    except ModsError:
        return None
    return target if target.suffix.lower() in TEXTURES and target.is_file() else None


def counts() -> dict:
    data = read_manifest()
    return {"skins": len(data["skins"]), "sounds": len(data["sounds"]), "vehicles": len(data["vehicles"]),
            "hangars": len(data["hangars"]), "config": BACKUP.exists()}


def remove_all(game: Path, running: bool) -> dict:
    """Uninstall: what WTFTD installed goes and config.blk gets its line back. The game running, the file is left for a later try,
    and so are the manifest and the copy that say so."""
    data = read_manifest()
    n = 0
    for name, m in data["skins"].items():
        n += _remove_files(game / SKINS / safe_path(name)[0], m["files"], m.get("stamps"))
        try:
            (game / SKINS / name).rmdir()
        except OSError:
            pass
    if not running:  # the game reads these as it runs: left for a later try
        for m in data["sounds"].values():
            n += _remove_files(game.joinpath(*SOUNDS), m["files"], m.get("stamps"))
        for m in [*data["vehicles"].values(), *data["hangars"].values()]:
            n += _remove_files(game, m["files"], m.get("stamps"))
    kept = False
    if BACKUP.exists():
        try:
            set_sound(game, False, running)
        except (ModsError, OSError):
            kept = True
    if running or kept:
        _write_manifest({"skins": {}, "sounds": data["sounds"] if running else {}, "vehicles": data["vehicles"] if running else {},
                         "hangars": data["hangars"] if running else {}})
    else:
        MANIFEST.unlink(missing_ok=True)
    return {"files": n, "kept": kept or (running and bool(data["sounds"] or data["vehicles"] or data["hangars"]))}
