"""The game's 3D models, read from the player's own install for the viewer: the bytes go to the page, which decodes them
(web/model3d.js). Nothing is kept on disk and nothing is exported."""
import json
import re
import struct
import threading
from pathlib import Path

from . import builder, terrain, vromfs

DYNMODEL, SKELETON, RENDINST = 0xB4B7D9C4, 0x56F81B6D, 0x77F8232F
PAIRED = 0x20000  # a texture stored as the difference to another one
_NAME = re.compile(r"^[A-Za-z0-9_\-.]{1,120}$")
_cache: dict = {}
_locks = {kind: threading.Lock() for kind in ("models", "materials", "objects", "textures", "assets")}
_LEVEL = re.compile(r"^[a-z0-9_]{1,80}$")
_ASSETS = "gamedata/objectgroups/"
_MARKS = re.compile(r"^[^a-z0-9_]+")  # what starts a name in an asset: how the game places that object (%, #, >...)


def _pack(path: Path, found: dict):
    """Adds a pack's models, skeletons and placed objects to found: {(class, name): (path, offset, end)}."""
    with path.open("rb") as f:
        head = f.read(16)
        if len(head) < 16 or head[:4] != b"GRP2":
            return
        data = head + f.read(struct.unpack_from("<I", head, 4)[0] + 64)
    name_ofs = struct.unpack_from("<I", data, 16)[0]
    res_ofs, res_n = struct.unpack_from("<II", data, 32)
    table = sorted((struct.unpack_from("<IIH", data, res_ofs + 12 * i) for i in range(res_n)), key=lambda e: e[1])
    size = path.stat().st_size
    for i, (cid, ofs, rid) in enumerate(table):
        if cid in (DYNMODEL, SKELETON, RENDINST):
            at = struct.unpack_from("<i", data, name_ofs + 4 * rid)[0]
            name = data[at:data.index(b"\0", at)].decode("utf-8", "replace").lower()
            found.setdefault((cid, name), (path, ofs, table[i + 1][1] if i + 1 < len(table) else size))


def _once(kind: str, game: Path, build) -> dict:
    """A list of the install, kept while the app runs and built once: the page asks for several things at a time, and warm()
    may be at it already. One lock each, so that a model shows while the textures are still being listed."""
    with _locks[kind]:
        got = _cache.get(kind)
        if got is None or got[0] != game:
            got = _cache[kind] = (game, build(game))
    return got[1]


def _list_models(game: Path) -> dict:
    found: dict = {}
    for d in sorted(game.iterdir()):
        if d.is_dir() and d.name.startswith("content"):
            for p in d.rglob("*.grp"):
                try:
                    _pack(p, found)
                except (OSError, struct.error, ValueError, IndexError):
                    pass  # a pack the game is updating: its models are left out
    return found


def index(game: Path) -> dict:
    """Every model of the install, from the heads of its packs."""
    return _once("models", game, _list_models)


def _list(v) -> list:
    return v if isinstance(v, list) else [v]


def _material(m: dict, tex: list) -> dict:
    """A material's shader class, its texture names (t0 to t3) and the alpha cut of its `atest=N` parameter."""
    out = {"cls": m.get("cls", "")}
    for k in ("t0", "t1", "t2", "t3"):
        if isinstance(m.get(k), int) and 0 <= m[k] < len(tex):
            out[k] = tex[m[k]].rstrip("*")
    cut = re.search(r"atest\s*=\s*(\d+)", str(m.get("par", "")))
    if cut:
        out["atest"] = int(cut.group(1))
    return out


def _list_descriptions(game: Path, file: str, blocks: dict) -> dict:
    """{model: {key: [material]}} from every copy of a description file, a patched one first. blocks: {key: block of materials}."""
    found: dict = {}
    files = [game / "patch" / "content" / "base" / "res" / file, *sorted(game.glob(f"content*/*/res/{file}"))]
    for path in files if vromfs.available() else ():
        try:
            raw = path.read_bytes()
            size = int.from_bytes(raw[1:4], "little")
            root = vromfs.parse_blk(vromfs.zstd.decompress(raw[4:4 + size])[1:], [])
        except (OSError, struct.error, ValueError, IndexError, vromfs.zstd.ZstdError):
            continue
        for name, d in root.items():
            if isinstance(d, dict) and name.lower() not in found:
                tex = _list((d.get("tex") or {}).get("tex", []))
                found[name.lower()] = {k: [_material(m, tex) for m in _list((d.get(b) or {}).get("mat", []))] for k, b in blocks.items()}
    return found


def materials(game: Path) -> dict:
    """{model: {"R": [...], "S": [...]}}: the materials of its rigid and skinned parts (dynModelDesc.bin). Empty without
    compression.zstd (Python < 3.14)."""
    return _once("materials", game, lambda g: _list_descriptions(g, "dynModelDesc.bin", {"R": "matR", "S": "matS"}))


def object_materials(game: Path) -> dict:
    """The same for the objects a level places (riDesc.bin)."""
    return _once("objects", game, lambda g: _list_descriptions(g, "riDesc.bin", {"R": "mat"}))


def _dxp(path: Path, found: dict):
    """Adds the textures of a pack to found: {name: (path, offset, size, header)}."""
    with path.open("rb") as f:
        head = f.read(16)
        if len(head) < 16 or head[:4] != b"DxP2":
            return
        dump = f.read(struct.unpack_from("<I", head, 12)[0])
    names_at, count = struct.unpack_from("<II", dump, 0)
    headers_at = struct.unpack_from("<I", dump, 0x10)[0]
    records_at = struct.unpack_from("<I", dump, 0x20)[0]
    for i in range(count):
        header = dump[headers_at + i * 32:headers_at + i * 32 + 32]
        if not any(header[0x0C:0x10]):  # a name without a texture
            continue
        at = struct.unpack_from("<Q", dump, names_at + i * 8)[0]
        name = dump[at:dump.index(b"\0", at)].decode("utf-8", "replace").split("*")[0].lower()
        ofs, packed = struct.unpack_from("<II", dump, records_at + i * 24 + 0x0C)
        found[name] = (path, ofs, packed or struct.unpack_from("<I", header, 0x18)[0], header)


def _list_textures(game: Path) -> dict:
    found: dict = {}
    packs = (p for d in game.iterdir() if d.is_dir() and (d.name.startswith("content") or d.name == "patch") for p in d.rglob("*.dxp.bin"))
    for p in sorted(packs, key=lambda p: "patch" in p.parts):
        try:
            _dxp(p, found)
        except (OSError, struct.error, ValueError, IndexError):
            pass
    return found


def textures(game: Path) -> dict:
    """Every texture of the install, from the tables of its packs (patched packs win)."""
    return _once("textures", game, _list_textures)


def variants(game: Path, name: str) -> list:
    """The models of a weapon's positions: stowed, deployed, in its container."""
    stem = re.sub(r"_(deployed|container)$", "", name.lower())
    found = index(game)
    return [n for n in (stem, stem + "_deployed", stem + "_container") if (DYNMODEL, n) in found]


def level_info(level: str) -> dict:
    """What the 3D map needs from a level's settings."""
    settings = builder.load(builder.DM / "aces.vromfs.bin_u" / "levels" / f"{level}.blkx") if _LEVEL.match(level) else None
    water = (settings or {}).get("water_level")
    return {"water": water if isinstance(water, (int, float)) else None}


def _list_assets(game: Path) -> dict:
    if not vromfs.available():
        return {}
    aces = vromfs.Container(game / "aces.vromfs.bin")
    return {n.removeprefix(_ASSETS).removesuffix(".blk"): aces.blk(n) for n in aces.files if n.startswith(_ASSETS) and n.endswith(".blk")}


def _times(a: list, b: list) -> list:
    """Two of the game's matrices (three axes and a position), one in the other."""
    turn = lambda v: [sum(a[k][i] * v[k] for k in range(3)) for i in range(3)]
    return [turn(b[0]), turn(b[1]), turn(b[2]), [p + q for p, q in zip(turn(b[3]), a[3])]]


def asset(game: Path, name: str) -> list:
    """The objects an asset is made of, the groups it holds unfolded: [[object, its matrix as 12 numbers, by rows]].
    shortcut: placed objects only, a group's few dynamic models and its helpers are left out; the map's 3D view would have to read them."""
    groups, found, out = _once("assets", game, _list_assets), index(game), []

    def unfold(group, tm, depth):
        for node in _list(groups[group].get("node") or []):
            bare = _MARKS.sub("", str(node.get("name") or "").lower())
            try:
                here = _times(tm, node["tm"])
            except (KeyError, TypeError, IndexError):
                continue
            if bare in groups and bare != group and depth < 8:
                unfold(bare, here, depth + 1)
            elif (RENDINST, bare) in found:
                out.append([bare, [round(here[c][r], 4) for r in range(3) for c in range(4)]])

    if name.lower() in groups:
        unfold(name.lower(), [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]], 0)
    return out


def _level_block(game: Path, level: str, tag: bytes) -> bytes | None:
    path = game / "levels" / f"{level}.bin"
    if not _LEVEL.match(level) or not path.exists():
        return None
    ofs, size = terrain._chunks(path)[tag]
    with path.open("rb") as f:
        f.seek(ofs)
        return f.read(size)


def level_objects(game: Path, level: str) -> bytes | None:
    """A level's table of placed objects, as stored: the page unpacks it."""
    try:
        return _level_block(game, level, b"RIGz")
    except (OSError, KeyError, terrain.TerrainError):
        return None


def level_land(game: Path, level: str) -> bytes | None:
    """A level's landmesh block, as stored: the page reads the ground's weights from it."""
    try:
        return _level_block(game, level, b"lmap")
    except (OSError, KeyError, terrain.TerrainError):
        return None


def _dstring(d: bytes, p: int) -> tuple[str, int]:
    n = struct.unpack_from("<I", d, p)[0]
    return d[p + 4:p + 4 + n].decode("utf-8", "replace"), p + 4 + n + (4 - n % 4) % 4


def _land_head(d: bytes) -> dict:
    """The landmesh's grid, and where its ray tracer (the ground as a triangle mesh) is."""
    if d[:4] != b"lndm":
        raise ValueError("not a landmesh")
    grid, land, cw, ch, ox, oz, use = struct.unpack_from("<ffiiiiI", d, 8)
    detail, tile, tracer = struct.unpack_from("<iii", d, 40)
    p = 36 + tile
    if use:
        p = _dstring(d, p)[1] + 8
    block = None
    if tracer:
        block = (p + 4, struct.unpack_from("<I", d, p)[0])
        p = block[0] + (block[1] & 0x3FFFFFFF)
    vertical, p = _dstring(d, p)
    if vertical:
        p = _dstring(d, p + 24)[1] + 12
    if d[p:p + 4] == b"LTS4":
        block = (p + 8, struct.unpack_from("<I", d, p + 4)[0])
    return {"grid": grid, "land": land, "cells": [cw, ch], "origin": [ox, oz], "detail": 36 + detail, "tracer": block}


def level_ground(game: Path, level: str) -> dict | None:
    """What paints a level's ground: its grid and its land classes (colour map, the metres it spans, its offset)."""
    try:
        d = _level_block(game, level, b"lmap")
        if d is None:
            return None
        head = _land_head(d)
        p = head.pop("detail")
        head.pop("tracer")
        word = struct.unpack_from("<I", d, p)[0]
        classes = d[p + 4:p + 4 + (word & 0x3FFFFFFF)]
        p += 4 + (word & 0x3FFFFFFF)
        q, out = 4, []
        for _ in range(struct.unpack_from("<I", classes, 0)[0]):
            size = struct.unpack_from("<I", classes, q)[0] & 0x3FFFFFFF
            one = classes[q + 4:q + 4 + size]
            q += 4 + size
            rest = one[_dstring(one, 0)[1]:]
            b = vromfs.parse_blk(rest[1:], []) if rest and vromfs.available() else {}
            out.append({"texture": str(b.get("texture") or "").rstrip("*"), "size": b.get("size") or [1, 1], "offset": b.get("offset") or [0, 0]})
        w, h, tex, elem = struct.unpack_from("<iiii", d, p)
        return {**head, "classes": out, "weights": {"w": w, "h": h, "tex": tex, "elem": elem, "at": p + 16}}
    except (OSError, KeyError, ValueError, IndexError, struct.error, terrain.TerrainError):
        return None


def level_tracer(game: Path, level: str) -> bytes | None:
    """The ground of a level as a triangle mesh: the unpacked size and the packed stream, or 0 and the stream (zstd is unpacked here)."""
    try:
        d = _level_block(game, level, b"lmap")
        block = _land_head(d)["tracer"] if d else None
        if block is None:
            return None
        at, word = block
        packed = d[at:at + (word & 0x3FFFFFFF)]
        if word >> 30 == 2:
            return packed
        return struct.pack("<I", 0) + vromfs.zstd.decompress(packed) if vromfs.available() else None
    except (OSError, KeyError, ValueError, IndexError, struct.error, terrain.TerrainError):
        return None


def level_cells(game: Path, level: str, start: int, cells: list) -> bytes | None:
    """The cells of placed objects at these offsets from start, unpacked: each its size, then its bytes."""
    if not vromfs.available():
        return None
    try:
        data = _level_block(game, level, b"RIGz")
        out = []
        for ofs in cells:
            word = struct.unpack_from("<I", data, start + ofs)[0]
            packed = data[start + ofs + 4:start + ofs + 4 + (word & 0x3FFFFFFF)]
            raw = vromfs.zstd.decompress(packed) if packed else b""
            out += [struct.pack("<I", len(raw)), raw]
        return b"".join(out)
    except (OSError, KeyError, TypeError, struct.error, vromfs.zstd.ZstdError, terrain.TerrainError):
        return None


def warm(game: Path | None):
    """Lists it all when the app starts, in the background, so that the first 3D view has nothing to wait for."""
    try:
        if game:
            index(game)
            materials(game)
            object_materials(game)
            textures(game)
    except OSError:
        pass  # the next view tries again


def texture(game: Path, name: str, hq: bool = True) -> bytes | None:
    """A texture for the page: its 32-byte header, then its data as stored. The high-quality copy when there is one and it is
    wanted (a map's objects don't need it), unless it is stored as a difference to another texture."""
    found = textures(game)
    e = found.get(name.lower() + "$hq") if hq else None
    if e is None or struct.unpack_from("<I", e[3], 8)[0] & PAIRED:
        e = found.get(name.lower())
    if e is None:
        return None
    with e[0].open("rb") as f:
        f.seek(e[1])
        return e[3] + f.read(e[2])


def read(game: Path, name: str, placed: bool = False) -> bytes | None:
    """A model (placed: an object of a level), its skeleton and its materials for the page: their three sizes, then their bytes."""
    found = index(game)

    def take(key):
        e = found.get(key)
        if e is None:
            return b""
        with e[0].open("rb") as f:
            f.seek(e[1])
            return f.read(e[2] - e[1])

    name = name.lower()
    model = take((RENDINST if placed else DYNMODEL, name))
    if not model:
        return None
    tree = b"" if placed else take((SKELETON, name + "_skeleton"))
    mats = json.dumps((object_materials(game) if placed else materials(game)).get(name) or {}).encode()
    return struct.pack("<III", len(model), len(tree), len(mats)) + model + tree + mats


def vehicle_model(vid: str) -> str:
    """The model a vehicle's unit file names (variants share one)."""
    if _NAME.match(vid):
        for cat in ("ground", "air", "ship"):
            unit = builder.load(builder.unit_file(vid, cat))
            if unit:
                return str(unit.get("model") or "")
    return ""


