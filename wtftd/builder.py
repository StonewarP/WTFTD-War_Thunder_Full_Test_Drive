"""Builds the app database from the community War Thunder datamine.

Source: https://github.com/gszabi99/War-Thunder-Datamine (sparse git clone, ~1 GB on disk).
Output (in ./data):
  meta.json          game version + build date
  vehicles.json      compact vehicle list for the browser grid
  details.json       per-vehicle loadouts / ammo (served one vehicle at a time)
  trees.json         in-game research trees per nation and vehicle type
  scenarios.json     official test drive / test flight missions usable as maps
  scenarios/<id>.json  the raw official missions (rebuilt to .blk with your vehicle)
  lang/<code>.json   vehicle / weapon / ammo / map names for every game language

Run:  python -m wtftd.builder            (clone or update the datamine, then build)
      python -m wtftd.builder --no-pull  (build from the existing clone)
"""
from __future__ import annotations

import csv
import math
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

from .paths import CACHE, DATA, HOME as ROOT
DM = CACHE / "datamine"
SCHEMA = 5  # bump when data/*.json gains fields the app needs: installed data gets rebuilt
REPO = "https://github.com/gszabi99/War-Thunder-Datamine.git"
SPARSE = [
    "aces.vromfs.bin_u/gamedata/flightmodels",
    "aces.vromfs.bin_u/gamedata/units/tankmodels",
    "aces.vromfs.bin_u/gamedata/units/ships",
    "aces.vromfs.bin_u/gamedata/weapons",
    "aces.vromfs.bin_u/gamedata/damage_model",
    "char.vromfs.bin_u/config",
    "lang.vromfs.bin_u/lang",
    "mis.vromfs.bin_u/gamedata/missions",
    "aces.vromfs.bin_u/config",
    "aces.vromfs.bin_u/levels",
]

# CSV column -> short language code used by the app
LANG_COLUMNS = {
    "<English>": "en", "<French>": "fr", "<Italian>": "it", "<German>": "de",
    "<Spanish>": "es", "<Russian>": "ru", "<Polish>": "pl", "<Czech>": "cs",
    "<Turkish>": "tr", "<Chinese>": "zh", "<Japanese>": "ja", "<Portuguese>": "pt",
    "<Ukrainian>": "uk", "<Serbian>": "sr", "<Hungarian>": "hu", "<Korean>": "ko",
    "<Belarusian>": "be", "<Romanian>": "ro", "<TChinese>": "zh-TW", "<Vietnamese>": "vi",
}

COUNTRIES = ["usa", "germany", "ussr", "britain", "japan", "china", "italy", "france", "sweden", "israel"]

Progress = callable


def log(msg: str, progress=None):
    print(msg, flush=True)
    if progress:
        progress(msg)


def report(progress, frac: float):
    """Overall progress of an update, 0..1 (for the UI's progress bar)."""
    if progress is not None and hasattr(progress, "set_frac"):
        progress.set_frac(max(0.0, min(1.0, frac)))


DM_BYTES = 1.2e9  # size of the checked-out datamine folders, to show the first download's progress


def _watch_size(folder: Path, progress, lo: float, hi: float, stop: threading.Event):
    """First download: git first fetches the repository index (nothing written for ~40 s, shown as a slow
    time-based advance up to 'mid'), then writes the files (progress = size on disk)."""
    mid = lo + (hi - lo) * 0.3
    t0 = time.time()
    while not stop.wait(1.5):
        total = 0
        for root, _, files in os.walk(folder):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        by_time = lo + (mid - lo) * (1 - math.exp(-(time.time() - t0) / 25))
        by_size = mid + (hi - mid) * min(total / DM_BYTES, 1.0) if total > 5e7 else 0.0
        report(progress, max(by_time, by_size))


# --------------------------------------------------------------------------- helpers

def aslist(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def load(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def first_str(v) -> str:
    for x in aslist(v):
        if isinstance(x, str) and x:
            return x
    return ""


def num(v, default=0) -> int:
    for x in aslist(v):
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            return int(x)
    return default


def blk_to_path(blk: str) -> Path:
    """'gameData/Weapons/foo/Bar.blk' -> datamine path to the .blkx file."""
    rel = blk.replace("\\", "/").lower()
    if rel.endswith(".blk"):
        rel = rel[:-4] + ".blkx"
    return DM / "aces.vromfs.bin_u" / rel


def basename(blk: str) -> str:
    return blk.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()


ZW = re.compile("[\u200b\u200c\u200d\ufeff]")
# War Thunder font glyphs (country-of-origin marks, icons) that render as junk outside the game
GLYPHS = re.compile("[\u2400-\u243f\u2580-\u25ff\u2600-\u26ff\u22e0\ue000-\uf8ff]")


def clean(s: str) -> str:
    s = ZW.sub("", s or "").replace("\u00a0", " ")
    return re.sub(r"\s{2,}", " ", GLYPHS.sub("", s)).strip()


# --------------------------------------------------------------------------- datamine

MINGIT = CACHE / "mingit"
_git_exe: str | None = None


def find_git(progress=None) -> str:
    """Git of this PC, or else the official portable MinGit (git-for-windows), downloaded once."""
    global _git_exe
    if _git_exe:
        return _git_exe
    found = shutil.which("git")
    for cand in ([found] if found else []) + [str(MINGIT / "cmd" / "git.exe"),
                                              r"C:\Program Files\Git\cmd\git.exe"]:
        if cand and Path(cand).is_file():
            _git_exe = cand
            return cand
    if sys.platform != "win32":
        raise RuntimeError("Git is required: install it from https://git-scm.com")
    log("Git not found: downloading the portable MinGit (git-for-windows, ~40 MB, once)...", progress)
    req = urllib.request.Request("https://api.github.com/repos/git-for-windows/git/releases/latest",
                                 headers={"User-Agent": "WTFTD", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        assets = json.load(r).get("assets", [])
    url = next((a["browser_download_url"] for a in assets
                if re.fullmatch(r"MinGit-[\d.]+(?:\.windows\.\d+)?-64-bit\.zip", a.get("name", ""))), None)
    if not url:
        raise RuntimeError("Could not find MinGit. Install Git from https://git-scm.com and retry.")
    if not url.startswith("https://github.com/git-for-windows/git/releases/download/"):
        raise RuntimeError("Unexpected MinGit download location")
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = CACHE / "mingit.zip"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "WTFTD"}), timeout=120) as r,             open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    shutil.rmtree(MINGIT, ignore_errors=True)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(MINGIT)
    tmp.unlink()
    _git_exe = str(MINGIT / "cmd" / "git.exe")
    return _git_exe


def git(*args, cwd=None):
    # no console window flashing from the packaged (windowed) app
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run([find_git(), "-c", "core.longpaths=true", *args], cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags)


def fetch_datamine(progress=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    find_git(progress)
    if not (DM / ".git").exists():
        shutil.rmtree(DM, ignore_errors=True)  # leftover of an interrupted first download
        log("Downloading the War Thunder datamine (community, ~1 GB, first run takes a few minutes)...", progress)
        report(progress, 0.03)
        stop = threading.Event()
        threading.Thread(target=_watch_size, args=(DM, progress, 0.04, 0.45, stop), daemon=True).start()
        try:
            git("clone", "--filter=blob:none", "--no-checkout", "--depth", "1", REPO, str(DM))
            git("sparse-checkout", "init", "--cone", cwd=DM)
            git("sparse-checkout", "set", *SPARSE, cwd=DM)
            git("checkout", "master", cwd=DM)
        finally:
            stop.set()
    else:
        log("Updating the War Thunder datamine...", progress)
        report(progress, 0.05)
        git("sparse-checkout", "set", *SPARSE, cwd=DM)
        git("fetch", "--depth", "1", "origin", "master", cwd=DM)
        git("reset", "--hard", "origin/master", cwd=DM)
    report(progress, 0.45)


# --------------------------------------------------------------------------- languages

def read_lang_csv(name: str) -> dict[str, dict[str, str]]:
    """Returns {key: {lang: text}}."""
    path = DM / "lang.vromfs.bin_u" / "lang" / name
    out: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=";", quotechar='"')
        header = next(reader)
        cols = [(i, LANG_COLUMNS[h]) for i, h in enumerate(header) if h in LANG_COLUMNS]
        for row in reader:
            if not row:
                continue
            key = row[0]
            vals = {}
            for i, code in cols:
                if i < len(row) and row[i]:
                    vals[code] = clean(row[i])
            out[key] = vals
    return out


class Lang:
    def __init__(self):
        self.tables = {}
        for n in ("units.csv", "units_weaponry.csv", "units_modifications.csv", "missions_locations.csv", "menu.csv"):
            try:
                self.tables[n] = read_lang_csv(n)
            except OSError:
                self.tables[n] = {}
        self.all = {}
        for t in self.tables.values():
            for k, v in t.items():
                self.all.setdefault(k, v)
        self.lower = {k.lower(): k for k in self.all}
        # collected output: {section: {key: {lang: text}}}
        self.out: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)

    def get(self, key: str):
        v = self.all.get(key)
        if v is None:
            k = self.lower.get(key.lower())
            v = self.all.get(k) if k else None
        return v

    def put(self, section: str, key: str, *candidates: str, fallback: str | None = None) -> bool:
        for c in candidates:
            v = self.get(c)
            if v and v.get("en"):
                self.out[section][key] = v
                return True
        if fallback:
            self.out[section][key] = {"en": fallback}
        return False

    def write(self):
        (DATA / "lang").mkdir(parents=True, exist_ok=True)
        codes = set()
        for sec in self.out.values():
            for v in sec.values():
                codes.update(v)
        for code in sorted(codes):
            data = {}
            for sec, entries in self.out.items():
                d = {}
                for k, v in entries.items():
                    t = v.get(code)
                    if t and (code == "en" or t != v.get("en")):
                        d[k] = t
                data[sec] = d
            with open(DATA / "lang" / f"{code}.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        return sorted(codes)


def humanize(s: str) -> str:
    s = re.sub(r"[_\-]+", " ", s).strip()
    return " ".join(w.upper() if len(w) <= 3 or any(ch.isdigit() for ch in w) else w.capitalize() for w in s.split())


# --------------------------------------------------------------------------- vehicles

def br_from(er):
    if er is None:
        return None
    return round(1.0 + er / 3.0, 1)


def categorize(move_type: str, unit_class: str) -> str:
    if move_type in ("tank", "heavy_tank", "wheeled_vehicle"):
        return "ground"
    if move_type == "helicopter":
        return "heli"
    if move_type == "air":
        return "air"
    if move_type == "fast_ship":
        return "boat"
    if move_type in ("ship", "slow_ship"):
        return "ship"
    return "other"


UNIT_BLOCK = {"ground": "tankModels", "air": "armada", "heli": "armada", "boat": "ships", "ship": "ships"}


def unit_file(vid: str, cat: str) -> Path:
    base = DM / "aces.vromfs.bin_u" / "gamedata"
    if cat == "ground":
        return base / "units" / "tankmodels" / f"{vid.lower()}.blkx"
    if cat in ("boat", "ship"):
        return base / "units" / "ships" / f"{vid.lower()}.blkx"
    return base / "flightmodels" / f"{vid.lower()}.blkx"


class WeaponCache:
    def __init__(self, lang: Lang):
        self.lang = lang
        self.cache: dict[str, dict | None] = {}

    def get(self, blk: str):
        key = blk.lower()
        if key not in self.cache:
            self.cache[key] = load(blk_to_path(blk))
        return self.cache[key]

    def weapon_name(self, blk: str) -> str:
        """Registers a localized name for a weapon blk, returns its key."""
        key = basename(blk)
        if key not in self.lang.out["weapons"]:
            if not self.lang.put("weapons", key, f"weapons/{key}", key):
                # containers: name after the inner weapon
                d = self.get(blk) or {}
                inner = None
                for w in aslist(d.get("Weapon")) + aslist((d.get("weapons") or {}).get("Weapon") if isinstance(d.get("weapons"), dict) else None):
                    if isinstance(w, dict) and first_str(w.get("blk")):
                        inner = w
                        break
                if inner:
                    ik = self.weapon_name(first_str(inner["blk"]))
                    n = num(inner.get("bullets"), 1) or 1
                    en = self.lang.out["weapons"].get(ik, {}).get("en", humanize(ik))
                    self.lang.out["weapons"][key] = {"en": f"{n}× {en}" if n > 1 else en}
                else:
                    self.lang.out["weapons"][key] = {"en": humanize(key)}
        return key

    def bullet_sets(self, blk: str):
        """Returns (default_set, {mod_name: set}) where set = {'b': [bulletName], 't': [bulletType]}."""
        d = self.get(blk)
        if not d:
            return None, {}

        def describe(b):
            names, types = [], []
            first = next((x for x in aslist(b.get("bullet")) if isinstance(x, dict)), None)
            for x in aslist(b.get("bullet")):
                if not isinstance(x, dict):
                    continue
                for bn in aslist(x.get("bulletName")):
                    if isinstance(bn, str) and bn and bn not in names:
                        names.append(bn)
                        self.lang.put("bullets", bn, bn, fallback=bn.split("_", 1)[-1].upper())
                for bt in aslist(x.get("bulletType")):
                    if isinstance(bt, str) and bt and bt not in types:
                        types.append(bt)
                        self.lang.put("btypes", bt, f"{bt}/name/short", f"{bt}_ball/name/short", fallback=bt.upper())
            out = {"b": names, "t": types}
            st = shell_stats(first)
            if st:
                out["s"] = st
            return out

        default = describe(d) if d.get("bullet") else None
        sets = {}
        for k, v in d.items():
            if isinstance(v, dict) and "bullet" in v:
                sets[k] = describe(v)
        return default, sets


def _numval(v):
    v = v[0] if isinstance(v, list) and v else v
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def shell_stats(b: dict | None) -> dict:
    """Editable shell values: v speed (m/s), m mass (kg), e explosive mass (kg), h HEAT penetration (mm),
    l APFSDS rod working length (mm)."""
    if not isinstance(b, dict):
        return {}
    out = {}
    for key, src in (("v", b.get("speed")), ("m", b.get("mass")), ("e", b.get("explosiveMass"))):
        val = _numval(src)
        if val is not None:
            out[key] = round(val, 4)
    cum = b.get("cumulativeDamage")
    if isinstance(cum, dict) and _numval(cum.get("armorPower")) is not None:
        out["h"] = _numval(cum.get("armorPower"))
    kin = (b.get("damage") or {}).get("kinetic") if isinstance(b.get("damage"), dict) else None
    if isinstance(kin, dict) and _numval(kin.get("lanzOdermattWorkingLength")) is not None:
        out["l"] = _numval(kin.get("lanzOdermattWorkingLength"))
    return out


def weapons_composition(weapons, wc: "WeaponCache") -> list:
    counts: dict[str, int] = {}
    for w in weapons:
        blk = first_str(w.get("blk")) if isinstance(w, dict) else ""
        if not blk or w.get("dummy"):
            continue
        trig = first_str(w.get("trigger")).lower()
        if trig == "countermeasures":
            continue
        n = num(w.get("bullets"), 1) or 1
        cont = wc.get(blk) if "container" in blk.lower() else None
        if isinstance(cont, dict) and cont.get("container") and first_str(cont.get("blk")):
            blk = first_str(cont.get("blk"))
            n = num(cont.get("bullets"), 1) or 1
        k = wc.weapon_name(blk)
        if trig in ("machine gun", "cannon", "gunner0", "gunner1", "additional gun"):
            n = 1
        counts[k] = counts.get(k, 0) + int(n)
    return [[k, v] for k, v in counts.items()]


ICON_VOTES: dict = {}  # weapon key -> {iconType: count}, to give catalog weapons the game's own icon
CATEGORY_ICONS = {"aam_ir": "missile_air_to_air", "aam_radar": "missile_air_to_air_midrange", "agm": "missile_air_to_uni",
                  "atgm": "missile_air_to_uni_middle", "rockets": "rockets_he_large", "bombs": "bombs_middle",
                  "guided_bombs": "guided_bomb_middle_laser", "nuke": "bombs_special", "fuel": "ptb",
                  "pods": "ltc", "torpedoes": "torpedo", "mines": "bombs_special"}


def weapon_slots(udata: dict, wc: "WeaponCache") -> list:
    """Pylons for custom aircraft loadouts: [{"i": slot index, "o": [{"n": preset, "w": composition}]}]."""
    ws = udata.get("WeaponSlots")
    if not isinstance(ws, dict):
        return []
    common = {w.get("slot") for w in aslist((udata.get("commonWeapons") or {}).get("Weapon")) if isinstance(w, dict) and "slot" in w}
    out = []
    for sl in aslist(ws.get("WeaponSlot")):
        if not isinstance(sl, dict) or sl.get("index") in common:
            continue
        opts, emitter = [], ""
        for wp in aslist(sl.get("WeaponPreset")):
            if isinstance(wp, dict) and wp.get("name"):
                comp = weapons_composition(aslist(wp.get("Weapon")), wc)
                if comp:
                    o = {"n": wp["name"], "w": comp}
                    icon = first_str(wp.get("iconType"))
                    if icon:
                        o["ic"] = icon
                        for k, _ in comp:
                            ICON_VOTES.setdefault(k, {}).setdefault(icon, 0)
                            ICON_VOTES[k][icon] += 1
                    opts.append(o)
                for w in aslist(wp.get("Weapon")):
                    if not emitter and isinstance(w, dict) and w.get("external") and first_str(w.get("trigger")) != "countermeasures":
                        emitter = first_str(w.get("emitter"))
        if opts:
            out.append({"i": sl.get("index"), "o": opts, "e": emitter, "t": num(sl.get("tier"), num(sl.get("index")))})
    out.sort(key=lambda x: x["i"] if isinstance(x["i"], int) else 0)
    return out


# real nuclear bombs of the game (the plain us_b61 / su_rn_28 files are inert dummies)
NUKES = ("su_rn_28_nt", "su_rn_40", "us_b61_5kt", "us_b61_30kt", "fr_an52_5kt_nt", "fr_an52_30kt_nt",
         "cn_kb1_5kt", "cn_kb1_30kt", "su_rds4_5kt_nt", "su_rds4_30kt_nt", "su_rds37")


def pylon_emitters(udata: dict) -> list:
    """Emitter nodes where this aircraft carries external stores, bomb points first."""
    bombs, other = [], []
    ws = udata.get("WeaponSlots")
    for sl in aslist(ws.get("WeaponSlot")) if isinstance(ws, dict) else []:
        for wp in aslist(sl.get("WeaponPreset")) if isinstance(sl, dict) else []:
            for w in aslist(wp.get("Weapon")) if isinstance(wp, dict) else []:
                if not isinstance(w, dict):
                    continue
                em = first_str(w.get("emitter"))
                if not em or not w.get("external") or first_str(w.get("trigger")) == "countermeasures":
                    continue
                (bombs if first_str(w.get("trigger")) == "bombs" else other).append(em)
    for p in aslist((udata.get("weapon_presets") or {}).get("preset")):
        pdata = load(blk_to_path(first_str(p.get("blk")))) if isinstance(p, dict) and p.get("blk") else None
        for w in aslist((pdata or {}).get("Weapon")):
            if isinstance(w, dict) and first_str(w.get("emitter")) and first_str(w.get("trigger")) != "countermeasures":
                (bombs if first_str(w.get("trigger")) == "bombs" else other).append(first_str(w["emitter"]))
    out = []
    for em in bombs + other:
        if em not in out:
            out.append(em)
    return out[:3]


def _r1(x, nd=1):
    return round(float(x), nd) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


_CAL_CACHE: dict = {}


def _caliber_mm(blk: str) -> float | None:
    if blk in _CAL_CACHE:
        return _CAL_CACHE[blk]
    _CAL_CACHE[blk] = None
    d = load(blk_to_path(blk)) if blk else None
    for b in aslist((d or {}).get("bullet")):
        if isinstance(b, dict) and isinstance(b.get("caliber"), (int, float)):
            _CAL_CACHE[blk] = round(b["caliber"] * 1000, 1)
            break
    return _CAL_CACHE[blk]


def ground_speeds(udata: dict) -> tuple[float | None, float | None]:
    """Top forward / reverse speed (km/h) from the gearbox: max RPM through the highest gear."""
    try:
        m = udata["VehiclePhys"]["mechanics"]
        rpm = float(udata["VehiclePhys"]["engine"]["maxRPM"])
        gears = [float(g) for g in aslist((m.get("gearRatios") or {}).get("ratio")) if isinstance(g, (int, float))]
        k = rpm * 2 * math.pi * float(m["driveGearRadius"]) * 60 / 1000 / (float(m["mainGearRatio"]) * float(m.get("sideGearRatio", 1)))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None, None
    fwd = [g for g in gears if g > 0]
    rev = [-g for g in gears if g < 0]
    return (round(k / min(fwd)) if fwd else None), (round(k / min(rev)) if rev else None)


def vehicle_stats(cat: str, udata: dict, wp: dict, tags: dict, st: dict, ammo: list) -> dict:
    """Comparable stats of a vehicle for the list (sort / filter) and the vehicle card. Units: km/h, m,
    m/s, s, deg/s, mm, t, hp/t. Air values are the game's own stat card (unittags Shop block)."""
    shop = (tags or {}).get("Shop") or {}
    out = {}
    if cat in ("air", "heli"):
        if shop.get("maxSpeed"):
            out["spd"] = round(shop["maxSpeed"] * 3.6)
        for key, src in (("alt", "maxSpeedAlt"), ("ceil", "maxAltitude"), ("turn", "turnTime"), ("roll", "rollRate"),
                         ("climb", "climbSpeed"), ("wl", "wingLoading")):
            if isinstance(shop.get(src), (int, float)) and shop[src] > 0.05:
                out[key] = _r1(shop[src])
        if shop.get("thrustToWeightRatio"):
            out["tw"] = _r1(shop["thrustToWeightRatio"], 2)
        elif shop.get("powerToWeightRatio"):
            out["pw"] = _r1(shop["powerToWeightRatio"] * 1000)  # hp / t
    elif cat == "ground":
        fwd, rev = ground_speeds(udata)
        if fwd:
            out["spd"] = fwd
        if rev:
            out["rev"] = rev
        if st.get("hp"):
            out["hp"] = round(st["hp"])
        if st.get("mass"):
            out["t"] = _r1(st["mass"] / 1000)
            if st.get("hp"):
                out["pw"] = _r1(st["hp"] / (st["mass"] / 1000))
        for key, src in (("armT", "armorThicknessTurret"), ("armH", "armorThicknessHull")):
            if isinstance(shop.get(src), list) and shop[src]:
                out[key] = [round(x) for x in shop[src][:3]]
        ts = wp.get("turretSpeed")
        if isinstance(ts, list) and ts and isinstance(ts[0], (int, float)) and ts[0] > 0:
            out["trav"] = _r1(ts[0])
        main = next((g for g in ammo if g.get("trig") == "gunner0" or g.get("wi") == 1), ammo[0] if ammo else None)
        if main:
            cal = _caliber_mm(main.get("p", ""))
            if cal:
                out["cal"] = cal
            heat = max((o.get("s", {}).get("h") or 0 for o in main.get("opts", [])), default=0)
            if heat:
                out["heat"] = round(heat)
        if isinstance(wp.get("reloadTime_cannon"), (int, float)):
            out["rel"] = _r1(wp["reloadTime_cannon"])
    else:  # boats and ships
        if shop.get("maxSpeed"):
            out["spd"] = round(shop["maxSpeed"] * 3.6)
        if shop.get("displacement"):
            out["disp"] = round(shop["displacement"] / 1000)
        main = ammo[0] if ammo else None
        cal = _caliber_mm(main.get("p", "")) if main else None
        if cal:
            out["cal"] = cal
    if isinstance(wp.get("crewTotalCount"), (int, float)) and wp["crewTotalCount"] > 0:
        out["crew"] = int(wp["crewTotalCount"])
    return out


def base_stats(udata: dict, cat: str) -> dict:
    """Editable vehicle values with their stock value (used by the Modifications step)."""
    st = {}
    if cat == "ground":
        vp = udata.get("VehiclePhys") or {}
        eng, mass, mech = vp.get("engine") or {}, vp.get("Mass") or {}, vp.get("mechanics") or {}
        for key, src in (("hp", eng.get("horsePowers")), ("rpm", eng.get("maxRPM")), ("mass", mass.get("Empty")),
                         ("fuel", mass.get("Fuel")), ("brake", mech.get("maxBrakeForce")), ("gear", mech.get("mainGearRatio"))):
            val = _numval(src)
            if val is not None:
                st[key] = val
    elif cat in ("air", "heli"):
        fm_path = first_str(udata.get("fmFile"))
        if fm_path:
            st["fm"] = fm_path
            fm = load(DM / "aces.vromfs.bin_u" / "gamedata" / "flightmodels" / (fm_path.lower().replace(".blk", ".blkx"))) or {}
            mass = fm.get("Mass") or {}
            for key, src in (("mass", mass.get("EmptyMass")), ("fuel", mass.get("MaxFuelMass0"))):
                val = _numval(src)
                if val is not None:
                    st[key] = val
            main = ((fm.get("EngineType0") or {}).get("Main")) or {}
            if isinstance(main, dict):
                st["etype"] = first_str(main.get("Type"))
                for key, src in (("thrust", main.get("Thrust")), ("tboost", main.get("ThrottleBoost")), ("abboost", main.get("AfterburnerBoost"))):
                    val = _numval(src)
                    if val is not None:
                        st[key] = val
    return st


def preset_composition(preset: dict, fm: dict | None, wc: WeaponCache):
    """Returns [[weaponKey, count], ...] for a weapon preset."""
    blk = first_str(preset.get("blk"))
    pdata = load(blk_to_path(blk)) if blk else None
    counts: dict[str, int] = {}
    if not pdata:
        return []
    slots = {}
    if fm and isinstance(fm.get("WeaponSlots"), dict):
        for s in aslist(fm["WeaponSlots"].get("WeaponSlot")):
            if isinstance(s, dict):
                slots[s.get("index")] = {p.get("name"): p for p in aslist(s.get("WeaponPreset")) if isinstance(p, dict)}

    def add_weapon(w):
        blk = first_str(w.get("blk")) if isinstance(w, dict) else ""
        if not blk:
            return
        trig = first_str(w.get("trigger")).lower()
        if trig in ("countermeasures",) or w.get("dummy"):
            return
        n = num(w.get("bullets"), 1) or 1
        cont = wc.get(blk) if "container" in blk.lower() else None
        if isinstance(cont, dict) and cont.get("container") and first_str(cont.get("blk")):
            # pod / rack: count the munitions it carries
            blk = first_str(cont.get("blk"))
            n = num(cont.get("bullets"), 1) or 1
        k = wc.weapon_name(blk)
        if trig in ("machine gun", "cannon", "gunner0", "gunner1", "additional gun"):
            n = 1  # guns: count barrels not rounds
        counts[k] = counts.get(k, 0) + int(n)

    for w in aslist(pdata.get("Weapon")):
        if isinstance(w, dict) and "slot" in w and "preset" in w:
            sp = slots.get(w["slot"], {}).get(w["preset"])
            if sp:
                for sw in aslist(sp.get("Weapon")):
                    add_weapon(sw)
        else:
            add_weapon(w)
    return [[k, v] for k, v in counts.items()]


def vehicle_ammo(udata: dict, cat: str, official_mods: set, wc: WeaponCache):
    """Ammo groups: one per distinct gun able to take alternate ammo / belts."""
    groups = []
    seen = set()
    weapons = []
    slots = {}
    if isinstance(udata.get("WeaponSlots"), dict):
        for sl in aslist(udata["WeaponSlots"].get("WeaponSlot")):
            if isinstance(sl, dict):
                slots[sl.get("index")] = {p.get("name"): p for p in aslist(sl.get("WeaponPreset")) if isinstance(p, dict)}
    for wi, w in enumerate(aslist((udata.get("commonWeapons") or {}).get("Weapon")), start=1):
        if isinstance(w, dict) and "slot" in w and "preset" in w:
            # modern aircraft declare their guns through a weapon slot preset
            weapons += [(None, x) for x in aslist(slots.get(w["slot"], {}).get(w["preset"], {}).get("Weapon")) if isinstance(x, dict) and not x.get("dummy")]
        else:
            weapons.append((wi, w))
    for wi, w in weapons:
        blk = first_str(w.get("blk")) if isinstance(w, dict) else ""
        if not blk:
            continue
        key = blk.lower()
        if key in seen:
            # several barrels of the same gun share belts
            for g in groups:
                if g["blk"] == key:
                    g["n"] += 1
            continue
        seen.add(key)
        default, sets = wc.bullet_sets(blk)
        if not sets and not default:
            continue
        opts = []
        if default:
            opts.append({"id": "", **default})
        for mod, s in sets.items():
            if mod.endswith("_ammo_pack"):
                continue
            o = {"id": mod, **s}
            if mod not in official_mods:
                o["x"] = 1  # not normally available on this vehicle
            opts.append(o)
            wc.lang.put("mods", mod, f"modification/{mod}/short", f"modification/{mod}", f"{mod}/name/short")
        if len(opts) <= 1 and cat != "ground":
            continue
        g = {
            "blk": key,
            "p": blk,  # original path, used to build a custom weapon file
            "w": wc.weapon_name(blk),
            "trig": first_str(w.get("trigger")),
            "cap": num(w.get("bullets")),
            "n": 1,
            "opts": opts,
        }
        if wi:
            g["wi"] = wi  # 1-based index of this Weapon block in commonWeapons
            for key2, src in (("yaw", w.get("speedYaw")), ("pitch", w.get("speedPitch"))):
                val = _numval(src)
                if val is not None:
                    g[key2] = val
        sf = _numval((wc.get(blk) or {}).get("shotFreq"))
        if sf:
            g["sf"] = sf
        groups.append(g)
    if cat == "ground":
        # main gun first (gunner0 with the most ammo options)
        groups.sort(key=lambda g: (g["trig"] != "gunner0", -len(g["opts"])))
    for g in groups:
        del g["blk"]
    return groups[:4]


PREFIX_NATION = {"us": "usa", "germ": "germany", "ger": "germany", "ussr": "ussr", "uk": "britain", "jp": "japan",
                 "cn": "china", "it": "italy", "fr": "france", "sw": "sweden", "il": "israel"}


def guess_nation(vid: str) -> str:
    return PREFIX_NATION.get(vid.lower().split("_", 1)[0], "")


# vehicle roles for the "type" filter, from unittags (localized by the game: menu.csv mainmenu/type_<role>)
ROLES = ("light_tank", "medium_tank", "heavy_tank", "tank_destroyer", "spaa", "missile_tank",
         "fighter", "jet_fighter", "interceptor", "aa_fighter", "assault", "strike_aircraft", "bomber",
         "dive_bomber", "light_bomber", "frontline_bomber", "longrange_bomber", "jet_bomber", "torpedo",
         "naval_aircraft", "hydroplane", "strike_ucav", "attack_helicopter", "utility_helicopter",
         "boat", "torpedo_boat", "gun_boat", "torpedo_gun_boat", "heavy_boat", "heavy_gun_boat", "armored_boat",
         "submarine_chaser", "minelayer", "barge", "frigate", "destroyer", "light_cruiser", "heavy_cruiser",
         "battlecruiser", "battleship")
CLASS_ROLES = {"tank_destroyer": "tank_destroyer", "SPAA": "spaa", "fighter": "fighter", "assault": "assault",
               "bomber": "bomber", "torpedo_boat": "torpedo_boat", "gun_boat": "gun_boat",
               "torpedo_gun_boat": "torpedo_gun_boat", "submarine_chaser": "submarine_chaser", "destroyer": "destroyer"}


def vehicle_roles(tags: dict, unit_class: str, lang: "Lang") -> list:
    tg = (tags or {}).get("tags") or {}
    roles = [k[5:] for k, on in tg.items() if on is True and k.startswith("type_") and k[5:] in ROLES]
    if not roles and CLASS_ROLES.get(unit_class):
        roles = [CLASS_ROLES[unit_class]]
    for r in roles:
        lang.put("roles", r, f"mainmenu/type_{r}", fallback=humanize(r))
    return sorted(roles, key=ROLES.index)


def build_vehicles(lang: Lang, progress=None):
    log("Reading vehicle economy table (wpcost)...", progress)
    report(progress, 0.49)
    wp = load(DM / "char.vromfs.bin_u" / "config" / "wpcost.blkx") or {}
    unittags = load(DM / "char.vromfs.bin_u" / "config" / "unittags.blkx") or {}
    arsenal: dict = {}  # every weapon / ammo carried by a vehicle: category + icon / caliber / shell type
    wc = WeaponCache(lang)
    vehicles, details = [], {}

    entries = []
    for vid, v in wp.items():
        if not isinstance(v, dict) or "unitMoveType" not in v:
            continue
        cat = categorize(v.get("unitMoveType", ""), v.get("unitClass", ""))
        if cat == "other":
            continue
        entries.append((vid, cat, v, False))

    # Units that exist in the game files but are not in the shop (AI, event, removed, dev).
    known = {e[0].lower() for e in entries}
    base = DM / "aces.vromfs.bin_u" / "gamedata"
    for folder, cat in ((base / "units" / "tankmodels", "ground"), (base / "units" / "ships", "ship"), (base / "flightmodels", "air")):
        for f in folder.glob("*.blkx"):
            vid = f.stem
            if vid.lower() in known:
                continue
            if not (lang.get(f"{vid}_shop") or lang.get(f"{vid}_0")):
                continue  # unnamed = internal helper, skip
            entries.append((vid, cat, {}, True))

    for n in NUKES:
        wc.weapon_name(f"gameData/Weapons/bombGuns/{n}.blk")
    catalog = build_weapon_catalog(wc, progress)
    with open(DATA / "weapons.json", "w", encoding="utf-8") as fw:
        json.dump(catalog, fw, separators=(",", ":"))
    log(f"Processing {len(entries)} vehicles...", progress)
    for i, (vid, cat, v, hidden) in enumerate(entries):
        if i % 500 == 0 and i:
            log(f"  {i}/{len(entries)}", progress)
        if i % 40 == 0:
            report(progress, 0.56 + 0.30 * i / max(1, len(entries)))
        udata = load(unit_file(vid, cat))
        if udata is None:
            continue
        if hidden and cat == "air":
            t = str(udata.get("type", "")).lower()
            if "helicopter" in t:
                cat = "heli"
            if not udata.get("fmFile") and "helicopter" not in t:
                continue
        if hidden and cat == "ship":
            ec = str(udata.get("expClass", "") or udata.get("type", "")).lower()
            if "boat" in ec or "fast" in ec:
                cat = "boat"

        lang.put("units", vid, f"{vid}_shop", f"{vid}_0", fallback=humanize(vid))
        if f"{vid}_0" in lang.all:
            lang.put("unitsFull", vid, f"{vid}_0")

        country = (v.get("country") or "").replace("country_", "") or guess_nation(vid)
        rec = {
            "id": vid,
            "c": cat,
            "n": country or "other",
            "r": num(v.get("rank")),
            "br": [br_from(v.get("economicRankArcade")), br_from(v.get("economicRankHistorical")), br_from(v.get("economicRankSimulation"))],
            "k": (v.get("unitClass") or "").replace("exp_", ""),
        }
        if v.get("costGold"):
            rec["p"] = 1
        if hidden:
            rec["h"] = 1
        if not v.get("value") and not v.get("costGold") and not hidden:
            rec["g"] = 1  # gift / event / squadron etc.

        mods = set(aslist(v.get("modifications")) if isinstance(v.get("modifications"), list) else (v.get("modifications") or {}).keys())

        presets = []
        for p in aslist((udata.get("weapon_presets") or {}).get("preset")):
            if not isinstance(p, dict) or not p.get("name"):
                continue
            entry = {"id": p["name"], "w": preset_composition(p, udata if cat in ("air", "heli") else None, wc)}
            if cat in ("air", "heli"):
                pdata = load(blk_to_path(first_str(p.get("blk")))) or {}
                smap = {str(w["slot"]): w["preset"] for w in aslist(pdata.get("Weapon"))
                        if isinstance(w, dict) and "slot" in w and "preset" in w}
                if smap:
                    entry["s"] = smap
            if p.get("reqModification"):
                entry["req"] = p["reqModification"]
            presets.append(entry)

        details[vid] = {
            "b": UNIT_BLOCK[cat],
            "pr": presets,
            "am": vehicle_ammo(udata, cat, mods, wc),
            "st": base_stats(udata, cat),
        }
        if cat in ("air", "heli"):
            sl = weapon_slots(udata, wc)
            if sl:
                details[vid]["sl"] = sl
            em = pylon_emitters(udata)
            if em:
                details[vid]["em"] = em
            keys = {k for s in sl for o in s["o"] for k, _ in o["w"]} | {k for p in presets for k, _ in p["w"]}
            for s in sl:
                for o in s["o"]:
                    o["c"] = next(((catalog.get(k) or {}).get("c") for k, _ in o["w"] if catalog.get(k)), "")
            caps = aircraft_caps(udata, catalog, keys)
            if caps:
                details[vid]["cap"] = caps
        roles = vehicle_roles(unittags.get(vid) or {}, rec["k"], lang)
        if roles:
            rec["ro"] = roles
        stats = vehicle_stats(cat, udata, v, unittags.get(vid) or {}, details[vid]["st"], details[vid]["am"])
        if stats:
            rec["s"] = stats
            su = stock_stats(cat, stats, stock_factors(udata, mods))
            if su:
                rec["su"] = su  # stock values (rec["s"] = fully upgraded)
        # what it carries, for "search by weapon": guns, presets / pylon weapons, ammunition
        guns, carried, ammo_names = [], [], []
        for g in details[vid]["am"]:
            if g.get("w"):
                guns.append(g["w"])
                if g["w"] not in arsenal:
                    arsenal[g["w"]] = {"c": "gun", "cal": _caliber_mm(g.get("p", ""))}
            for o in g.get("opts", []):
                if o.get("x"):
                    continue
                for b in o.get("b", []):
                    ammo_names.append(b)
                    if b not in arsenal and o.get("t"):
                        arsenal[b] = {"c": "ammo", "t": o["t"][0]}
        carried += [k for p in presets for k, _ in p["w"]]
        carried += [k for sl_ in details[vid].get("sl", []) for o in sl_["o"] for k, _ in o["w"]]
        for key, lst in (("wg", guns), ("wp", carried), ("wa", ammo_names)):
            if lst:
                rec[key] = list(dict.fromkeys(lst))
        vehicles.append(rec)
    for key, entry in catalog.items():
        votes = ICON_VOTES.get(key)
        entry["ic"] = max(votes, key=votes.get) if votes else CATEGORY_ICONS.get(entry["c"], "bombs_middle")
    with open(DATA / "weapons.json", "w", encoding="utf-8") as fw:
        json.dump(catalog, fw, separators=(",", ":"))
    # pylon / preset weapons: category and game icon from the catalog (variants like "<key>_default" too)
    for v in vehicles:
        for k in v.get("wp", []):
            if k in arsenal:
                continue
            base = catalog.get(k) or catalog.get(re.sub(r"(_default|_\d+)$", "", k))
            votes = ICON_VOTES.get(k)
            arsenal[k] = {"c": (base or {}).get("c", "other"),
                          "ic": max(votes, key=votes.get) if votes else (base or {}).get("ic", "")}
    with open(DATA / "arsenal.json", "w", encoding="utf-8") as fw:
        json.dump(arsenal, fw, separators=(",", ":"))
    return vehicles, details


# --------------------------------------------------------------------------- air weapons catalog

CATALOG_FOLDERS = ("rocketguns", "bombguns", "torpedoes", "mines", "drop_tank", "equipment", "containers")
TRIGGERS = {"aam_ir": "aam", "aam_radar": "aam", "agm": "atgm", "atgm": "atgm", "rockets": "rockets",
            "bombs": "bombs", "guided_bombs": "guided bombs", "nuke": "bombs", "torpedoes": "torpedoes",
            "mines": "bombs", "fuel": "fuel tanks", "pods": "targetingPod"}
GUIDANCE = {"radar": "radar", "laser": "laser", "saclos": "saclos", "sns": "gps", "sonar": ""}


def _payload(d: dict):
    for k in ("rocket", "bomb", "torpedo", "mine"):
        if k in d:
            v = d[k]
            v = v[0] if isinstance(v, list) and v else v
            return k, v if isinstance(v, dict) else {}
    return None, {}


def classify_weapon(d: dict, folder: str):
    """-> (category, guidance) for an air-launched weapon file, or None to skip it."""
    if not isinstance(d, dict):
        return None
    if folder == "drop_tank":
        return "fuel", ""
    if folder == "equipment":
        return ("pods", "") if d.get("mesh") or d.get("payload") else None
    kind, p = _payload(d)
    bt = first_str(p.get("bulletType")).lower()
    gt = first_str(p.get("guidanceType")).lower()
    if folder == "torpedoes" or kind == "torpedo":
        return "torpedoes", ""
    if folder == "mines":
        return "mines", ""
    if bt in ("flare", "chaff") or not kind:
        return None
    if bt == "aam":
        return ("aam_radar", "radar") if gt == "radar" else ("aam_ir", "ir")
    if gt and gt != "none":
        g = GUIDANCE.get(gt, "tv" if gt == "optical" else gt)
        if kind == "bomb" or folder == "bombguns":
            return "guided_bombs", g
        return ("atgm", g) if bt.startswith("atgm") else ("agm", g)
    if kind == "bomb":
        return "bombs", ""
    if kind == "rocket":
        return "rockets", ""
    return None


def build_weapon_catalog(wc: "WeaponCache", progress=None) -> dict:
    """Every air-launched weapon of the game: {key: {"p": blk path, "c": category, "g": guidance, "t": trigger}}."""
    log("Building the air weapons catalog...", progress)
    report(progress, 0.50)
    base = DM / "aces.vromfs.bin_u" / "gamedata" / "weapons"
    out = {}
    for folder in CATALOG_FOLDERS:
        for f in sorted((base / folder).glob("*.blkx")):
            d = load(f)
            path = f"gameData/Weapons/{folder}/{f.stem}.blk"
            if folder == "containers":
                if not isinstance(d, dict) or not first_str(d.get("blk")):
                    continue
                inner = first_str(d["blk"])
                ifolder = inner.replace("\\", "/").split("/")[-2].lower()
                cl = classify_weapon(load(blk_to_path(inner)), ifolder)
                if not cl:
                    continue
                cat, g = cl
                entry = {"p": path, "c": cat, "g": g, "t": TRIGGERS.get(cat, "bombs"), "pod": num(d.get("bullets"), 1) or 1}
            else:
                cl = classify_weapon(d, folder)
                if not cl:
                    continue
                cat, g = cl
                if f.stem in NUKES:
                    cat = "nuke"
                entry = {"p": path, "c": cat, "g": g, "t": TRIGGERS.get(cat, "bombs")}
            key = wc.weapon_name(path)
            out[key] = entry
    log(f"  {len(out)} weapons", progress)
    return out


def aircraft_caps(udata: dict, catalog: dict, slot_keys: set) -> list:
    """Guidance systems this aircraft can use: from its official weapons + its own designators."""
    caps = set()
    for k in slot_keys:
        g = (catalog.get(k) or {}).get("g")
        if g:
            caps.add(g)
        if (catalog.get(k) or {}).get("c") == "pods":
            caps.add("laser")
    if udata.get("laserDesignator"):
        caps.add("laser")
    se = udata.get("sensors")
    for s in aslist(se.get("sensor")) if isinstance(se, dict) else []:
        b = first_str((s or {}).get("blk")).lower() if isinstance(s, dict) else ""
        if "laserdesignator" in b or "laserbeamriding" in b:
            caps.add("laser")
            if "beamriding" in b:
                caps.add("saclos")
    return sorted(caps)


# --------------------------------------------------------------------------- research trees

TREE_TYPES = {"army": "ground", "aviation": "air", "helicopters": "heli", "boats": "boat", "ships": "ship"}
TREE_FLAGS = {"gift": "gift", "event": "event", "isClanVehicle": "clan", "showOnlyWhenBought": "removed",
              "hideFeature": "hidden", "marketplaceItemdefId": "market"}


def build_trees(lang: Lang, known: set, progress=None):
    """In-game research trees: {nation: {category: [column: [item]]}}.

    item = {"id", "r"(rank), "f"[flags]} or a folder {"g"(group id), "r", "u": [items]}.
    Columns keep the game's order, so premium / event lines sit on the right like in game.
    """
    log("Reading research trees...", progress)
    report(progress, 0.94)
    shop = load(DM / "char.vromfs.bin_u" / "config" / "shop.blkx") or {}

    def unit(uid, v):
        it = {"id": uid, "r": num(v.get("rank"))}
        flags = [f for k, f in TREE_FLAGS.items() if v.get(k)]
        if flags:
            it["f"] = flags
        return it

    trees = {}
    for ckey, types in shop.items():
        if not isinstance(types, dict):
            continue
        nation = ckey.replace("country_", "")
        for tkey, tv in types.items():
            cat = TREE_TYPES.get(tkey)
            if not cat or not isinstance(tv, dict):
                continue
            columns = []
            for rng in aslist(tv.get("range")):
                if not isinstance(rng, dict):
                    continue
                col = []
                for k, v in rng.items():
                    if not isinstance(v, dict):
                        continue
                    if "rank" in v:
                        if k in known:
                            col.append(unit(k, v))
                    else:  # folder of several vehicles
                        members = [unit(kk, vv) for kk, vv in v.items() if isinstance(vv, dict) and "rank" in vv and kk in known]
                        if members:
                            lang.put("units", k, f"shop/group/{k}", fallback=" / ".join(m["id"] for m in members))
                            col.append({"g": k, "r": min(m["r"] for m in members), "u": members})
                if col:
                    columns.append(col)
            if columns:
                trees.setdefault(nation, {})[cat] = columns
    return trees


# --------------------------------------------------------------------------- hangar scenarios

HANGARS = (("hangar", "regular"), ("hangar_winter", "winter"), ("hangar_halloween", "halloween"),
           ("hangar_lunar_ny", "lunar_ny"), ("hangar_14_years", "anniversary"))
HANGAR_PLACES = {"ground": ("tank", "tank_premium"), "air": ("aircraft", "aircraft_premium"),
                 "heli": ("aircraft_premium", "aircraft"), "boat": ("hydroplane", "ship"), "ship": ("ship", "hydroplane")}


def _hangar_mission(level: str, block: str, pos: list, title: str) -> dict:
    from .mission import UNIT_DEFAULTS
    import copy as _copy
    x, y, z = (float(c) for c in pos)
    wing = "t1_player01"
    props = _copy.deepcopy(UNIT_DEFAULTS[block])
    unit = {"name": wing, "tm": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [x, y, z]], "unit_class": "",
            "objLayer": 1, "closed_waypoints": False, "isShipSpline": False, "shipTurnRadius": 100.0,
            "weapons": "", "bullets0": "", "bullets1": "", "bullets2": "", "bullets3": "",
            "bulletsCount0": 0, "bulletsCount1": 0, "bulletsCount2": 0, "bulletsCount3": 0,
            "crewSkillK": 0.0, "applyAllMods": True, "props": props, "way": {}}
    if block == "armada":
        props["speed"] = 0.0
    respawn = {
        "is_enabled": True, "comments": "respawn the player where they started",
        "props": {"actionsType": "PERFORM_ONE_BY_ONE", "conditionsType": "ALL", "enableAfterComplete": True},
        "events": {"periodicEvent": {"time": 1.0}},
        "conditions": {"playersWhenStatus": {"players": "isKilled", "check_players": "any"}},
        "actions": {"wait": {"time": 3.0}, "unitRespawn": {"delay": 1.0, "offset": [0.0, 0.0, 0.0], "object": wing, "target": "wtftd_spawn"}},
        "else_actions": {},
    }
    return {
        "selected_tag": "", "bin_dump_file": "",
        "mission_settings": {
            "player": {"army": 1, "wing": wing}, "player_teamB": {"army": 2},
            "mission": {"level": f"levels/{level}.bin", "type": "singleMission", "environment": "Day", "weather": "clear",
                        "locName": title, "restoreType": "attempts", "optionalTakeOff": False},
            "atmosphere": {"pressure": 760.0, "temperature": 15.0},
        },
        "imports": {}, "triggers": {"isCategory": True, "is_enabled": True, "wtftd_respawn": respawn},
        "mission_objectives": {"isCategory": True, "is_enabled": True},
        "variables": {}, "dialogs": {}, "airfields": {}, "effects": {},
        "units": {block: unit},
        "areas": {"wtftd_spawn": {"type": "Sphere", "tm": [[6.0, 0.0, 0.0], [0.0, 6.0, 0.0], [0.0, 0.0, 6.0], [x, y, z]],
                                  "objLayer": 0, "props": {}}},
        "objLayers": {}, "wayPoints": {},
    }


def build_hangar_scenarios(out_dir: Path) -> list:
    """Scenarios on the hangar maps (menu background), using the vehicle spots from config/hangar*.blk."""
    blocks = {"ground": "tankModels", "air": "armada", "heli": "armada", "boat": "ships", "ship": "ships"}
    out = []
    for cfg_name, variant in HANGARS:
        cfg = load(DM / "aces.vromfs.bin_u" / "config" / f"{cfg_name}.blkx")
        if not isinstance(cfg, dict) or not cfg.get("level"):
            continue
        level = first_str(cfg["level"]).replace("\\", "/").rsplit("/", 1)[-1].replace(".bin", "")
        places = {}
        for up in aslist(cfg.get("unitPos")):
            if isinstance(up, dict) and up.get("hangarPlace") and isinstance(up.get("modelPos"), list):
                places[up["hangarPlace"]] = up["modelPos"]
        for kind, wanted in HANGAR_PLACES.items():
            pos = next((places[p] for p in wanted if p in places), None)
            if not pos:
                continue
            sid = f"hangar_{variant}_{kind}"
            m = _hangar_mission(level, blocks[kind], pos, f"WTFTD Hangar ({variant})")
            with open(out_dir / f"{sid}.json", "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, separators=(",", ":"))
            out.append({"id": sid, "map": level, "kind": kind, "nation": "", "tags": ["hangar"], "start": "ground",
                        "block": blocks[kind], "wing": "t1_player01", "pos": [round(float(c), 1) for c in pos],
                        "units": 1, "type": "singleMission", "en": {}, "title": f"scenario.hangar.{variant}"})
    return out


# --------------------------------------------------------------------------- official test-drive scenarios

NATIONS = {"ussr": "ussr", "germ": "germany", "germany": "germany", "usa": "usa", "uk": "britain", "britain": "britain",
           "jp": "japan", "japan": "japan", "it": "italy", "italy": "italy", "china": "china", "fr": "france", "sw": "sweden"}
TAGS = ["jet", "navy", "hydroplane", "hydrobase", "heli", "ucav", "me", "in_air", "era", "destroyer", "universal"]


def scenario_kind(rel: str, level: str) -> str:
    n = rel.lower()
    if "/tank/" in n:
        return "ground"
    if "/ship/" in n:
        return "ship" if "destroyer" in n else "boat"
    if "ucav" in n:
        return "ucav"
    if "heli" in n:
        return "heli"
    return "air"


def _mission_path(game_path: str) -> Path:
    """'gameData/missions/x/y.blk' -> datamine .blkx path."""
    rel = game_path.replace("\\", "/").lower()
    if rel.startswith("gamedata/"):
        rel = rel[len("gamedata/"):]
    return DM / "mis.vromfs.bin_u" / "gamedata" / (rel[:-4] + ".blkx" if rel.endswith(".blk") else rel)


def imported_units(d: dict, depth: int = 0, seen: set | None = None) -> list:
    """Units defined in the game templates a mission imports (read-only for the editor)."""
    seen = seen if seen is not None else set()
    out = []
    if depth > 4 or not isinstance(d, dict):
        return out
    for rec in aslist((d.get("imports") or {}).get("import_record") if isinstance(d.get("imports"), dict) else None):
        if not isinstance(rec, dict) or rec.get("importUnits") is False:
            continue
        path = first_str(rec.get("file"))
        if not path or path.lower() in seen:
            continue
        seen.add(path.lower())
        sub = load(_mission_path(path))
        if not isinstance(sub, dict):
            continue
        for block, entries in (sub.get("units") or {}).items():
            if block == "squad":
                continue
            for u in aslist(entries):
                if not isinstance(u, dict) or not isinstance(u.get("tm"), list):
                    continue
                try:
                    x, y, z = (float(c) for c in u["tm"][3])
                    yaw = math.degrees(math.atan2(float(u["tm"][0][2]), float(u["tm"][0][0])))
                except (TypeError, ValueError, IndexError):
                    continue
                props = u.get("props") or {}
                out.append({"name": u.get("name"), "block": block, "cls": first_str(u.get("unit_class")),
                            "x": round(x, 1), "y": round(y, 1), "z": round(z, 1), "yaw": round(yaw, 1),
                            "army": props.get("army", 0) if isinstance(props, dict) else 0,
                            "count": props.get("count", 1) if isinstance(props, dict) else 1,
                            "attack": props.get("attack_type", "") if isinstance(props, dict) else ""})
        out += imported_units(sub, depth + 1, seen)
    return out


def build_levels(progress=None) -> dict:
    """Tactical maps per level: world x/z extents (a0/a1 = full map, t0/t1 = ground battle map) and
    the game textures holding them (am / tm), used as the scenario editor background."""
    out = {}
    for f in (DM / "aces.vromfs.bin_u" / "levels").glob("*.blkx"):
        d = load(f)
        if not isinstance(d, dict):
            continue
        e = {}
        for key, name in (("mapCoord0", "a0"), ("mapCoord1", "a1"), ("tankMapCoord0", "t0"), ("tankMapCoord1", "t1")):
            v = d.get(key)
            if isinstance(v, list) and len(v) == 2 and all(isinstance(c, (int, float)) for c in v):
                e[name] = [float(v[0]), float(v[1])]
        level = f.stem.lower()
        if "a0" in e:
            e["am"] = (first_str(d.get("customLevelMap")) or f"{level}_map*").split("*")[0].lower()
        if "t0" in e:
            e["tm"] = (first_str(d.get("customLevelTankMap")) or f"{level}_tankmap*").split("*")[0].lower()
        if e:
            out[f.stem.lower()] = e
    return out


def build_scenarios(lang: Lang, progress=None):
    log("Collecting official test drive / test flight missions...", progress)
    report(progress, 0.87)
    root = DM / "mis.vromfs.bin_u" / "gamedata" / "missions"
    src = root / "training" / "testflight"
    out_dir = DATA / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.json"):
        old.unlink()
    scenarios = []
    for f in sorted(src.rglob("*.blkx")):
        rel = f.relative_to(root).as_posix()
        if "template" in f.stem or "/human/" in rel or "sound_areas" in f.stem:
            continue
        d = load(f)
        if not isinstance(d, dict):
            continue
        ms = d.get("mission_settings") or {}
        mission = ms.get("mission") or {}
        wing = (ms.get("player") or {}).get("wing")
        level = (mission.get("level") or "").replace("\\", "/").rsplit("/", 1)[-1].replace(".bin", "")
        if not level or not isinstance(wing, str):
            continue
        player = None
        for block, units in (d.get("units") or {}).items():
            for u in aslist(units):
                if isinstance(u, dict) and u.get("name") == wing:
                    player = (block, u)
        if not player:
            continue
        block, u = player
        pos = tm_pos(u.get("tm"))
        kind = scenario_kind("/" + rel, level)
        stem = f.stem.lower()
        tokens = stem.replace("testflight_", "").replace("test_flight_", "").replace("_tft", "").replace("_tfs", "").split("_")
        nation = next((NATIONS[t] for t in tokens if t in NATIONS), "")
        tags = [t for t in TAGS if t in stem.split("_") or (t == "in_air" and "in_air" in stem)]
        if kind in ("air", "ucav", "heli"):
            speed = (u.get("props") or {}).get("speed")
            start = "air" if (pos and pos[1] > 600 and speed != 0.0) or "in_air" in stem else "ground"
        else:
            start = "ground"
        sid = stem
        lang.put("maps", level, f"location/{level}", f"missions/{level}", level,
                 fallback=humanize(re.sub(r"^(avg|avn|air|hvg|arcade)_", "", level)))
        with open(out_dir / f"{sid}.json", "w", encoding="utf-8") as fo:
            json.dump(d, fo, ensure_ascii=False, separators=(",", ":"))
        tpl = imported_units(d)
        if tpl:
            with open(out_dir / f"{sid}.units.json", "w", encoding="utf-8") as fo:
                json.dump(tpl, fo, ensure_ascii=False, separators=(",", ":"))
        scenarios.append({
            "id": sid,
            "map": level,
            "kind": kind,
            "nation": nation,
            "tags": tags,
            "start": start,
            "block": block,
            "wing": wing,
            "pos": [round(c, 1) for c in pos] if pos else None,
            "units": sum(len(aslist(v)) for v in (d.get("units") or {}).values()),
            # enemy units defined in the mission itself (those in game templates can't be swapped)
            "en": {blk: n for blk in ("tankModels", "armada", "ships")
                   if (n := sum(1 for x in aslist((d.get("units") or {}).get(blk))
                                if isinstance(x, dict) and (x.get("props") or {}).get("army") == 2))},
            "type": mission.get("type", ""),
        })
    scenarios += build_hangar_scenarios(out_dir)
    log(f"  {len(scenarios)} scenarios", progress)
    return scenarios


def tm_pos(tm):
    try:
        return [float(c) for c in tm[3]]
    except (TypeError, IndexError, ValueError):
        return None


# --------------------------------------------------------------------------- stock vs fully upgraded
# Vehicle files describe the fully upgraded vehicle: performance modules carry invertEnableLogic, i.e.
# their effects (power x0.9, traverse x0.85, mass x1.025...) apply while the module is NOT researched.
# Stock values = upgraded values with all those penalties. Exact for engine power / traverse; aircraft
# speed, climb and turn are estimated with simple physics (the game runs a flight model for those).

_GLOBAL_MODS: dict | None = None


def _global_mods() -> dict:
    global _GLOBAL_MODS
    if _GLOBAL_MODS is None:
        d = load(DM / "char.vromfs.bin_u" / "config" / "modifications.blkx") or {}
        _GLOBAL_MODS = d.get("modifications") if isinstance(d.get("modifications"), dict) else {}
    return _GLOBAL_MODS


def stock_factors(udata: dict, mod_names) -> dict:
    """Product of the penalty multipliers a stock vehicle carries (all 1.0 when nothing applies)."""
    f = {"P": 1.0, "M": 1.0, "D": 1.0, "Y": 1.0, "T": 1.0}
    local = udata.get("modifications") if isinstance(udata.get("modifications"), dict) else {}
    for name in mod_names:
        g = _global_mods().get(name)
        lo = local.get(name)
        g = g if isinstance(g, dict) else {}
        lo = lo if isinstance(lo, dict) else {}
        if not (lo.get("invertEnableLogic", g.get("invertEnableLogic"))):
            continue
        eff = lo.get("effects") if isinstance(lo.get("effects"), dict) else g.get("effects")
        if not isinstance(eff, dict):
            continue

        def mul(key):
            x = _numval(eff.get(key))
            return x if x and 0.2 < x < 5 else 1.0

        f["P"] *= mul("mulHorsePowers") * mul("thrustMult")
        f["M"] *= mul("mulMass")
        f["D"] *= mul("mulCdmin")
        f["Y"] *= mul("mulSpeedYaw")
        f["T"] *= mul("mulTransmissionEfficiency")
    return f


def stock_stats(cat: str, s: dict, f: dict) -> dict:
    """Stock value of each stat that modules change (only those that differ)."""
    out = {}
    P, M, D, Y = f["P"], f["M"], f["D"], f["Y"]

    def put(k, val, digits=1):
        if k in s and isinstance(s[k], (int, float)) and val is not None:
            v = round(val, digits) if digits else round(val)
            if abs(v - s[k]) > (10 ** -digits if digits else 0.5):
                out[k] = v

    if cat == "ground":
        put("hp", s.get("hp", 0) * P, 0)
        put("pw", s.get("pw", 0) * P / M)
        put("trav", s.get("trav", 0) * Y)
    elif cat in ("air", "heli"):
        jet = "tw" in s
        put("spd", s.get("spd", 0) * ((P / D) ** (0.5 if jet else 1 / 3)), 0)
        put("climb", s.get("climb", 0) * P / M)
        put("turn", s.get("turn", 0) * (M ** 0.5))
        put("tw", s.get("tw", 0) * P / M, 2)
        put("pw", s.get("pw", 0) * P / M)
        put("wl", s.get("wl", 0) * M, 0)
    return out


RARITY = {"tree": 0, "premium": 1, "squadron": 2, "pack": 3, "event": 4, "removed": 5, "hidden": 6}


def apply_rarity(vehicles: list, trees: dict):
    """ra = 0 tech tree, 1 premium (Golden Eagles), 2 squadron, 3 pack / gift, 4 event / marketplace,
    5 removed / no longer obtainable, 6 not playable (AI, unreleased)."""
    flags: dict = {}
    for nation in trees.values():
        for cols in nation.values():
            for col in cols:
                for it in col:
                    for u in (it.get("u") or [it]):
                        flags.setdefault(u["id"], set()).update(u.get("f") or [])
    for v in vehicles:
        fl = flags.get(v["id"], set())
        if v.get("h"):
            ra = 6
        elif "removed" in fl or "hidden" in fl:
            ra = 5
        elif "event" in fl or "market" in fl:
            ra = 4
        elif "gift" in fl and not v.get("p"):
            ra = 3
        elif "clan" in fl:
            ra = 2
        elif v.get("p") or "gift" in fl:
            ra = 1
        elif v["id"] not in flags:
            ra = 5  # not in any research tree: no longer obtainable
        else:
            ra = 0
        if ra:
            v["ra"] = ra


# --------------------------------------------------------------------------- main

def build(pull: bool = True, progress=None):
    t0 = time.time()
    if pull:
        fetch_datamine(progress)
    if not DM.exists():
        raise RuntimeError("Datamine not found. Run without --no-pull first.")
    DATA.mkdir(exist_ok=True)
    log("Loading game localization...", progress)
    report(progress, 0.46)
    lang = Lang()
    vehicles, details = build_vehicles(lang, progress)
    scenarios = build_scenarios(lang, progress)
    trees = build_trees(lang, {v["id"] for v in vehicles}, progress)
    apply_rarity(vehicles, trees)
    from .armament import build_armament
    build_armament(lang, vehicles, progress)
    log("Writing database...", progress)
    report(progress, 0.97)
    with open(DATA / "vehicles.json", "w", encoding="utf-8") as f:
        json.dump(vehicles, f, separators=(",", ":"))
    with open(DATA / "details.json", "w", encoding="utf-8") as f:
        json.dump(details, f, separators=(",", ":"))
    with open(DATA / "levels.json", "w", encoding="utf-8") as f:
        json.dump(build_levels(progress), f, separators=(",", ":"))
    with open(DATA / "trees.json", "w", encoding="utf-8") as f:
        json.dump(trees, f, separators=(",", ":"))
    with open(DATA / "scenarios.json", "w", encoding="utf-8") as f:
        json.dump(scenarios, f, separators=(",", ":"))
    codes = lang.write()
    version = (DM / "version").read_text().strip() if (DM / "version").exists() else "?"
    meta = {"version": version, "schema": SCHEMA, "built": int(time.time()), "vehicles": len(vehicles), "scenarios": len(scenarios), "langs": codes}
    with open(DATA / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    report(progress, 1.0)
    log(f"Done: {len(vehicles)} vehicles, {len(scenarios)} scenarios, game v{version} ({time.time() - t0:.0f}s)", progress)
    return meta


if __name__ == "__main__":
    build(pull="--no-pull" not in sys.argv)
