"""Reads the game's own data: .vromfs.bin containers and the binary BLK files inside them.

Container: "VRFx", platform, unpacked size, packing (6 bits) + packed size (26 bits), 8-byte extended header
(its last 4 bytes: the game version, reversed), then the zstd payload with its first 16 and last 16 aligned bytes
XORed, then the MD5 of the unpacked payload and a signature. Unpacked, a directory of names and (offset, size) pairs.

BLK files start with their kind (BLK_*). Slim files share the names of the container's "nm" file, and those of
aces and mis are compressed with its zstd dictionary (<hash>.dict). Body: uleb128 counts of blocks, params and bytes
of param data, the param data, 8 bytes per param (name id: 24 bits, type: 8 bits, value or offset: 32 bits), then per
block its name id + 1, param count, child count and first child. Params follow the blocks' order.

unpack() writes the same .blkx (JSON) and .csv files as the community datamine, in the same folders, so the builder
reads either. compression.zstd comes with Python 3.14: without it the app starts as usual, only this source is off.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path

try:
    from compression import zstd
except ImportError:  # Python < 3.14
    zstd = None

NO_ZSTD = "Reading the game files needs Python 3.14 (compression.zstd): use the datamine, or a newer Python."
CONTAINERS = ("aces", "char", "lang", "mis")
PACKED = 0x30  # obfuscated zstd, with MD5
BLK_FAT, BLK_SLIM, BLK_SLIM_ZSTD, BLK_SLIM_DICT = 1, 3, 4, 5
XOR_HEAD = (0xAA55AA55, 0xF00FF00F, 0xAA55AA55, 0x12481248)
XOR_TAIL = XOR_HEAD[::-1]


class VromfsError(Exception):
    """A container that can't be read: the message is for the player."""


def available() -> bool:
    return zstd is not None


def _xor(buf: bytearray, at: int, key: tuple):
    words = struct.unpack_from("<4I", buf, at)
    struct.pack_into("<4I", buf, at, *(w ^ k for w, k in zip(words, key)))


def _header(raw: bytes, name: str) -> tuple[int, int, int, str]:
    """(payload offset, packed size, unpacked size, game version)."""
    if len(raw) < 16 or raw[:4] not in (b"VRFs", b"VRFx"):
        raise VromfsError(f"{name} is not a game data file: War Thunder may be updating, or need a repair in its launcher.")
    size, packed = struct.unpack_from("<II", raw, 8)
    if packed >> 26 != PACKED:
        raise VromfsError(f"{name} uses a packing WTFTD doesn't know ({packed >> 26:#x}): update WTFTD, or use the datamine in Settings.")
    if raw[:4] == b"VRFx":
        ext = struct.unpack_from("<H", raw, 16)[0]
        return 16 + ext, packed & 0x3FFFFFF, size, ".".join(str(b) for b in reversed(raw[20:24]))
    return 16, packed & 0x3FFFFFF, size, "?"


def version(game_dir: Path) -> str:
    """The game's version: the newest of its containers (a small patch leaves some of them as they were)."""
    out = []
    for name in CONTAINERS:
        try:
            with open(game_dir / f"{name}.vromfs.bin", "rb") as f:
                out.append(_header(f.read(32), name)[3])
        except OSError as e:
            raise VromfsError(f"Can't read {name}.vromfs.bin ({e.strerror}): is War Thunder updating? Retry once it is done.")
    return max(out, key=lambda v: [int(x) for x in v.split(".") if x.isdigit()])


def read_container(path: Path) -> dict[str, bytes]:
    """{file name: raw content} of a .vromfs.bin. The MD5 catches a file half written by an update."""
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise VromfsError(f"Can't read {path.name} ({e.strerror}): is War Thunder updating? Retry once it is done.")
    offset, packed, size, _ = _header(raw, path.name)
    if len(raw) < offset + packed + 16:
        raise VromfsError(f"{path.name} is incomplete: War Thunder may be updating, or need a repair in its launcher.")
    body = bytearray(raw[offset:offset + packed])
    if packed >= 16:
        _xor(body, 0, XOR_HEAD)
    if packed >= 32:
        _xor(body, (packed & 0x03FFFFFC) - 16, XOR_TAIL)
    try:
        data = zstd.decompress(bytes(body))
    except zstd.ZstdError as e:
        raise VromfsError(f"{path.name} is damaged ({e}): War Thunder may be updating, or need a repair in its launcher.")
    if len(data) != size or hashlib.md5(data).digest() != raw[offset + packed:offset + packed + 16]:
        raise VromfsError(f"{path.name} is damaged: War Thunder may be updating, or need a repair in its launcher.")
    names_at, count = struct.unpack_from("<II", data, 0)
    table_at = struct.unpack_from("<I", data, 16)[0]
    out = {}
    for i, at in enumerate(struct.unpack_from(f"<{count}Q", data, names_at)):
        name = data[at:data.index(0, at)]
        start, length = struct.unpack_from("<II", data, table_at + i * 16)
        out[name.removeprefix(b"\xff?").decode("utf-8")] = data[start:start + length]
    return out


def _uleb(b: bytes, p: int) -> tuple[int, int]:
    v = shift = 0
    while True:
        c = b[p]
        p += 1
        v |= (c & 0x7F) << shift
        if c < 0x80:
            return v, p
        shift += 7


def _names(b: bytes, p: int = 0) -> tuple[list[str], int]:
    count, p = _uleb(b, p)
    if not count:
        return [], p
    size, p = _uleb(b, p)
    return [s.decode("utf-8", "replace") for s in b[p:p + size].split(b"\0")[:count]], p + size


def _string(b: bytes, at: int) -> str:
    return b[at:b.index(0, at)].decode("utf-8", "replace")


def _float(x: float) -> float:
    """The shortest decimal of a 32-bit float, as the datamine shows it: 0.1, not 0.10000000149011612."""
    exact = struct.pack("<f", x)
    for digits in range(1 if abs(x) < 1.2e-38 else 6, 9):  # any 6 digits survive a 32-bit float, except denormals
        v = float(f"{x:.{digits}g}")
        if struct.pack("<f", v) == exact:
            return v
    return float(f"{x:.9g}")


def parse_blk(b: bytes, names: list[str]) -> dict:
    """A BLK body -> the datamine's JSON: a key seen twice in a block becomes a list."""
    own, p = _names(b)
    names = own or names
    n_blocks, p = _uleb(b, p)
    n_params, p = _uleb(b, p)
    size, p = _uleb(b, p)
    data, p = p, p + size
    params = []
    for key, value in struct.iter_unpack("<II", b[p:p + n_params * 8]):
        kind, name = key >> 24, names[key & 0xFFFFFF]
        if kind == 1:
            v = names[value & 0x7FFFFFFF] if value >> 31 else _string(b, data + value)
        elif kind == 2:
            v = value - (1 << 32) if value >> 31 else value
        elif kind == 3:
            v = _float(struct.unpack("<f", value.to_bytes(4, "little"))[0])
        elif kind == 4:
            v = [_float(x) for x in struct.unpack_from("<2f", b, data + value)]
        elif kind == 5:
            v = [_float(x) for x in struct.unpack_from("<3f", b, data + value)]
        elif kind == 6:
            v = [_float(x) for x in struct.unpack_from("<4f", b, data + value)]
        elif kind == 7:
            v = list(struct.unpack_from("<2i", b, data + value))
        elif kind == 8:
            v = list(struct.unpack_from("<3i", b, data + value))
        elif kind == 9:
            v = value != 0
        elif kind == 10:
            v = list(value.to_bytes(4, "little"))
        elif kind == 11:
            m = [_float(x) for x in struct.unpack_from("<12f", b, data + value)]
            v = [m[i:i + 3] for i in range(0, 12, 3)]
        elif kind == 12:
            v = struct.unpack_from("<q", b, data + value)[0]
        elif kind == 13:
            v = list(struct.unpack_from("<4i", b, data + value))
        else:
            raise VromfsError(f"BLK value of unknown type {kind}")
        params.append((name, v))
    p += n_params * 8
    blocks = []
    for _ in range(n_blocks):
        name, p = _uleb(b, p)
        count, p = _uleb(b, p)
        children, p = _uleb(b, p)
        first = 0
        if children:
            first, p = _uleb(b, p)
        blocks.append((name, count, children, first))
    # children come after their parent: built from the last block up. Params: in the blocks' order
    starts, at = [], 0
    for block in blocks:
        starts.append(at)
        at += block[1]
    done: list = [None] * n_blocks
    for i in range(n_blocks - 1, -1, -1):
        _, count, children, first = blocks[i]
        d: dict = {}
        for k, v in params[starts[i]:starts[i] + count]:
            d.setdefault(k, []).append(v)
        for c in range(first, first + children):
            d.setdefault(names[blocks[c][0] - 1], []).append(done[c])
        done[i] = {k: v[0] if len(v) == 1 else v for k, v in d.items()}
    return done[0] if done else {}


class Container:
    """The files of a .vromfs.bin, with what decoding its BLK files takes (shared names, zstd dictionary)."""

    def __init__(self, path: Path):
        self.files = read_container(path)
        self.names: list[str] = []
        self.options = None
        nm = self.files.get("nm")
        if nm:
            self.names = _names(zstd.decompress(nm[40:]))[0]
            d = self.files.get(nm[8:40].hex() + ".dict")
            self.options = zstd.ZstdDict(d) if d else None

    def blk(self, name: str) -> dict:
        b = self.files[name]
        kind = b[0]
        if kind == BLK_SLIM_DICT:
            return parse_blk(zstd.decompress(b[1:], zstd_dict=self.options), self.names)
        if kind == BLK_SLIM_ZSTD:
            return parse_blk(zstd.decompress(b[1:]), self.names)
        if kind in (BLK_FAT, BLK_SLIM):
            return parse_blk(b[1:], self.names)
        raise VromfsError(f"{name}: unknown BLK kind {kind}")


def unpack(game_dir: Path, target: Path, folders: list[str], progress=None):
    """Writes these folders of the containers ("aces.vromfs.bin_u/config", the datamine's paths) under target:
    BLK files as .blkx JSON, anything else as it is. progress(fraction) as it goes."""
    todo = []
    for name in CONTAINERS:
        wanted = tuple(f.split("/", 1)[1] + "/" for f in folders if f.startswith(f"{name}.vromfs.bin_u/"))
        c = Container(game_dir / f"{name}.vromfs.bin")  # all four read first: a damaged one stops before any writing
        todo += [(c, target / f"{name}.vromfs.bin_u", n) for n in c.files
                 if n.startswith(wanted) and ".." not in re.split(r"[\\/]", n)]  # never written outside target, whatever the file says
    made = set()
    for i, (c, root, name) in enumerate(todo):
        path = root / (name + "x" if name.endswith(".blk") else name)
        if path.parent not in made:
            path.parent.mkdir(parents=True, exist_ok=True)
            made.add(path.parent)
        if name.endswith(".blk"):
            try:
                text = json.dumps(c.blk(name), ensure_ascii=False, separators=(",", ":"))
            except (IndexError, ValueError, struct.error, zstd.ZstdError) as e:  # the file passed its MD5: a new format
                raise VromfsError(f"{name} can't be read ({e}): update WTFTD, or use the datamine in Settings.")
            path.write_text(text, encoding="utf-8")
        elif name.endswith(".csv"):  # the datamine's multi-line texts end their lines with \r\n, as the rest of the file
            path.write_bytes(re.sub(rb"(?<!\r)\n", b"\r\n", c.files[name]))
        else:
            path.write_bytes(c.files[name])
        if progress and not i % 200:
            progress(i / len(todo))
    (target / "version").write_text(version(game_dir), encoding="utf-8")
