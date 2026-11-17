"""The game's Oodle streams read in Python: map backgrounds and heightmaps need no Oodle runtime on the PC (issue #20)."""
import hashlib
import random
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_models import BAD, GOOD, GOOD_SHA
from wtftd import lzdecode, maptex, terrain


def dxp(name: str, width: int, mem: int, body: bytes) -> bytes:
    """A texture pack holding one Oodle-packed DXT1 texture: three tables, a name, then the data."""
    names_at, header_at, record_at, strings_at = 0x30, 0x38, 0x58, 0x70
    size = strings_at + len(name) + 1
    dump = b"".join(struct.pack("<IIQ", at, 1, 0) for at in (names_at, header_at, record_at)) + struct.pack("<Q", strings_at)
    dump += b"DDSx" + struct.pack("<4sIHH", b"DXT1", maptex.FLG_OODLE, width, width) + bytes(8) + struct.pack("<II", mem, len(body))
    dump += struct.pack("<QiIII", 0, 0, 16 + size, len(body), 0)
    return b"DxP2" + struct.pack("<III", 2, 1, size) + dump + name.encode() + b"\0" + body


class Decoder(unittest.TestCase):
    """The same streams as the page's decoder (test_models.Decoder), with the same answers."""

    def test_a_compressed_stream(self):
        self.assertEqual(hashlib.sha256(lzdecode.decode(bytes.fromhex(GOOD), 140)).hexdigest(), GOOD_SHA)

    def test_a_stored_block(self):
        self.assertEqual(lzdecode.decode(bytes.fromhex("4c0c61626364"), 4), b"abcd")

    def test_bad_streams_are_refused(self):
        for hexa, size in ((BAD, 140), (GOOD[:40], 140), ("4c0661626364", 4)):
            with self.subTest(hexa[:12]), self.assertRaises(lzdecode.LzError):
                lzdecode.decode(bytes.fromhex(hexa), size)

    def test_bytes_add_without_carries(self):
        rnd = random.Random(1)
        x, y = bytes(rnd.randrange(256) for _ in range(300)), bytes(rnd.randrange(256) for _ in range(300))
        self.assertEqual(lzdecode.add_bytes(x, y), bytes((a + b) & 255 for a, b in zip(x, y)))


class GameFiles(unittest.TestCase):
    def test_an_oodle_map_becomes_a_picture(self):
        with tempfile.TemporaryDirectory() as d:
            game = Path(d) / "game"
            (game / "content").mkdir(parents=True)
            (game / "content" / "maps.dxp.bin").write_bytes(dxp("test_map", 4, 140, bytes.fromhex(GOOD)))
            with mock.patch.object(maptex, "CACHE", Path(d) / "tex"):
                png = maptex.png_path(game, "test_map").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (4, 4))

    def test_a_heightmap_block(self):
        self.assertEqual(hashlib.sha256(terrain._unpack(bytes.fromhex(GOOD), 140)).hexdigest(), GOOD_SHA)
        with self.assertRaises(terrain.TerrainError):
            terrain._unpack(bytes.fromhex(BAD), 140)


if __name__ == "__main__":
    unittest.main()
