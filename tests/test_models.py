"""The 3D viewer: finding a model in the game's packs, and the page's decoder."""
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wtftd import armament, models, vromfs

WEB = Path(__file__).resolve().parent.parent / "web"
OTHER = 0x12345678


def grp(entries):
    """A pack with the given (class, name, bytes): two tables of names and resources, then the data."""
    n = len(entries)
    names_at, res_at, strings_at = 64, 64 + 4 * n, 64 + 16 * n
    strings, spots = b"", []
    for _, name, _ in entries:
        spots.append(strings_at + len(strings))
        strings += name.encode() + b"\0"
    data_at = strings_at + len(strings)
    out = b"GRP2" + struct.pack("<III", data_at - 16, data_at - 16, 0)
    for at in (names_at, res_at, res_at):
        out += struct.pack("<IIQ", at, n, 0)
    out += b"".join(struct.pack("<i", at) for at in spots)
    ofs, blobs = data_at, b""
    for i, (cid, _, body) in enumerate(entries):
        out += struct.pack("<IIHH", cid, ofs, i, 0)
        ofs += len(body)
        blobs += body
    return out + strings + blobs


class Packs(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.game = Path(d.name)
        res = self.game / "content" / "base" / "res" / "tanks"
        res.mkdir(parents=True)
        (res / "ussr_t_72a.grp").write_bytes(grp([
            (models.SKELETON, "T_72a_skeleton", b"bones"), (OTHER, "t_72a_anim", b"xx"), (models.DYNMODEL, "t_72a", b"mesh!"),
            (models.DYNMODEL, "alone", b"z")]))
        (res / "broken.grp").write_bytes(b"GRP2\xff\xff")
        (self.game / "other").mkdir()
        (self.game / "other" / "not_read.grp").write_bytes(grp([(models.DYNMODEL, "hidden", b"no")]))
        models._cache.clear()
        self.addCleanup(models._cache.clear)

    def test_a_model_comes_with_its_skeleton(self):
        self.assertEqual(models.read(self.game, "T_72A"), struct.pack("<III", 5, 5, 2) + b"mesh!bones{}")

    def test_a_model_without_a_skeleton(self):
        self.assertEqual(models.read(self.game, "alone"), struct.pack("<III", 1, 0, 2) + b"z{}")

    def test_a_model_comes_with_the_classes_of_its_materials(self):
        found = {"t_72a": {"R": [{"cls": "aces_weapon_fire"}], "S": []}}
        with mock.patch.object(models, "materials", return_value=found):
            body = models.read(self.game, "t_72a")
        size = struct.unpack_from("<I", body, 8)[0]
        self.assertEqual(json.loads(body[-size:]), found["t_72a"])

    def test_what_is_not_a_model_is_not_served(self):
        self.assertIsNone(models.read(self.game, "t_72a_anim"))
        self.assertIsNone(models.read(self.game, "t_72a_skeleton"))
        self.assertIsNone(models.read(self.game, "../../secret"))

    def test_a_weapons_positions(self):
        (self.game / "content" / "base" / "res" / "tanks" / "m.grp").write_bytes(grp([
            (models.DYNMODEL, "rocket_deployed", b"a"), (models.DYNMODEL, "rocket", b"b"), (models.DYNMODEL, "rocket_container", b"c")]))
        models._cache.clear()
        self.assertEqual(models.variants(self.game, "rocket_deployed"), ["rocket", "rocket_deployed", "rocket_container"])
        self.assertEqual(models.variants(self.game, "alone"), ["alone"])
        self.assertEqual(models.variants(self.game, "nothing"), [])

    def test_a_placed_object_is_found_apart(self):
        (self.game / "content" / "base" / "res" / "tanks" / "m.grp").write_bytes(grp([(models.RENDINST, "house", b"walls")]))
        models._cache.clear()
        self.assertEqual(models.read(self.game, "house", True), struct.pack("<III", 5, 0, 2) + b"walls{}")
        self.assertIsNone(models.read(self.game, "house"))

    def test_a_level_name_is_never_a_path(self):
        for read in (models.level_objects, models.level_land, models.level_tracer, models.level_ground):
            self.assertIsNone(read(self.game, "../../settings"))
            self.assertIsNone(read(self.game, "nothing"))
        self.assertEqual(models.level_info("../x"), {"water": None})

    def test_only_the_game_content_folders_are_read(self):
        self.assertIsNone(models.read(self.game, "hidden"))

    def test_the_index_is_kept(self):
        models.index(self.game)
        with mock.patch.object(models, "_pack") as pack:
            models.index(self.game)
        pack.assert_not_called()

    def test_everything_is_listed_at_launch(self):
        models.warm(self.game)
        self.assertEqual(set(models._cache), {"models", "materials", "objects", "textures"})

    def test_no_game_nothing_to_list(self):
        models.warm(None)
        self.assertEqual(models._cache, {})


@unittest.skipUnless(vromfs.available(), "needs compression.zstd")
class Materials(unittest.TestCase):
    def test_the_patched_description_comes_first(self):
        models._cache.clear()
        self.addCleanup(models._cache.clear)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(vromfs, "parse_blk") as parse:
            game = Path(d)
            for rel in ("patch/content/base/res", "content/base/res"):
                (game / rel).mkdir(parents=True)
                packed = vromfs.zstd.compress(b"\x01body")
                (game / rel / "dynModelDesc.bin").write_bytes(b"\x02" + len(packed).to_bytes(3, "little") + packed)
            parse.side_effect = [{"Tank": {"matR": {"mat": {"cls": "new"}}, "matS": {"mat": [{"cls": "a"}, {"cls": "b"}]}}},
                                 {"tank": {"matR": {"mat": {"cls": "old"}}}, "plane": {"matR": {"mat": [{"cls": "c"}]}}, "bare": "x"}]
            found = models.materials(game)
        self.assertEqual(found, {"tank": {"R": [{"cls": "new"}], "S": [{"cls": "a"}, {"cls": "b"}]}, "plane": {"R": [{"cls": "c"}], "S": []}})
        self.assertEqual(parse.call_args_list[0].args[0], b"body")

    def test_a_material_names_its_textures_and_its_cut(self):
        m = models._material({"cls": "dynamic_tank_atest", "par": "atest=128", "t0": 1, "t2": 0, "t3": 9}, ["a_n*", "b_c*"])
        self.assertEqual(m, {"cls": "dynamic_tank_atest", "t0": "b_c", "t2": "a_n", "atest": 128})


def dxp(entries):
    """A pack with the given (name, width, bytes): its head, three tables, then the data."""
    n = len(entries)
    entries = [(*e, 0)[:4] for e in entries]
    names_at, headers_at, records_at, strings_at = 0x30, 0x30 + 8 * n, 0x30 + 40 * n, 0x30 + 64 * n
    strings, spots = b"", []
    for name, *_ in entries:
        spots.append(strings_at + len(strings))
        strings += name.encode() + b"\0"
    size = strings_at + len(strings)
    dump = b"".join(struct.pack("<IIQ", at, n, 0) for at in (names_at, headers_at, records_at))
    dump += b"".join(struct.pack("<Q", at) for at in spots)
    data, ofs = b"", 16 + size
    records = b""
    for _, width, body, flags in entries:
        dump += b"DDSx" + struct.pack("<4sIHH", b"DXT1", flags, width, width) + bytes(8) + struct.pack("<II", len(body), 0)
        records += bytes(12) + struct.pack("<II", ofs, 0) + bytes(4)
        ofs += len(body)
        data += body
    return b"DxP2" + struct.pack("<III", 2, n, size) + dump + records + strings + data


class Assets(unittest.TestCase):
    def setUp(self):
        self.game = Path(".")
        turned = [[0, 0, 1], [0, 1, 0], [-1, 0, 0], [10, 0, 0]]  # a quarter turn, 10 m along x
        groups = {"camp": {"node": [{"name": "%tent", "tm": turned}, {"name": "#position", "tm": turned}, {"name": "crate", "tm": turned}]},
                  "crate": {"node": {"name": ">box_a", "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 5]]}},
                  "tent": {"node": {"name": "%tent", "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]]}}}
        models._cache.clear()
        self.addCleanup(models._cache.clear)
        models._cache["assets"] = (self.game, groups)
        models._cache["models"] = (self.game, {(models.RENDINST, "tent"): None, (models.RENDINST, "box_a"): None})

    def test_a_group_is_unfolded_into_its_objects(self):
        got = dict(models.asset(self.game, "Camp"))
        self.assertEqual(set(got), {"tent", "box_a"})  # a helper is not an object; a group named after its object is no loop
        self.assertEqual(got["tent"], [0, 0, -1, 10, 0, 1, 0, 0, 1, 0, 0, 0])
        self.assertEqual(got["box_a"], [0, 0, -1, 5, 0, 1, 0, 0, 1, 0, 0, 0])  # its own place turned with the group's

    def test_an_unknown_asset_is_empty(self):
        self.assertEqual(models.asset(self.game, "../aces"), [])


class Land(unittest.TestCase):
    @staticmethod
    def landmesh(tracer=b"tree"):
        """A landmesh with no land classes: its head, a tile texture, a ray tracer block, no cliff texture, then its detail data."""
        tile = struct.pack("<I", 1) + b"t\0\0\0" + struct.pack("<ff", 1, 1)
        head = 36 + 16
        tracer_at = head + len(tile) + 4
        body = tile + struct.pack("<I", len(tracer) | 2 << 30) + tracer + struct.pack("<I", 0)
        detail = head + len(body)
        out = b"lndm" + struct.pack("<IffiiiiI", 4, 32.0, 4096.0, 2, 2, -1, -1, 1)
        out += struct.pack("<iiii", 0, detail - 36, head - 36, tracer_at - 36) + body
        classes = struct.pack("<I", 0)
        return out + struct.pack("<I", len(classes)) + classes + struct.pack("<iiii", 2, 2, 64, 64)

    def level(self, d):
        game = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, game)
        (game / "levels").mkdir()
        (game / "levels" / "m.bin").write_bytes(b"DBLD3x64" + bytes(4) + struct.pack("<I", len(d) + 4) + b"lmap" + d + struct.pack("<I", 4) + b"\0END")
        return game

    def test_a_landmesh_says_how_its_ground_is_painted(self):
        got = models.level_ground(self.level(self.landmesh()), "m")
        self.assertEqual((got["grid"], got["land"], got["cells"], got["origin"]), (32.0, 4096.0, [2, 2], [-1, -1]))
        self.assertEqual((got["weights"]["w"], got["weights"]["elem"], got["classes"]), (2, 64, []))

    def test_an_oodle_stream_goes_to_the_page_as_it_is(self):
        self.assertEqual(models.level_tracer(self.level(self.landmesh()), "m"), b"tree")


class Textures(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.game = Path(d.name)
        (self.game / "content" / "a").mkdir(parents=True)
        (self.game / "patch" / "content").mkdir(parents=True)
        (self.game / "content" / "a" / "tank.dxp.bin").write_bytes(dxp([
            ("Turret_c*", 8, b"low!"), ("turret_c$hq*", 16, b"high"), ("old_c*", 8, b"old!"), ("gone*?q1", 0, b""),
            ("wing_c*", 8, b"whole"), ("wing_c$hq*", 16, b"diff", models.PAIRED)]))
        (self.game / "patch" / "content" / "new.dxp.bin").write_bytes(dxp([("old_c*", 8, b"new!")]))
        models._cache.clear()
        self.addCleanup(models._cache.clear)

    def test_the_high_quality_copy_comes_first(self):
        self.assertEqual(models.texture(self.game, "turret_c")[32:], b"high")

    def test_a_copy_stored_as_a_difference_is_left_out(self):
        self.assertEqual(models.texture(self.game, "wing_c")[32:], b"whole")

    def test_a_texture_comes_with_its_header(self):
        body = models.texture(self.game, "TURRET_C")
        self.assertEqual(body[:4], b"DDSx")
        self.assertEqual(struct.unpack_from("<H", body, 12)[0], 16)

    def test_a_patched_pack_wins(self):
        self.assertEqual(models.texture(self.game, "old_c")[32:], b"new!")

    def test_a_name_without_a_texture(self):
        self.assertIsNone(models.texture(self.game, "gone"))
        self.assertIsNone(models.texture(self.game, "../../settings"))


class Names(unittest.TestCase):
    def test_a_vehicle_names_its_model(self):
        with mock.patch.object(models.builder, "load", side_effect=[None, {"model": "t_80u"}]):
            self.assertEqual(models.vehicle_model("ussr_t_80u_yt_cup_2019"), "t_80u")

    def test_a_vehicle_id_is_never_a_path(self):
        with mock.patch.object(models.builder, "load") as load:
            self.assertEqual(models.vehicle_model("../../settings"), "")
        load.assert_not_called()

    def test_a_weapon_names_its_mesh_or_what_it_fires(self):
        self.assertEqual(armament._mesh({"mesh": "launcher", "rocket": {"mesh": "missile"}}), "launcher")
        self.assertEqual(armament._mesh({"bullet": [{"caliber": 1}, {"rocket": {"mesh": "missile"}}]}), "missile")
        self.assertEqual(armament._mesh({"rocket": {"mass": 1}}), "")


# small synthetic streams, no game data: one good, one the format declares invalid
GOOD = "8c0c000038880036e6821d6c8deb04aa8000000103000002025b00001a80bbaee8dbb1ce33890409036ae8901c693e45e52df0d0026dde000003e9192780"
GOOD_SHA = "799697d56069dda9883463882e89c4e26aed86b656c371d7412e23d9cc2033c8"
BAD = "8c0c0000388000364790d71de13002c58000000103000002025b00001aeeef7e6decfb238edafb5ed1cf0bee037393f99ffaaf5f018620000003e9192780"
SCRIPT = """
const { lzDecode } = require(process.argv[1]);
const out = {};
for (const [k, hex, size] of JSON.parse(process.argv[2])) {
  try { out[k] = Buffer.from(lzDecode(new Uint8Array(Buffer.from(hex, 'hex')), size)).toString('hex'); }
  catch (e) { out[k] = null; }
}
console.log(JSON.stringify(out));
"""


GRID = """
const fs = require('fs'), vm = require('vm');
const stub = new Proxy(function () {}, { get: () => stub, apply: () => stub });
globalThis.$ = globalThis.$$ = globalThis.window = stub;
for (const f of process.argv.slice(1)) vm.runInThisContext(fs.readFileSync(f, 'utf8'));
const info = { origin: [0, 0], land: 64, cells: [1, 1], grid: 32 };
const pos = new Float32Array([0, 10, 0, 64, 10, 0, 64, 30, 64, 0, 30, 64]);
const T = vm.runInThisContext('m3Grid')({ pos, idx: new Uint32Array([0, 1, 2, 0, 2, 3]) }, info);
const empty = vm.runInThisContext('m3Grid')({ pos: pos.subarray(0, 0), idx: new Uint32Array(0) }, info);
const under = { ofs: [0, 0], cell: 32, w: 3, h: 3, hmin: 5, hscale: 0, grid: new Uint16Array(9) };
const holed = vm.runInThisContext('m3Grid')({ pos, idx: new Uint32Array([0, 1, 2]) }, info, under);
const height = (G, i, j) => G.hmin + G.grid[j * G.w + i] * G.hscale / 65535;
const inside = vm.runInThisContext('edInZone'), box = { type: 'Box', x: 100, z: 0, sx: 200, sz: 40, yaw: 90 }, round = { type: 'Cylinder', x: 0, z: 0, sx: 30, sz: 30, yaw: 0 };
const zones = [inside(box, 110, 95), inside(box, 110, 105), inside(box, 125, 0), inside(round, 21, 21), inside(round, 22, 22)];
const pos2 = [], idx2 = [], lathe = vm.runInThisContext('m3Lathe'), cube = lathe([[0, 1], [Math.SQRT2, 1, true], [Math.SQRT2, -1, true]], 4, Math.PI / 4, pos2, idx2);
const corners = pos2.slice(12).map(v => Math.round(v * 1000) / 1000);
console.log(JSON.stringify({ w: T.w, cell: T.cell, hmin: T.hmin, hscale: T.hscale, mid: height(T, 1, 1), empty, hole: height(holed, 0, 2), kept: height(holed, 2, 0), zones, cube, corners, top: idx2.length }));
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class Relief(unittest.TestCase):
    def test_triangles_become_a_grid_of_heights(self):
        files = [str(WEB / f) for f in ("lzdecode.js", "model3d.js", "map3d.js", "editor.js")]
        got = json.loads(subprocess.run(["node", "-e", GRID, *files], capture_output=True, text=True, check=True).stdout)
        self.assertEqual((got["w"], got["cell"], got["hmin"], got["hscale"]), (3, 32, 10, 20))
        self.assertAlmostEqual(got["mid"], 20, places=2)
        self.assertIsNone(got["empty"])  # a level whose relief is all in its heightmap
        self.assertAlmostEqual(got["hole"], 5, places=2)  # the hole over the heightmap has its heights
        self.assertAlmostEqual(got["kept"], 10, places=2)
        self.assertEqual(got["zones"], [True, False, False, True, False])  # a box's sizes are widths, turned by its heading
        self.assertEqual(got["corners"][:3], [1, 1, 1])
        self.assertEqual(max(map(abs, got["corners"])), 1)  # a box of four sides reaches its corners
        self.assertEqual((got["cube"]["faces"], got["cube"]["edges"]), (48, 24))


@unittest.skipUnless(shutil.which("node"), "needs node")
class Decoder(unittest.TestCase):
    def run_js(self, *streams):
        p = subprocess.run(["node", "-e", SCRIPT, str(WEB / "lzdecode.js"), json.dumps(streams)], capture_output=True, text=True, check=True)
        return json.loads(p.stdout)

    def test_a_compressed_stream(self):
        out = self.run_js(["good", GOOD, 140])["good"]
        self.assertEqual(hashlib.sha256(bytes.fromhex(out)).hexdigest(), GOOD_SHA)

    def test_a_stored_block(self):
        self.assertEqual(bytes.fromhex(self.run_js(["s", "4c0c61626364", 4])["s"]), b"abcd")

    def test_bad_streams_are_refused(self):
        got = self.run_js(["invalid", BAD, 140], ["cut", GOOD[:40], 140], ["other format", "4c0661626364", 4])
        self.assertEqual(got, {"invalid": None, "cut": None, "other format": None})
