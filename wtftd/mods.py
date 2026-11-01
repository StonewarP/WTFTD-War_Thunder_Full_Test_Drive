"""Skins and sounds: the one page that writes into the game on purpose, and only when the player asks.

  <game>/UserSkins/<skin>/  skins: where the game exports its templates and reads them (the Saves folder has sights, not skins)
  <game>/sound/mod/         sound mods, which the game loads with enable_mod:b=yes in the sound block of <game>/config.blk

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
import zipfile
from pathlib import Path

from .paths import CACHE, USER

MANIFEST = USER / "mods_manifest.json"
BACKUP = USER / "config.blk.bak"
STAGING = CACHE / "mods_staging"  # what's being installed: it goes with the cache
SKINS, SOUNDS = "UserSkins", ("sound", "mod")
KINDS = ("skin", "sound")
ALLOWED = {"skin": {".blk", ".tga", ".dds", ".png", ".jpg", ".jpeg", ".txt"}, "sound": {".bank", ".txt"}}
JUNK = {"thumbs.db", "desktop.ini", ".ds_store"}  # what an archiver leaves: dropped, not refused
TEXTURES = (".tga", ".dds")
MAX_FILE = 2 << 30  # a sound mod's banks can be large: a skin's textures are about 64 MB each
MAX_TOTAL = 4 << 30
MAX_FILES = 3000
MAX_DEPTH = 6
MAX_NAME = 120
MAX_RATIO, RATIO_FROM = 300, 1 << 20  # real skins pack 6 times, solid colour 1000 times: what passes this has a size of its own to check
CHUNK = 1 << 20
TOKEN = re.compile(r"[a-z0-9]{6,40}")
BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
TEMP = ".wtftd_tmp"
REPLACE = re.compile(r'replace_tex\s*\{[^}]*?from\s*:\s*t\s*=\s*"([^"]+)"[^}]*?to\s*:\s*t\s*=\s*"([^"]+)"', re.S)
ENABLE = re.compile(rb"^[ \t]*enable_mod[ \t]*:[ \t]*b[ \t]*=[ \t]*(yes|no|true|false|1|0)[ \t]*(?:\r?\n|$)", re.M | re.I)
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
    if kind not in KINDS:
        raise ModsError("path", str(kind))
    root, parts = _staging(token), safe_path(rel)
    if _junk(parts):
        return
    suffix = Path(parts[-1]).suffix.lower()
    if suffix != ".zip" and suffix not in ALLOWED[kind] or suffix == ".zip" and len(parts) > 1:
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
    infos, total, seen = z.infolist(), 0, set()
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
        if i.file_size > RATIO_FROM and i.file_size > MAX_RATIO * max(i.compress_size, 1):
            raise ModsError("ratio", i.filename)
        key = "/".join(parts).lower()
        if key in seen:  # one would replace the other on Windows
            raise ModsError("path", i.filename)
        seen.add(key)
        kept.append((i, parts))
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
    if len(named) == 1:
        return {"vehicle": named[0], "sure": True, "candidates": named}
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


def inspect(token: str, kind: str, ids=()) -> dict:
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


def read_manifest() -> dict:
    try:
        raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    keep = lambda v: {k: x for k, x in v.items() if isinstance(x, dict) and isinstance(x.get("files"), list)} if isinstance(v, dict) else {}  # noqa: E731
    return {"skins": keep(raw.get("skins")), "sounds": keep(raw.get("sounds"))}


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
            shutil.copyfile(src, target)
    except OSError:
        for target in done:
            target.unlink(missing_ok=True)
        raise


def install(game: Path, token: str, kind: str, vehicles: dict | None = None, ids=(), running: bool = False) -> dict:
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
            data["skins"][name] = {"vehicle": wanted if wanted in set(ids) else guess["vehicle"], "files": [p.relative_to(d).as_posix() for p in inner]}
    else:
        if running:
            raise ModsError("running")
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
        data["sounds"][name] = {"files": sorted(paths.values())}
    _write_manifest(data)
    forget(token)
    return data


def _remove_files(root: Path, files: list) -> int:
    """Only the listed files, then the folders that leaves empty."""
    n = 0
    for rel in files:
        try:
            target = _inside(root, *safe_path(rel))
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
        _remove_files(game / SKINS / safe_path(name)[0], data["skins"].pop(name)["files"])
        try:
            (game / SKINS / name).rmdir()
        except OSError:
            pass
    elif kind == "sound" and name in data["sounds"]:
        if running:
            raise ModsError("running")
        _remove_files(game.joinpath(*SOUNDS), data["sounds"].pop(name)["files"])
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
        out.append({"name": d.name, "vehicle": (mine or {}).get("vehicle") or guess["vehicle"], "sure": bool(mine) or guess["sure"], "ours": bool(mine),
                    "files": len(files), "bytes": sum(p.stat().st_size for p in files), "replace": replaced})
    return out


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
    return {"skins": len(data["skins"]), "sounds": len(data["sounds"]), "config": BACKUP.exists()}


def remove_all(game: Path, running: bool) -> dict:
    """Uninstall: what WTFTD installed goes and config.blk gets its line back. The game running, the file is left for a later try,
    and so are the manifest and the copy that say so."""
    data = read_manifest()
    n = 0
    for name, m in data["skins"].items():
        n += _remove_files(game / SKINS / safe_path(name)[0], m["files"])
        try:
            (game / SKINS / name).rmdir()
        except OSError:
            pass
    if not running:
        for m in data["sounds"].values():
            n += _remove_files(game.joinpath(*SOUNDS), m["files"])
    kept = False
    if BACKUP.exists():
        try:
            set_sound(game, False, running)
        except (ModsError, OSError):
            kept = True
    if running or kept:
        _write_manifest({"skins": {}, "sounds": data["sounds"] if running else {}})
    else:
        MANIFEST.unlink(missing_ok=True)
    return {"files": n, "kept": kept or (running and bool(data["sounds"]))}
