"""Ground height of a level, for placing units on the ground in the scenario editor.

Most ground-battle levels (levels/<name>.bin, "DBLD" format) store their terrain as a Dagor
"HM2" heightmap: a grid of 16-bit heights compressed in 8x8 blocks (min + delta + 8-bit
delta-coded variance per cell, see DagorEngine compressedHeightmap.cpp), Oodle-packed.
Older levels only have a land mesh ("lmap") and are not supported here.

The decoded grid is cached in .cache/maps/terrain/<level>.bin (uint16, little endian, row by
row along world z) with its metadata in <level>.json; the editor interpolates in it.
"""
from __future__ import annotations

import array
import ctypes
import json
import re
import struct
import sys
import threading
from itertools import accumulate
from pathlib import Path

from . import maptex
from .paths import CACHE as APP_CACHE

CACHE = APP_CACHE / "maps" / "terrain"
MAX_SIZE = 2048  # samples per side sent to the editor (full resolution on ground maps)
HMAP_CBLOCK_DELTAC_VER = 2
BTAG_OODLE = 2

_lock = threading.Lock()


class TerrainError(Exception):
    pass


def _chunks(path: Path) -> dict:
    """DBLD level file: {tag: (data offset, size)}."""
    out = {}
    with open(path, "rb") as f:
        if f.read(4) != b"DBLD":
            raise TerrainError("Not a level file")
        p = 0x0C
        while True:
            f.seek(p)
            h = f.read(8)
            if len(h) < 8:
                break
            size, tag = struct.unpack_from("<I", h)[0], h[4:8]
            out[tag] = (p + 8, size - 4)
            if size < 4 or tag == b"\0END":
                break
            p += 4 + size
    return out


def _unpack(src: bytes, raw_len: int, dll: str) -> bytes:
    dst = ctypes.create_string_buffer(raw_len)
    n = maptex._decompressor(dll)(src, len(src), dst, raw_len, 1, 0, 0, None, 0, None, None, None, 0, 3)
    if n != raw_len:
        raise TerrainError("Oodle could not decode the heightmap")
    return dst.raw


def _decode(data: bytes, dll: str) -> tuple[dict, array.array]:
    cell, hmin, hscale, ox, oz = struct.unpack_from("<5f", data, 0)
    width_version, height_mirrored = struct.unpack_from("<iI", data, 20)
    version, w, h = width_version >> 24, width_version & 0xFFFFFF, height_mirrored & 0x7FFFFFFF
    p = 44  # + 4 exclude-bounding ints
    if version != HMAP_CBLOCK_DELTAC_VER:
        raise TerrainError(f"Unsupported heightmap version {version}")
    chunk_sz = struct.unpack_from("<I", data, p)[0]
    p += 4
    bshift = chunk_sz & 0xFF
    hrb_sub = (1 << ((chunk_sz >> 8) & 0xF)) if chunk_sz & 0xF00 else 0
    bw, bh = w >> bshift, h >> bshift
    nblocks, bsize = bw * bh, 1 << (2 * bshift)
    hrb_levels = (w // hrb_sub).bit_length() - 1 if hrb_sub else 0
    hrb_bytes = ((4 ** hrb_levels - 1) // 3) * 16
    per_chunk = (chunk_sz & ~0xFFF) >> (2 * bshift)

    def block(pos: int):
        tag = struct.unpack_from("<I", data, pos)[0]
        size, fmt = tag & 0x3FFFFFFF, tag >> 30
        if fmt != BTAG_OODLE:
            raise TerrainError("Unsupported heightmap compression")
        return data[pos + 4:pos + 4 + size], pos + 4 + size

    if not per_chunk:  # one block: block infos + variance + height range blocks
        src, p = block(p)
        raw = _unpack(src, nblocks * 4 + nblocks * bsize + hrb_bytes, dll)
        infos, variance = raw[:nblocks * 4], raw[nblocks * 4:nblocks * 4 + nblocks * bsize]
    else:  # block infos first, then the variance by groups of blocks
        src, p = block(p)
        infos = _unpack(src, nblocks * 4 + hrb_bytes, dll)[:nblocks * 4]
        parts = []
        for b0 in range(0, nblocks, per_chunk):
            src, p = block(p)
            parts.append(_unpack(src, (min(nblocks, b0 + per_chunk) - b0) * bsize, dll))
        variance = b"".join(parts)

    # full-resolution grid, then keep every <step>th sample
    step = max(1, max(w, h) // MAX_SIZE)
    ow, oh = (w + step - 1) // step, (h + step - 1) // step
    out = array.array("H", bytes(2 * ow * oh))
    info = array.array("H", infos)
    if sys.byteorder != "little":
        info.byteswap()
    bw_px = 1 << bshift
    for by in range(bh):
        for bx in range(bw):
            bi = by * bw + bx
            mn, delta = info[2 * bi], info[2 * bi + 1]
            if delta:
                vals = [mn + ((a & 255) * delta + 127) // 255 for a in accumulate(variance[bi * bsize:(bi + 1) * bsize])]
            for j in range(bw_px):
                y = (by << bshift) + j
                if y % step:
                    continue
                row = (y // step) * ow
                for i in range(0, bw_px):
                    x = (bx << bshift) + i
                    if x % step:
                        continue
                    out[row + x // step] = vals[j * bw_px + i] if delta else mn
    meta = {"cell": cell * step, "hmin": hmin, "hscale": hscale, "ofs": [ox, oz], "w": ow, "h": oh,
            "max": [ox + w * cell, oz + h * cell]}
    return meta, out


def terrain(game_dir: Path | None, level: str, dll: str | None) -> dict | None:
    """Metadata of the cached ground grid of <level> (decoding it on first use), or None if the
    level has no heightmap."""
    if not re.fullmatch(r"[a-z0-9_]+", level or ""):
        raise TerrainError("Invalid level")
    meta_path = CACHE / f"{level}.json"
    with _lock:
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return meta if meta.get("w") else None
        if not game_dir:
            raise TerrainError("Game folder not found")
        path = game_dir / "levels" / f"{level}.bin"
        if not path.exists():
            raise TerrainError(f"Level {level} not found in the game files")
        chunks = _chunks(path)
        CACHE.mkdir(parents=True, exist_ok=True)
        if b"\0HM2" not in chunks:
            meta_path.write_text(json.dumps({"w": 0}), encoding="utf-8")  # remember: no heightmap
            return None
        if not dll:
            raise TerrainError("No Oodle runtime (oo2core_*_win64.dll / liboo2core*.dylib) found on this PC")
        ofs, size = chunks[b"\0HM2"]
        with open(path, "rb") as f:
            f.seek(ofs)
            data = f.read(size)
        meta, grid = _decode(data, dll)
        if sys.byteorder != "little":
            grid.byteswap()
        (CACHE / f"{level}.bin").write_bytes(grid.tobytes())
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        return meta


def grid_path(level: str) -> Path:
    return CACHE / f"{level}.bin"
