"""Tactical map images straight from the game files, for the scenario editor background.

The maps are DDSx textures (DXT1 / DXT5) inside the game's texture packs
(content/base/res/*.dxp.bin, "DxP2" format), compressed with Oodle (Leviathan), read by
lzdecode. Decoded maps are cached as PNG in .cache/maps/tex/.
"""
from __future__ import annotations

import re
import struct
import threading
import zlib
from pathlib import Path

from . import lzdecode
from .paths import CACHE as APP_CACHE

CACHE = APP_CACHE / "maps" / "tex"
MAP_NAME = re.compile(r"_(tank|infantry)?map$")
FLG_REV_MIP_ORDER = 0x40000
FLG_COMPR_MASK = 0xE0000000
FLG_OODLE = 0x60000000
FLG_ZLIB = 0x80000000

_lock = threading.Lock()
_index: dict | None = None  # texture name -> (pack path, header bytes, data offset, data size)
_index_dir: str | None = None


class MapTexError(Exception):
    pass


# --------------------------------------------------------------------------- texture packs

def _read_pack(path: Path, out: dict):
    with open(path, "rb") as f:
        head = f.read(16)
        if len(head) < 16 or head[:4] != b"DxP2":
            return
        count, size = struct.unpack_from("<II", head, 8)
        b = head + f.read(size)
    base = 0x10
    names_ofs = struct.unpack_from("<I", b, 0x10)[0]
    hdr_ofs = struct.unpack_from("<I", b, 0x20)[0]
    rec_ofs = struct.unpack_from("<I", b, 0x30)[0]
    for i in range(count):
        p = struct.unpack_from("<Q", b, base + names_ofs + 8 * i)[0]
        end = b.index(b"\0", base + p)
        name = b[base + p:end].decode("utf-8", "ignore").split("*")[0].lower()
        if not MAP_NAME.search(name):
            continue
        hdr = b[base + hdr_ofs + 32 * i: base + hdr_ofs + 32 * i + 32]
        _, _, ofs, sz, _ = struct.unpack_from("<QiIII", b, base + rec_ofs + 24 * i)
        out[name] = (str(path), hdr, ofs, sz)


def texture_index(game_dir: Path) -> dict:
    global _index, _index_dir
    with _lock:
        if _index is None or _index_dir != str(game_dir):
            idx: dict = {}
            for pack in sorted((game_dir / "content").glob("**/*.dxp.bin")):
                try:
                    _read_pack(pack, idx)
                except (OSError, struct.error, ValueError):
                    continue
            _index, _index_dir = idx, str(game_dir)
        return _index


# --------------------------------------------------------------------------- DXT -> PNG

def _565(c: int):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def _decode_dxt(data: bytes, w: int, h: int, dxt5: bool) -> bytearray:
    """-> RGBA pixels."""
    out = bytearray(w * h * 4)
    bs = 16 if dxt5 else 8
    i = 0
    for by in range(0, h, 4):
        for bx in range(0, w, 4):
            alpha = None
            if dxt5:
                a0, a1 = data[i], data[i + 1]
                abits = int.from_bytes(data[i + 2:i + 8], "little")
                if a0 > a1:
                    apal = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
                else:
                    apal = [a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
                alpha = [apal[(abits >> (3 * k)) & 7] for k in range(16)]
            c0, c1, bits = struct.unpack_from("<HHI", data, i + bs - 8)
            i += bs
            a, b = _565(c0), _565(c1)
            if c0 > c1 or dxt5:
                pal = [a + (255,), b + (255,), tuple((2 * p + q) // 3 for p, q in zip(a, b)) + (255,),
                       tuple((p + 2 * q) // 3 for p, q in zip(a, b)) + (255,)]
            else:
                pal = [a + (255,), b + (255,), tuple((p + q) // 2 for p, q in zip(a, b)) + (255,), (0, 0, 0, 0)]
            for py in range(4):
                y = by + py
                if y >= h:
                    break
                for px in range(4):
                    x = bx + px
                    if x >= w:
                        continue
                    k = py * 4 + px
                    o = (y * w + x) * 4
                    px_ = pal[(bits >> (2 * k)) & 3]
                    out[o:o + 4] = bytes(px_) if alpha is None else bytes(px_[:3] + (alpha[k],))
    return out


def _png(w: int, h: int, rgba: bytearray) -> bytes:
    stride = w * 4
    rows = b"".join(b"\0" + bytes(rgba[y * stride:(y + 1) * stride]) for y in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


THUMBS = APP_CACHE / "maps" / "thumb"
THUMB_SIZE = 768  # longest side, about: the maps tab's cards and the map window


def thumbnail(png: Path, out: Path, size: int = THUMB_SIZE) -> bool:
    """A small copy of one of our own PNGs (_png: 8-bit RGBA, no row filters), every n-th row and pixel: the maps tab
    showed the 4096 px maps themselves (64 MB each once decoded). False when the PNG is not one of ours."""
    import array
    data = png.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    w, h, depth, colour = struct.unpack(">IIBB", data[16:26])
    if depth != 8 or colour != 6:
        return False
    idat, pos = [], 8
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IDAT":
            idat.append(data[pos + 8:pos + 8 + n])
        pos += 12 + n
    raw = zlib.decompress(b"".join(idat))
    stride = 1 + w * 4
    step = max(1, -(-max(w, h) // size))
    rows = []
    for y in range(0, h, step):
        if raw[y * stride] != 0:  # a row filter: not one of ours
            return False
        px = array.array("I", raw[y * stride + 1:(y + 1) * stride])[::step]
        rows.append(px.tobytes())
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part")
    tmp.write_bytes(_png(len(rows[0]) // 4, len(rows), bytearray(b"".join(rows))))
    tmp.replace(out)
    return True


def thumb_path(game_dir: Path | None, name: str) -> Path:
    """The small version of texture <name>'s PNG (made once, cached); the full PNG when it can't be made."""
    if not re.fullmatch(r"[a-z0-9_\-]+", name or ""):
        raise MapTexError("Invalid texture name")
    out = THUMBS / f"{name}.png"
    if out.exists():
        return out
    full = png_path(game_dir, name)
    with _lock:
        if out.exists() or thumbnail(full, out):
            return out
    return full


# --------------------------------------------------------------------------- public

def available(game_dir: Path | None, name: str) -> bool:
    if not game_dir or not name:
        return False
    if (CACHE / f"{name}.png").exists():
        return True
    return name in texture_index(game_dir)


def png_path(game_dir: Path | None, name: str) -> Path:
    """Decodes texture <name> (e.g. "berlin_map") to a cached PNG and returns its path."""
    if not re.fullmatch(r"[a-z0-9_\-]+", name or ""):
        raise MapTexError("Invalid texture name")
    out = CACHE / f"{name}.png"
    if out.exists():
        return out
    if not game_dir:
        raise MapTexError("Game folder not found")
    entry = texture_index(game_dir).get(name)
    if not entry:
        raise MapTexError(f"Texture {name} not found in the game files")
    pack, hdr, ofs, sz = entry
    fmt = hdr[4:8]
    flags, w, h = struct.unpack_from("<IHH", hdr, 8)
    levels = hdr[16]
    mem, packed = struct.unpack_from("<II", hdr, 24)
    if fmt not in (b"DXT1", b"DXT5"):
        raise MapTexError(f"Unsupported texture format {fmt!r}")
    with open(pack, "rb") as f:
        f.seek(ofs)
        src = f.read(sz)
    compr = flags & FLG_COMPR_MASK
    if compr == FLG_OODLE:
        try:
            raw = lzdecode.decode(src, mem)
        except lzdecode.LzError as e:
            raise MapTexError(f"Could not decode {name}: {e}")
    elif compr == FLG_ZLIB:
        raw = zlib.decompress(src)
    elif compr == 0:
        raw = src
    else:
        raise MapTexError(f"Unsupported compression for {name}")
    dxt5 = fmt == b"DXT5"
    top = max(1, w // 4) * max(1, h // 4) * (16 if dxt5 else 8)  # biggest mip
    data = raw[-top:] if levels > 1 and flags & FLG_REV_MIP_ORDER else raw[:top]
    png = _png(w, h, _decode_dxt(data, w, h, dxt5))
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_bytes(png)
    tmp.replace(out)
    return out
