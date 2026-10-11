"""Custom tank sights (the game's UserSights).

The game reads user-made reticles from <Documents>/My Games/WarThunder/Saves/<player id>/production/UserSights:
a folder per vehicle (its unit id) or all_tanks, holding .blk sight files, picked in game under Options → Main
parameters → Ground vehicle battle settings → Sight settings → Reticle.

WTFTD lists the sights found there and the ones imported into its own library (user/sights). For a mission, it
copies the chosen sight to UserSights/<vehicle>/wtftd.blk for the vehicle the game loads (the custom vehicle's host,
and the vehicle itself): pick "wtftd" once in the game's sight settings for that vehicle, and every later mission
only changes that file's content. WTFTD never changes the game's settings files; every file it writes is listed in
user/sights_manifest.json and removed by cleanup().
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

SIGHT_FILE = "wtftd.blk"
_NAME = re.compile(r"^[A-Za-z0-9 _\-.()\[\]+]{1,100}\.blk$")
_FOLDER = re.compile(r"^[A-Za-z0-9_\-.]{1,120}$")
MAX_SIZE = 512 * 1024


class SightError(Exception):
    pass


def _saves_roots() -> list[Path]:
    home = Path.home()
    docs = [Path(os.environ[k]) / "Documents" for k in ("USERPROFILE", "OneDrive") if os.environ.get(k)]
    out = []
    for d in docs + [home / "Documents", home]:
        p = d / "My Games" / "WarThunder" / "Saves"
        if p.is_dir() and p not in out:
            out.append(p)
    return out


def production_dir() -> Path | None:
    """Saves/<player id>/production of the last player who logged in (Saves/last/lastUid), else the newest."""
    for root in _saves_roots():
        try:
            uid = (root / "last" / "lastUid").read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            uid = ""
        if uid.isdigit() and (root / uid / "production").is_dir():
            return root / uid / "production"
        ids = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit() and (p / "production").is_dir()]
        if ids:
            return max(ids, key=lambda p: p.stat().st_mtime) / "production"
    return None


def user_sights_dir() -> Path | None:
    prod = production_dir()
    return prod / "UserSights" if prod else None


def _manifest(user_dir: Path) -> Path:
    return user_dir / "sights_manifest.json"


def _read_manifest(user_dir: Path) -> list[str]:
    try:
        data = json.loads(_manifest(user_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in data if isinstance(p, str)]


def _write_manifest(user_dir: Path, paths: list[str]):
    user_dir.mkdir(parents=True, exist_ok=True)
    _manifest(user_dir).write_text(json.dumps(sorted(set(paths)), indent=1), encoding="utf-8")


def library_dir(user_dir: Path) -> Path:
    return user_dir / "sights"


def list_sights(user_dir: Path) -> dict:
    """{dir: UserSights folder or "", sights: [{id, name, folder}]}; id = "lib/<file>" | "game/<folder>/<file>"."""
    out = []
    lib = library_dir(user_dir)
    if lib.is_dir():
        for f in sorted(lib.glob("*.blk")):
            out.append({"id": f"lib/{f.name}", "name": f.stem, "folder": ""})
    us = user_sights_dir()
    if us and us.is_dir():
        for d in sorted(p for p in us.iterdir() if p.is_dir()):
            for f in sorted(d.glob("*.blk")):
                if f.name.lower() == SIGHT_FILE:
                    continue  # WTFTD's own copy
                out.append({"id": f"game/{d.name}/{f.name}", "name": f.stem, "folder": d.name})
    return {"dir": str(us) if us else "", "sights": out[:500]}


def _resolve(user_dir: Path, sid: str) -> Path:
    parts = str(sid or "").split("/")
    if len(parts) == 2 and parts[0] == "lib" and _NAME.match(parts[1]):
        path = library_dir(user_dir) / parts[1]
    elif len(parts) == 3 and parts[0] == "game" and _FOLDER.match(parts[1]) and _NAME.match(parts[2]):
        us = user_sights_dir()
        if not us:
            raise SightError("UserSights folder not found")
        path = us / parts[1] / parts[2]
    else:
        raise SightError("Invalid sight")
    if not path.is_file():
        raise SightError("Sight file not found")
    return path


def import_sight(user_dir: Path, name: str, text: str) -> str:
    """Saves a sight file (.blk text) into WTFTD's library; returns its id."""
    name = Path(str(name or "")).name
    if not name.lower().endswith(".blk"):
        name += ".blk"
    name = re.sub(r"[^A-Za-z0-9 _\-.()\[\]+]", "_", name)
    if not _NAME.match(name) or name.lower() == SIGHT_FILE:
        raise SightError("Invalid file name")
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > MAX_SIZE:
        raise SightError("Not a sight file")
    if "{" not in text:
        raise SightError("Not a sight file")
    lib = library_dir(user_dir)
    lib.mkdir(parents=True, exist_ok=True)
    (lib / name).write_text(text, encoding="utf-8")
    return f"lib/{name}"


def install(user_dir: Path, sid: str, vehicles: list[str]) -> list[str]:
    """Copies the sight to UserSights/<vehicle>/wtftd.blk for each vehicle; returns the folders written."""
    src = _resolve(user_dir, sid)
    us = user_sights_dir()
    if not us:
        raise SightError("UserSights folder not found: start War Thunder once with this account")
    text = src.read_bytes()
    if len(text) > MAX_SIZE:
        raise SightError("Sight file too large")
    manifest = _read_manifest(user_dir)
    done = []
    for vid in dict.fromkeys(v for v in vehicles if v):
        if not _FOLDER.match(vid):
            continue
        target = (us / vid / SIGHT_FILE)
        if us.resolve() not in target.resolve().parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text)
        manifest.append(f"{vid}/{SIGHT_FILE}")
        done.append(vid)
    _write_manifest(user_dir, manifest)
    return done


def cleanup(user_dir: Path) -> int:
    """Removes the sight copies WTFTD wrote (and their folders when left empty)."""
    us = user_sights_dir()
    removed = 0
    for rel in _read_manifest(user_dir):
        if not us:
            break
        target = us / rel
        try:
            if us.resolve() in target.resolve().parents and target.name == SIGHT_FILE and target.is_file():
                target.unlink()
                removed += 1
                try:
                    target.parent.rmdir()
                except OSError:
                    pass
        except OSError:
            pass
    try:
        _manifest(user_dir).unlink()
    except OSError:
        pass
    return removed
