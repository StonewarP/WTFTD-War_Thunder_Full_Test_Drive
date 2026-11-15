"""Skins and sounds: everything here works in a made-up game folder, with archives made on the spot."""
import base64
import io
import json
import os
import shutil
import stat
import struct
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from wtftd import blk, builder, imports, mission, mods, server, uninstall
from wtftd.paths import WEB

CONFIG = b'graphicsQuality:t="custom"\r\nlanguage:t="French"\r\n\r\nsound{\r\n  speakerMode:t="auto"\r\n  fmod_sound_enable:b=yes\r\n}\r\n\r\nyunetwork{\r\n  curCircuit:t="production"\r\n}\r\n'
IDS = ("rafale_c_f3", "fa_18e_block_2", "germ_pzkpfw_VI_ausf_h1_tiger", "f_16a", "f_16a_block_20")
BLK = b'name:t="user"\n\nreplace_tex{\n  from:t="rafale_c_f3_c*"\n  to:t="rafale_c_f3.tga"\n}\n'


def archive(path: Path, files: dict, method=zipfile.ZIP_DEFLATED) -> Path:
    with zipfile.ZipFile(path, "w", method) as z:
        for name, body in files.items():
            z.writestr(name, body)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.game = self.root / "War Thunder"
        (self.game / "UserSkins").mkdir(parents=True)
        (self.game / "sound").mkdir()
        (self.game / "config.blk").write_bytes(CONFIG)
        for name, value in (("MANIFEST", self.root / "user" / "mods_manifest.json"), ("BACKUP", self.root / "user" / "config.blk.bak"), ("STAGING", self.root / "staging")):
            p = mock.patch.object(mods, name, value)
            p.start()
            self.addCleanup(p.stop)

    def stage(self, files: dict, kind="skin", token="abcdef", name="pack.zip", **kw) -> dict:
        z = archive(self.root / name, files, **kw)
        with open(z, "rb") as f:
            mods.receive(token, name, f, z.stat().st_size, kind)
        return mods.inspect(token, kind, IDS)

    def refused(self, code: str, files: dict, kind="skin"):
        with self.assertRaises(mods.ModsError) as e:
            self.stage(files, kind)
        self.assertEqual(e.exception.code, code)
        self.assertEqual([p for p in (self.game / "UserSkins").iterdir()], [])
        mods.forget("abcdef")


class Names(unittest.TestCase):
    def test_what_stays_where_it_is_put(self):
        self.assertEqual(mods.safe_path("my skin/rafale_c_f3.tga"), ("my skin", "rafale_c_f3.tga"))
        self.assertEqual(mods.safe_path("a\\b.tga"), ("a", "b.tga"))
        self.assertEqual(mods.safe_path("été/ラファール.blk"), ("été", "ラファール.blk"))

    def test_what_could_go_elsewhere_is_refused(self):
        for name in ("../evil.tga", "a/../../evil.tga", "..\\evil.tga", "/etc/passwd", "\\\\server\\share\\x.tga", "C:\\Windows\\x.tga", "C:evil.tga",
                     "a//b.tga", "./a.tga", "con.tga", "a/NUL.blk", "lpt1.txt", "a.tga ", "a.tga.", "a:stream.tga", "a|b.tga", "bad\x00name.tga",
                     "x" * 300 + ".tga", "/".join("abcdefghij"), "", None, 5):
            with self.assertRaises(mods.ModsError, msg=name):
                mods.safe_path(name)


class Archives(Base):
    def test_a_skin_goes_in_and_is_listed(self):
        found = self.stage({"my_rafale/rafale_c_f3.blk": BLK, "my_rafale/rafale_c_f3.tga": b"x" * 100})
        self.assertEqual(found["skins"][0]["folder"], "my_rafale")
        self.assertEqual((found["skins"][0]["vehicle"], found["skins"][0]["sure"]), ("rafale_c_f3", True))
        mods.install(self.game, "abcdef", "skin", ids=IDS)
        self.assertTrue((self.game / "UserSkins" / "my_rafale" / "rafale_c_f3.tga").is_file())
        listed = mods.skins(self.game, IDS)[0]
        self.assertEqual((listed["name"], listed["vehicle"], listed["ours"], listed["files"]), ("my_rafale", "rafale_c_f3", True, 2))
        self.assertEqual(listed["replace"], [{"from": "rafale_c_f3_c", "to": "rafale_c_f3.tga"}])
        self.assertFalse(mods._staging("abcdef").exists())

    def test_traversal_is_refused_and_nothing_is_written(self):
        for name in ("../evil.tga", "a/../../evil.tga", "..\\..\\evil.tga", "/abs/evil.tga", "C:/evil.tga"):
            self.refused("path", {"good/ok.tga": b"1", name: b"2"})
        self.assertEqual(sorted(p.name for p in self.game.iterdir()), ["UserSkins", "config.blk", "sound"])

    def test_links_are_refused(self):
        z = self.root / "pack.zip"
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("good/ok.tga", b"1")
            link = zipfile.ZipInfo("good/link.tga")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            f.writestr(link, "../../config.blk")
        with open(z, "rb") as f:
            mods.receive("abcdef", "pack.zip", f, z.stat().st_size, "skin")
        with self.assertRaises(mods.ModsError) as e:
            mods.inspect("abcdef", "skin", IDS)
        self.assertEqual(e.exception.code, "link")

    def test_only_allowed_file_types(self):
        for name in ("run.exe", "a.bat", "a.cmd", "a.ps1", "a.dll", "a.js", "a.vbs", "a.py", "a.nut", "a.lnk", "a.scr", "a.html", "inner.zip", "a.tga.exe", "noextension"):
            self.refused("type", {"good/ok.tga": b"1", f"good/{name}": b"2"})
        self.refused("type", {"good/a.tga": b"1"}, "sound")  # each folder has its own list
        self.refused("type", {"a.bank": b"1"}, "skin")

    def test_junk_of_archivers_is_dropped(self):
        found = self.stage({"s/rafale_c_f3.blk": BLK, "s/Thumbs.db": b"x", "__MACOSX/s/._a": b"x", "s/.DS_Store": b"x"})
        self.assertEqual(found["skins"][0]["files"], 1)

    def test_too_many_files(self):
        with mock.patch.object(mods, "MAX_FILES", 3):
            self.refused("count", {f"s/{i}.tga": b"1" for i in range(5)})

    def test_total_size(self):
        with mock.patch.object(mods, "MAX_TOTAL", 150):
            self.refused("size", {"s/a.tga": b"1" * 100, "s/b.tga": b"2" * 100})

    def test_a_compression_ratio_past_the_limit(self):  # of the whole archive
        with mock.patch.object(mods, "RATIO_FROM", 1 << 20):
            self.refused("ratio", {"s/bomb.tga": b"\0" * (4 << 20)})
            self.stage({"s/rafale_c_f3.blk": BLK, "s/small.tga": b"\0" * 900_000})  # small archives can be empty paint

    def test_one_flat_texture_in_a_real_skin(self):  # the F-4 MECHA's normal detail packs 860 times
        real = os.urandom(3 << 20)
        with mock.patch.object(mods, "RATIO_FROM", 1 << 20):
            found = self.stage({"s/rafale_c_f3.blk": BLK, "s/rafale_c_f3.tga": real, "s/flat_n.dds": b"\x80" * (4 << 20)})
        self.assertEqual(found["skins"][0]["vehicle"], "rafale_c_f3")

    def test_a_real_skin_passes_the_ratio(self):
        real = bytes(range(256)) * 20_000 + os.urandom(1 << 20)
        self.assertEqual(self.stage({"s/rafale_c_f3.blk": BLK, "s/rafale_c_f3.tga": real})["skins"][0]["vehicle"], "rafale_c_f3")

    def test_two_entries_for_one_file(self):
        self.refused("path", {"s/A.tga": b"1", "s/a.tga": b"2"})

    def test_a_file_that_gives_more_than_it_says(self):
        z = self.root / "pack.zip"
        archive(z, {"s/a.tga": b"1" * 2000}, method=zipfile.ZIP_STORED)
        raw = bytearray(z.read_bytes())
        for head, at in ((b"PK\x03\x04", 22), (b"PK\x01\x02", 24)):  # the sizes both headers declare
            i = raw.index(head)
            raw[i + at:i + at + 4] = (10).to_bytes(4, "little")
        z.write_bytes(raw)
        with self.assertRaises(mods.ModsError):
            mods.unpack(z, self.root / "out", "skin")

    def test_an_encrypted_archive(self):
        z = self.root / "pack.zip"
        archive(z, {"s/a.tga": b"1"})
        raw = bytearray(z.read_bytes())
        raw[6] |= 1
        raw[raw.index(b"PK\x01\x02") + 8] |= 1
        z.write_bytes(raw)
        with self.assertRaises(mods.ModsError) as e:
            mods.unpack(z, self.root / "out", "skin")
        self.assertEqual(e.exception.code, "locked")

    def test_a_damaged_archive(self):
        (self.root / "bad.zip").write_bytes(b"not a zip at all")
        with self.assertRaises(mods.ModsError) as e:
            mods.unpack(self.root / "bad.zip", self.root / "out", "skin")
        self.assertEqual(e.exception.code, "zip")

    def test_an_archive_with_no_skin(self):
        with self.assertRaises(mods.ModsError) as e:
            self.stage({"readme.txt": b"hello"})
        self.assertEqual(e.exception.code, "noSkin")


class Uploads(Base):
    def test_a_picked_folder_goes_through_the_same_rules(self):
        for rel, body in (("my_skin/rafale_c_f3.blk", BLK), ("my_skin/rafale_c_f3.tga", b"12345")):
            mods.receive("abcdef", rel, io.BytesIO(body), len(body), "skin")
        self.assertEqual(mods.inspect("abcdef", "skin", IDS)["skins"][0]["folder"], "my_skin")
        for rel, code in (("../x.tga", "path"), ("my_skin/run.exe", "type"), ("my_skin/inner.zip", "type")):
            with self.assertRaises(mods.ModsError) as e:
                mods.receive("abcdef", rel, io.BytesIO(b"1"), 1, "skin")
            self.assertEqual(e.exception.code, code)

    def test_the_token_can_only_name_a_folder_of_the_staging(self):
        for token in ("../../evil", "a/b", "AB", "", None):
            with self.assertRaises(mods.ModsError):
                mods.receive(token, "a.tga", io.BytesIO(b"1"), 1, "skin")

    def test_limits_of_an_upload(self):
        with self.assertRaises(mods.ModsError):
            mods.receive("abcdef", "a.tga", io.BytesIO(b"1"), mods.MAX_FILE + 1, "skin")
        with mock.patch.object(mods, "MAX_TOTAL", 3):
            mods.receive("abcdef", "a.tga", io.BytesIO(b"12"), 2, "skin")
            with self.assertRaises(mods.ModsError):
                mods.receive("abcdef", "b.tga", io.BytesIO(b"12"), 2, "skin")

    def test_an_upload_cut_short_leaves_nothing(self):
        with self.assertRaises(mods.ModsError):
            mods.receive("abcdef", "s/a.tga", io.BytesIO(b"12"), 50, "skin")
        self.assertFalse((mods._staging("abcdef") / "s" / "a.tga").exists())

    def test_the_route_keeps_its_own_limit_and_the_origin_check(self):
        handler = mock.Mock(path="/api/mods/upload?token=abcdef&path=a.tga&kind=skin", headers={"Content-Length": "4"}, rfile=io.BytesIO(b"1234"))
        server.Handler.mods_upload(handler)
        self.assertEqual((mods._staging("abcdef") / "a.tga").read_bytes(), b"1234")
        self.assertEqual(handler.send_json.call_args.args[0], {"ok": True})
        handler = mock.Mock(path="/api/mods/upload?token=abcdef&path=run.exe&kind=skin", headers={"Content-Length": "4"}, rfile=io.BytesIO(b"1234"))
        server.Handler.mods_upload(handler)
        self.assertEqual((handler.send_json.call_args.args[0]["code"], handler.send_json.call_args.args[1]), ("type", 400))
        foreign = mock.Mock(path="/api/mods/upload?token=abcdef&path=b.tga&kind=skin", spec=server.Handler)
        foreign.local_origin = lambda: False
        server.Handler.do_POST(foreign)
        self.assertEqual(foreign.send_json.call_args.args[1], 403)
        self.assertFalse((mods._staging("abcdef") / "b.tga").exists())

    def test_other_routes_keep_the_2_mb_limit(self):
        handler = mock.Mock(headers={"Content-Length": str(3_000_000)})
        with self.assertRaises(ValueError):
            server.Handler.read_body(handler)


class RealRequests(Base):
    """Over a socket: a file object can't show a server waiting for bytes that never come."""

    def setUp(self):
        super().setUp()
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def post(self, path: str, body: bytes, origin: str | None = None):
        port = self.httpd.server_address[1]
        headers = {"Host": f"127.0.0.1:{port}", **({"Origin": origin} if origin else {})}
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/{path}", data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_a_refused_file_gets_an_answer_at_once(self):
        for body in (b"MZ", b"MZ" * 5000, b"M" * (3 << 20)):
            status, sent = self.post("mods/upload?token=abcdef&path=run.exe&kind=skin", body)
            self.assertEqual((status, sent["code"], sent["name"]), (400, "type", "run.exe"))

    def test_a_file_past_the_2_mb_of_other_routes_comes_in(self):
        status, sent = self.post("mods/upload?token=abcdef&path=a.tga&kind=skin", b"1" * (3 << 20))
        self.assertEqual((status, sent), (200, {"ok": True}))
        self.assertEqual((mods._staging("abcdef") / "a.tga").stat().st_size, 3 << 20)

    def test_another_site_is_refused(self):
        status, _ = self.post("mods/upload?token=abcdef&path=a.tga&kind=skin", b"1", origin="http://evil.example")
        self.assertEqual(status, 403)
        self.assertFalse((mods._staging("abcdef") / "a.tga").exists())


class Guess(unittest.TestCase):
    def test_a_blk_named_after_the_vehicle(self):
        g = mods.guess_vehicle("anything", ["germ_pzkpfw_vi_ausf_h1_tiger.blk", "a.tga"], [], IDS)
        self.assertEqual((g["vehicle"], g["sure"]), ("germ_pzkpfw_VI_ausf_h1_tiger", True))

    def test_the_folder_is_a_guess_the_longest_first(self):
        g = mods.guess_vehicle("f_16a_block_20_tiger_meet", ["paint.tga"], [], IDS)
        self.assertEqual((g["vehicle"], g["sure"], g["candidates"]), ("f_16a_block_20", False, ["f_16a_block_20", "f_16a"]))

    def test_a_template_folder(self):
        self.assertEqual(mods.guess_vehicle("template_rafale_c_f3", [], [], IDS)["vehicle"], "rafale_c_f3")

    def test_the_textures_it_replaces(self):
        g = mods.guess_vehicle("camo", ["custom.blk"], [{"from": "rafale_c_f3_c", "to": "a.tga"}], IDS)
        self.assertEqual((g["vehicle"], g["sure"]), ("rafale_c_f3", False))

    def test_nothing_to_go_by(self):
        self.assertEqual(mods.guess_vehicle("cool camo", ["a.tga"], [], IDS), {"vehicle": "", "sure": False, "candidates": []})

    def test_a_skin_for_several_vehicles(self):  # one .blk each, as the game reads it (the F-14 New Jersey's, the F-4 MECHA's)
        g = mods.guess_vehicle("pack", ["f_16a.blk", "f_16a_block_20.blk", "f_16a_c.tga"], [], IDS)
        self.assertEqual((g["sure"], g["vehicle"], g["vehicles"]), (True, "f_16a", ["f_16a", "f_16a_block_20"]))


class Ownership(Base):
    def test_the_players_answer_is_kept(self):
        self.stage({"cool/a.blk": b"", "cool/a.tga": b"1"})
        mods.install(self.game, "abcdef", "skin", vehicles={"cool": "rafale_c_f3"}, ids=IDS)
        self.assertEqual(mods.skins(self.game, IDS)[0]["vehicle"], "rafale_c_f3")

    def test_an_answer_must_be_a_vehicle(self):
        self.stage({"cool/a.blk": b"", "cool/a.tga": b"1"})
        mods.install(self.game, "abcdef", "skin", vehicles={"cool": "<img src=x>"}, ids=IDS)
        self.assertEqual(mods.skins(self.game, IDS)[0]["vehicle"], "")

    def test_a_skin_put_there_by_hand_is_shown_and_never_touched(self):
        hand = self.game / "UserSkins" / "template_rafale_c_f3"
        hand.mkdir()
        (hand / "rafale_c_f3.blk").write_bytes(BLK)
        (hand / "rafale_c_f3.tga").write_bytes(b"1")
        listed = mods.skins(self.game, IDS)[0]
        self.assertEqual((listed["ours"], listed["vehicle"]), (False, "rafale_c_f3"))
        with self.assertRaises(mods.ModsError) as e:
            mods.remove(self.game, "skin", "template_rafale_c_f3")
        self.assertEqual(e.exception.code, "notOurs")
        self.assertTrue((hand / "rafale_c_f3.tga").exists())

    def test_an_install_never_replaces_what_is_there(self):
        (self.game / "UserSkins" / "mine").mkdir()
        (self.game / "UserSkins" / "mine" / "own.tga").write_bytes(b"own")
        self.stage({"mine/rafale_c_f3.blk": BLK})
        with self.assertRaises(mods.ModsError) as e:
            mods.install(self.game, "abcdef", "skin", ids=IDS)
        self.assertEqual(e.exception.code, "exists")
        self.assertEqual([p.name for p in (self.game / "UserSkins" / "mine").iterdir()], ["own.tga"])

    def test_removing_takes_only_the_listed_files(self):
        self.stage({"s/rafale_c_f3.blk": BLK, "s/a.tga": b"1"})
        mods.install(self.game, "abcdef", "skin", ids=IDS)
        (self.game / "UserSkins" / "s" / "added_by_hand.tga").write_bytes(b"2")
        mods.remove(self.game, "skin", "s")
        self.assertEqual([p.name for p in (self.game / "UserSkins" / "s").iterdir()], ["added_by_hand.tga"])
        self.assertEqual(mods.read_manifest()["skins"], {})

    def test_a_manifest_edited_to_reach_outside_removes_nothing_outside(self):
        mods.MANIFEST.parent.mkdir()
        mods.MANIFEST.write_text(json.dumps({"skins": {"s": {"files": ["../../config.blk", "../x"]}}, "sounds": {"m": {"files": ["../../config.blk"]}}}))
        (self.game / "UserSkins" / "s").mkdir()
        mods.remove(self.game, "skin", "s")
        mods.remove(self.game, "sound", "m")
        self.assertEqual((self.game / "config.blk").read_bytes(), CONFIG)

    def test_a_damaged_manifest_owns_nothing(self):
        mods.MANIFEST.parent.mkdir()
        for text in ("{ broken", "[1]", '{"skins": 5}', '{"skins": {"a": 5}}'):
            mods.MANIFEST.write_text(text)
            self.assertEqual(mods.read_manifest(), {"skins": {}, "sounds": {}, "vehicles": {}})

    def test_nothing_is_written_outside_the_two_folders(self):
        before = {p for p in self.game.rglob("*")}
        self.stage({"s/rafale_c_f3.blk": BLK})
        mods.install(self.game, "abcdef", "skin", ids=IDS)
        self.stage({"mod/a.bank": b"1"}, "sound", token="ghijkl")
        mods.install(self.game, "ghijkl", "sound", running=False)
        new = {p for p in self.game.rglob("*")} - before
        allowed = (self.game / "UserSkins", self.game / "sound" / "mod")
        self.assertTrue(new and all(p == allowed[1] or any(a in p.parents for a in allowed) for p in new), new)
        self.assertEqual((self.game / "config.blk").read_bytes(), CONFIG)

    def test_the_texture_route_stays_in_the_skins(self):
        (self.game / "UserSkins" / "s").mkdir()
        (self.game / "UserSkins" / "s" / "a.tga").write_bytes(b"1")
        (self.game / "UserSkins" / "s" / "a.blk").write_bytes(b"1")
        self.assertEqual(mods.skin_file(self.game, "s", "a.tga").name, "a.tga")
        for folder, file in (("s", "a.blk"), ("..", "config.blk"), ("s", "../../config.blk"), ("s", "none.tga")):
            self.assertIsNone(mods.skin_file(self.game, folder, file))


class Sounds(Base):
    def install(self, files=None, token="abcdef"):
        self.stage(files or {"RCSM/mod/engine.bank": b"1", "RCSM/mod/engine.assets.bank": b"2", "RCSM/readme.txt": b"3"}, "sound", token=token, name="RCSM.zip")
        mods.install(self.game, token, "sound")

    def test_banks_land_in_sound_mod(self):
        self.install()
        self.assertEqual(sorted(p.name for p in (self.game / "sound" / "mod").iterdir() if p.is_file()), ["engine.assets.bank", "engine.bank"])
        self.assertEqual([(m["ours"], m["files"]) for m in mods.sounds(self.game)][0], (True, 3))

    def test_a_flat_archive(self):
        self.install({"a.bank": b"1"})
        self.assertTrue((self.game / "sound" / "mod" / "a.bank").is_file())

    def test_an_archive_with_no_bank(self):
        with self.assertRaises(mods.ModsError) as e:
            self.stage({"readme.txt": b"1"}, "sound")
        self.assertEqual(e.exception.code, "noBank")

    def test_a_file_put_there_by_hand_is_shown_and_never_touched(self):
        (self.game / "sound" / "mod").mkdir()
        (self.game / "sound" / "mod" / "hand.bank").write_bytes(b"own")
        self.install({"a.bank": b"1"})
        self.assertIn(("hand.bank", False), [(m["name"], m["ours"]) for m in mods.sounds(self.game)])
        with self.assertRaises(mods.ModsError):
            mods.remove(self.game, "sound", "hand.bank")
        ours = next(m["name"] for m in mods.sounds(self.game) if m["ours"])
        mods.remove(self.game, "sound", ours)
        self.assertEqual([p.name for p in (self.game / "sound" / "mod").iterdir()], ["hand.bank"])

    def test_a_file_already_there_is_never_replaced(self):
        (self.game / "sound" / "mod").mkdir()
        (self.game / "sound" / "mod" / "a.bank").write_bytes(b"own")
        with self.assertRaises(mods.ModsError) as e:
            self.install({"a.bank": b"new"})
        self.assertEqual(e.exception.code, "exists")
        self.assertEqual((self.game / "sound" / "mod" / "a.bank").read_bytes(), b"own")

    def test_in_with_the_game_running_out_only_closed(self):  # new banks: heard from its next start; open ones: not removed
        self.stage({"a.bank": b"1"}, "sound")
        mods.install(self.game, "abcdef", "sound", running=True)
        self.assertTrue((self.game / "sound" / "mod" / "a.bank").is_file())
        name, = mods.read_manifest()["sounds"]
        with self.assertRaises(mods.ModsError) as e:
            mods.remove(self.game, "sound", name, running=True)
        self.assertEqual(e.exception.code, "running")
        self.assertTrue((self.game / "sound" / "mod" / "a.bank").is_file())


class Config(Base):
    def blk(self) -> bytes:
        return (self.game / "config.blk").read_bytes()

    def test_off_by_default(self):
        self.assertEqual(mods.sound_state(self.game), {"on": False, "ours": False, "block": True})

    def test_on_adds_one_line_and_changes_no_other_byte(self):
        mods.set_sound(self.game, True, False)
        new = self.blk()
        self.assertEqual(new, CONFIG.replace(b"sound{\r\n", b"sound{\r\n  enable_mod:b=yes\r\n"))
        self.assertEqual(mods.BACKUP.read_bytes(), CONFIG)
        self.assertEqual(mods.sound_state(self.game), {"on": True, "ours": True, "block": True})

    def test_off_gives_the_file_back_byte_for_byte(self):
        mods.set_sound(self.game, True, False)
        mods.set_sound(self.game, False, False)
        self.assertEqual(self.blk(), CONFIG)
        self.assertFalse(mods.BACKUP.exists())

    def test_lines_ending_in_lf(self):
        lf = CONFIG.replace(b"\r\n", b"\n")
        (self.game / "config.blk").write_bytes(lf)
        mods.set_sound(self.game, True, False)
        self.assertEqual(self.blk(), lf.replace(b"sound{\n", b"sound{\n  enable_mod:b=yes\n"))
        mods.set_sound(self.game, False, False)
        self.assertEqual(self.blk(), lf)

    def test_a_players_own_no_comes_back_as_no(self):
        own = CONFIG.replace(b"sound{\r\n", b"sound{\r\n    enable_mod:b=no\r\n")
        (self.game / "config.blk").write_bytes(own)
        mods.set_sound(self.game, True, False)
        self.assertEqual(self.blk(), own.replace(b"enable_mod:b=no", b"enable_mod:b=yes"))
        mods.set_sound(self.game, False, False)
        self.assertEqual(self.blk(), own)

    def test_a_players_own_yes_is_left_alone(self):
        own = CONFIG.replace(b"sound{\r\n", b"sound{\r\n  enable_mod:b=yes\r\n")
        (self.game / "config.blk").write_bytes(own)
        self.assertEqual(mods.sound_state(self.game), {"on": True, "ours": False, "block": True})
        for on in (True, False):
            with self.assertRaises(mods.ModsError) as e:
                mods.set_sound(self.game, on, False)
            self.assertEqual(e.exception.code, "byHand")
        self.assertEqual(self.blk(), own)

    def test_what_the_game_saved_since_stays(self):
        mods.set_sound(self.game, True, False)
        (self.game / "config.blk").write_bytes(self.blk().replace(b'language:t="French"', b'language:t="English"'))
        mods.set_sound(self.game, False, False)
        self.assertEqual(self.blk(), CONFIG.replace(b'language:t="French"', b'language:t="English"'))

    def test_off_after_the_game_dropped_the_line(self):
        mods.set_sound(self.game, True, False)
        (self.game / "config.blk").write_bytes(CONFIG)
        mods.set_sound(self.game, False, False)
        self.assertEqual(self.blk(), CONFIG)
        self.assertFalse(mods.BACKUP.exists())

    def test_refused_while_the_game_runs_nothing_changes(self):
        for on in (True, False):
            with self.assertRaises(mods.ModsError) as e:
                mods.set_sound(self.game, on, True)
            self.assertEqual(e.exception.code, "running")
        self.assertEqual(self.blk(), CONFIG)
        self.assertFalse(mods.BACKUP.exists())

    def test_no_sound_block_is_refused(self):
        (self.game / "config.blk").write_bytes(b'language:t="French"\r\n')
        with self.assertRaises(mods.ModsError) as e:
            mods.set_sound(self.game, True, False)
        self.assertEqual(e.exception.code, "noBlock")
        self.assertEqual(self.blk(), b'language:t="French"\r\n')

    def test_only_the_sound_block_counts(self):
        other = b'mysound{\r\n  enable_mod:b=yes\r\n}\r\nsound{\r\n  deep{\r\n    enable_mod:b=yes\r\n  }\r\n}\r\nafter{\r\n  enable_mod:b=yes\r\n}\r\n'
        (self.game / "config.blk").write_bytes(other)
        self.assertTrue(mods.sound_state(self.game)["on"])  # nested in it: the regular expression stays inside the block
        plain = b'sound{\r\n  x:b=yes\r\n}\r\nafter{\r\n  enable_mod:b=yes\r\n}\r\n'
        (self.game / "config.blk").write_bytes(plain)
        self.assertFalse(mods.sound_state(self.game)["on"])
        mods.set_sound(self.game, True, False)
        self.assertEqual(self.blk(), plain.replace(b"sound{\r\n", b"sound{\r\n  enable_mod:b=yes\r\n"))

    def test_no_file_at_all(self):
        (self.game / "config.blk").unlink()
        self.assertEqual(mods.sound_state(self.game), {"on": False, "ours": False, "block": False})


class Remove(Base):
    def setUp(self):
        super().setUp()
        self.cache, self.data, self.user = self.root / ".cache", self.root / "data", self.root / "user"
        for d in (self.cache, self.data):
            d.mkdir()
        self.user.mkdir(exist_ok=True)
        for name, value in (("CACHE", self.cache), ("DATA", self.data), ("USER", self.user), ("HOME", self.root)):
            p = mock.patch.object(uninstall, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.stage({"s/rafale_c_f3.blk": BLK})
        mods.install(self.game, "abcdef", "skin", ids=IDS)
        self.stage({"a.bank": b"1"}, "sound", token="ghijkl")
        mods.install(self.game, "ghijkl", "sound")
        mods.set_sound(self.game, True, False)
        (self.game / "UserSkins" / "hand").mkdir()
        (self.game / "UserSkins" / "hand" / "hand.tga").write_bytes(b"own")

    def test_it_is_a_part_of_uninstall(self):
        self.assertIn("mods", uninstall.PARTS)
        self.assertEqual(uninstall.info(self.game)["mods"], {"skins": 1, "sounds": 1, "vehicles": 0, "config": True})

    def test_uninstall_takes_what_wtftd_installed_and_gives_the_file_back(self):
        res = uninstall.run(["mods"], self.game)
        self.assertEqual(res["removed"]["mods"]["kept"], False)
        self.assertEqual((self.game / "config.blk").read_bytes(), CONFIG)
        self.assertEqual([p.name for p in (self.game / "UserSkins").iterdir()], ["hand"])
        self.assertEqual(list((self.game / "sound" / "mod").iterdir()), [])
        self.assertFalse(mods.MANIFEST.exists() or mods.BACKUP.exists())

    def test_the_game_running_keeps_what_it_takes_to_finish_later(self):
        res = uninstall.run(["mods"], self.game, running=True)
        self.assertTrue(res["removed"]["mods"]["kept"])
        self.assertIn(b"enable_mod", (self.game / "config.blk").read_bytes())
        self.assertTrue(mods.BACKUP.exists() and mods.MANIFEST.exists())
        uninstall.run(["mods"], self.game)
        self.assertEqual((self.game / "config.blk").read_bytes(), CONFIG)

    def test_the_user_part_alone_keeps_the_manifest_and_the_copy(self):
        uninstall.run(["user"], self.game)
        self.assertTrue(mods.BACKUP.exists() and mods.MANIFEST.exists())
        uninstall.run(["mods", "user"], self.game)
        self.assertFalse(mods.BACKUP.exists() or mods.MANIFEST.exists())
        self.assertEqual((self.game / "config.blk").read_bytes(), CONFIG)


DECODE = """
const fs = require('fs'), vm = require('vm');
const stub = new Proxy(function () {}, { get: () => stub, apply: () => stub });
globalThis.$ = globalThis.$$ = globalThis.window = stub;
globalThis.document = undefined;
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const tga = vm.runInThisContext('mdTga'), dds = vm.runInThisContext('mdDds');
const head = (type, w, h, bits, desc) => { const b = new Uint8Array(18); b[2] = type; b[12] = w; b[14] = h; b[16] = bits; b[17] = desc; return b; };
const join = (...p) => { const n = p.reduce((a, x) => a + x.length, 0), o = new Uint8Array(n); let at = 0; for (const x of p) { o.set(x, at); at += x.length; } return o; };
const list = x => (x ? [...x.rgba] : null);
const blue = [255, 0, 0, 255], red = [0, 0, 255, 128];  // BGRA
const ddsHead = (w, h, fourcc, bits, flags) => { const b = new Uint8Array(128), v = new DataView(b.buffer); b.set([68, 68, 83, 32]); v.setUint32(12, h, true); v.setUint32(16, w, true); v.setUint32(80, flags, true); b.set(fourcc, 84); v.setUint32(88, bits, true); v.setUint32(92, 0xff0000, true); v.setUint32(96, 0xff00, true); v.setUint32(100, 0xff, true); v.setUint32(104, 0xff000000, true); return b; };
const dxt = dds(join(ddsHead(4, 4, [68, 88, 84, 49], 0, 4), new Uint8Array(8)));
console.log(JSON.stringify({
  bottomUp: list(tga(join(head(2, 1, 2, 32, 8), new Uint8Array(blue), new Uint8Array(red)))),
  topDown: list(tga(join(head(2, 1, 2, 32, 40), new Uint8Array(blue), new Uint8Array(red)))),
  bits24: list(tga(join(head(2, 1, 1, 24, 32), new Uint8Array([1, 2, 3])))),
  rle: list(tga(join(head(10, 2, 1, 32, 32), new Uint8Array([129, ...blue])))),
  raw: list(tga(join(head(10, 2, 1, 32, 32), new Uint8Array([1, ...blue, ...red])))),
  paletted: tga(join(head(1, 1, 1, 8, 0), new Uint8Array(4))), short: tga(join(head(2, 4, 4, 32, 0), new Uint8Array(4))), rleShort: tga(join(head(10, 2, 2, 32, 0), new Uint8Array([200]))),
  dxt: [dxt.fourcc, dxt.w, dxt.h, dxt.top.length], plain: list(dds(join(ddsHead(1, 1, [0, 0, 0, 0], 32, 0x41), new Uint8Array(blue)))),
  notDds: dds(new Uint8Array(200)), odd: dds(join(ddsHead(4, 4, [90, 90, 90, 90], 0, 4), new Uint8Array(8))),
}));
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class SkinTextures(unittest.TestCase):
    got = None

    @classmethod
    def setUpClass(cls):
        cls.got = json.loads(subprocess.run(["node", "-e", DECODE, str(WEB / "model3d.js")], capture_output=True, text=True, check=True).stdout)

    def test_a_tga_comes_out_rgba_with_its_top_row_first(self):
        self.assertEqual(self.got["bottomUp"], [255, 0, 0, 128, 0, 0, 255, 255])  # stored from the bottom up: the game's own export
        self.assertEqual(self.got["topDown"], [0, 0, 255, 255, 255, 0, 0, 128])

    def test_24_bits_and_rle(self):
        self.assertEqual(self.got["bits24"], [3, 2, 1, 255])
        self.assertEqual(self.got["rle"], [0, 0, 255, 255, 0, 0, 255, 255])
        self.assertEqual(self.got["raw"], [0, 0, 255, 255, 255, 0, 0, 128])

    def test_what_can_t_be_drawn_is_nothing(self):
        for k in ("paletted", "short", "rleShort", "notDds", "odd"):
            self.assertIsNone(self.got[k], k)

    def test_dds(self):
        self.assertEqual(self.got["dxt"], ["DXT1", 4, 4, 8])
        self.assertEqual(self.got["plain"], [0, 0, 255, 255])


FM = b"""Vne:r=1540
VneMach:r=2.1
Mass{
  EmptyMass:r=18000
  GearDestructionIndSpeed:r=700
}
Aerodynamics{
  WingPlane{
    Strength{
      VNE:r=1540
      MNE:r=2.1
    }
  }
}
"""
AIRCRAFT = b'model:t="j50"\nfmFile:t="fm/j50.blk"\nweapon_presets{\n  preset{\n    name:t="j50_default"\n    blk:t="gameData/FlightModels/weaponPresets/j50_default.blk"\n  }\n}\n'
J50_MISSION = (b'mission_settings{\n  player{\n    army:i=1\n    wing:t="t1_player01"\n  }\n  mission{\n    name:t="j50_test"\n'
               b'    level:t="levels/avg_training_ground.bin"\n  }\n}\nunits{\n  armada{\n    name:t="t1_player01"\n'
               b'    tm:m=[[1, 0, 0] [0, 1, 0] [0, 0, 1] [0, 1000, 0]]\n    unit_class:t="j50"\n    props{\n      army:i=1\n    }\n  }\n}\n')
PACKAGE = {"README.txt": b"Copy content and UserMissions into the game.",
           "content/pkg_local/gameData/flightModels/j50.blk": AIRCRAFT,
           "content/pkg_local/gameData/flightModels/fm/j50.blk": FM,
           "content/pkg_local/gameData/flightModels/weaponPresets/j50_default.blk": b"weapon{}",
           "content/pkg_local/res/pkg_local_/j50.grp": b"\0model", "content/pkg_local/res/pkg_local_/j50.dxp.bin": b"\0textures",
           "UserMissions/J50/j50_test.blk": J50_MISSION, "UserMissions/J50/usr_j50.csv": "<ID|readonly|noverify>;English\nj50;J-50\n".encode()}


def own_grp(names: list, textures: list) -> bytes:
    """A mod's pack (GRP2): its names, then one model carrying its texture names."""
    strings_at = 64 + 4 * len(names)
    strings, spots = b"", []
    for n in names:
        spots.append(strings_at + len(strings))
        strings += n.encode() + b"\0"
    res_at = strings_at + len(strings)
    model_at = res_at + 12
    tex = b"".join(t.encode() + b"\0" for t in textures)
    offs, at = [], 16
    for t in textures:
        offs.append(at)
        at += len(t) + 1
    block = struct.pack("<IIQ", 16 + len(tex), len(textures), 0) + tex + b"".join(struct.pack("<I", o) for o in offs)
    model = struct.pack("<5I", 4, len(textures), 0, 0, 0) + struct.pack("<I", len(block)) + block
    head = b"GRP2" + struct.pack("<III", model_at - 16, model_at - 16, 0)
    head += struct.pack("<IIQ", 64, len(names), 0) + struct.pack("<IIQ", res_at, 1, 0) + struct.pack("<IIQ", res_at, 1, 0)
    return head + b"".join(struct.pack("<i", s) for s in spots) + strings + struct.pack("<IIHH", mods.DYNMODEL, model_at, 0, 0) + model


def own_dxp(names: list) -> bytes:
    """A texture pack (DxP2): its names' table and names."""
    strings_at = 16 + 8 * len(names)
    strings, spots = b"", []
    for n in names:
        spots.append(strings_at + len(strings))
        strings += n.encode() + b"\0"
    dump = struct.pack("<IIQ", 16, len(names), 0) + b"".join(struct.pack("<Q", s) for s in spots) + strings
    return b"DxP2" + struct.pack("<III", 2, len(names), len(dump)) + dump


class Vehicles(Base):
    """A custom-vehicle package (the J-50's shape): into content/pkg_local and UserMissions, its vehicle offered in WTFTD."""

    def install(self, files=PACKAGE, running=False):
        found = self.stage(files, "vehicle", name="J50_v014.zip")
        mods.install(self.game, "abcdef", "vehicle", ids=IDS, running=running)
        return found["vehicle"]

    def test_installed_where_its_readme_says_and_offered(self):
        found = self.install()
        self.assertEqual((found["name"], found["missions"], found["files"]), ("J50_v014", ["j50_test.blk"], 7))  # the README stays out
        v, = found["vehicles"]
        self.assertEqual({k: v[k] for k in ("id", "name", "kind", "block", "preset", "model")},
                         {"id": "j50", "name": "J-50", "kind": "air", "block": "armada", "preset": "j50_default", "model": "j50"})
        self.assertEqual((v["lim"]["v"], v["lim"]["m"], v["lim"]["mass"]), (1540, 2.1, 18000))  # its own flight model
        self.assertTrue((self.game / "content/pkg_local/gamedata/flightModels/j50.blk").is_file())  # gamedata: as WTFTD writes
        self.assertTrue((self.game / "content/pkg_local/res/pkg_local_/j50.dxp.bin").is_file())
        self.assertTrue((self.game / "UserMissions/J50/usr_j50.csv").is_file())
        self.assertFalse((self.game / "README.txt").exists())
        self.assertEqual(list(mods.mod_vehicles()), ["j50"])
        self.assertEqual(mods.mod_vehicles()["j50"]["package"], "J50_v014")
        pkg, = mods.vehicle_packages(self.game)
        self.assertEqual((pkg["name"], pkg["files"], pkg["missions"]), ("J50_v014", 7, ["j50_test.blk"]))

    def test_removed_whole(self):
        self.install()
        mods.remove(self.game, "vehicle", "J50_v014")
        self.assertEqual((mods.mod_vehicles(), mods.vehicle_packages(self.game)), ({}, []))
        self.assertFalse((self.game / "content").exists())
        self.assertFalse((self.game / "UserMissions").exists())

    def test_uninstall_takes_them_too_unless_the_game_runs(self):
        self.install()
        self.assertEqual(mods.counts()["vehicles"], 1)
        self.assertTrue(mods.remove_all(self.game, running=True)["kept"])  # left for a later try, still listed
        self.assertEqual(list(mods.read_manifest()["vehicles"]), ["J50_v014"])
        self.assertTrue((self.game / "content/pkg_local/gamedata/flightModels/j50.blk").is_file())
        mods.remove_all(self.game, running=False)
        self.assertFalse((self.game / "content").exists())
        self.assertEqual(mods.read_manifest()["vehicles"], {})

    def test_what_a_package_cant_hold_refuses_it_whole(self):
        for code, extra in (("place", {"content/pkg_local/gameData/flightModels/evil.bin": b"x"}),  # a .bin out of res/
                            ("place", {"content/pkg_main/gameData/x.blk": b"x"}),  # not one of the user packages
                            ("place", {"Saves/x.blk": b"x"}),
                            ("type", {"content/pkg_local/res/run.exe": b"MZ"})):
            with self.subTest(extra=list(extra)):
                with self.assertRaises(mods.ModsError) as e:
                    self.stage({**PACKAGE, **extra}, "vehicle")
                self.assertEqual(e.exception.code, code)
                mods.forget("abcdef")
        self.assertFalse((self.game / "content").exists())

    def test_one_of_the_games_vehicles_goes_in_as_a_copy(self):  # the FA-22+'s Su-33: the game's stays as it is
        mine = b'include "f_16a_base.blk"\nmodel:t="j50"\nfmFile:t="fm/j50.blk"\n'
        self.stage({**PACKAGE, "content/pkg_local/gameData/flightModels/f_16a.blk": mine,
                    "UserMissions/J50/j50_test.blk": J50_MISSION.replace(b'unit_class:t="j50"', b'unit_class:t="f_16a"')}, "vehicle")
        mods.install(self.game, "abcdef", "vehicle", ids=IDS)
        flight = self.game / "content/pkg_local/gamedata/flightModels"
        self.assertFalse((flight / "f_16a.blk").exists())
        self.assertEqual((flight / "pack/f_16a.blk").read_text(),
                         'include "#/develop/gameBase/gamedata/flightModels/f_16a_base.blk"\nmodel:t="j50"\nfmFile:t="fm/j50.blk"\n')
        self.assertEqual((flight / "pack/fm/j50.blk").read_text(), 'include "#/develop/gameBase/gamedata/flightModels/fm/j50.blk"\n')
        self.assertIn(b'unit_class:t="pack/f_16a"', (self.game / "UserMissions/J50/j50_test.blk").read_bytes())  # its missions fly the copy
        m, = mods.read_manifest()["vehicles"].values()
        v = next(v for v in m["vehicles"] if v.get("copy"))
        self.assertEqual((v["id"], v["unit"], v["copy"], v["name"], m["copies"]),
                         ("pack.f_16a", "pack/f_16a", "f_16a", "f_16a", {"vehicles": ["f_16a"]}))  # named as the game's, not its folder
        mods.remove(self.game, "vehicle", "pack")
        self.assertFalse((self.game / "content").exists())

    def test_models_and_textures_named_like_the_games_are_renamed(self):  # the F-22 free flight's su_33 and empty_glass
        files = {"content/pkg_local/gameData/flightModels/ac_su_33.blk": b'model:t="su_33"\n',
                 "content/pkg_local/res/pkg_local_/su_33.grp": own_grp(["su_33", "su_33_skeleton", "rack"], ["empty_glass*", "su_33_c*"]),
                 "content/pkg_local/res/pkg_local_/su_33.dxp.bin": own_dxp(["empty_glass*", "su_33_c*"])}
        there = ({"su_33", "su_33_skeleton"}, {"empty_glass"})
        with mock.patch.object(mods, "_game_names", lambda game: there):
            found = self.stage(files, "vehicle")["vehicle"]
            mods.install(self.game, "abcdef", "vehicle", ids=IDS)
        self.assertEqual(found["copies"], {"models": ["su_33"], "textures": ["empty_glass"]})
        self.assertEqual(found["vehicles"][0]["model"], "z0_33")
        res = self.game / "content/pkg_local/res/pkg_local_"
        grp = (res / "su_33.grp").read_bytes()
        self.assertEqual([n for _, n in mods._grp_names(grp)], ["z0_33", "z0_33_skeleton", "rack"])
        self.assertEqual([n for _, n in mods._grp_textures(grp)], ["z0pty_glass*", "su_33_c*"])
        self.assertEqual([n for _, n in mods._dxp_names((res / "su_33.dxp.bin").read_bytes())], ["z0pty_glass*", "su_33_c*"])
        self.assertEqual((self.game / "content/pkg_local/gamedata/flightModels/ac_su_33.blk").read_text(), 'model:t="z0_33"\n')

    def test_a_tank_gets_the_shells_its_mission_gives_it(self):  # the T-14's: empty slots gave it one round, no reload
        tank = (b'model:t="t_14"\ncommonWeapons{\n  Weapon{\n    blk:t="gameData/Weapons/groundModels_weapons/gun.blk"\n    bullets:i=45\n  }\n'
                b'  Weapon{\n    bullets:i=300\n  }\n}\n')
        armata = ('mission_settings{\n  player{\n    army:i=1\n    wing:t="me"\n  }\n  mission{\n    name:t="armata"\n'
                  '    level:t="levels/avg_training_ground.bin"\n  }\n}\nunits{\n  tankModels{\n    name:t="me"\n'
                  '    tm:m=[[1, 0, 0] [0, 1, 0] [0, 0, 1] [0, 0, 0]]\n    unit_class:t="t_14"\n    bullets0:t="125mm_3bm42"\n'
                  '    bullets1:t=""\n    bulletsCount0:i=20\n    bulletsCount1:i=10\n  }\n}\n').encode()
        files = {"content/pkg_local/gameData/units/tankModels/t_14.blk": tank}
        v, = self.stage({**files, "UserMissions/Armata/armata.blk": armata}, "vehicle")["vehicle"]["vehicles"]
        self.assertEqual(v["ammo"], [{"id": "125mm_3bm42", "count": 20}, {"id": "", "count": 10}, {"id": "", "count": 0}, {"id": "", "count": 0}])
        mods.forget("abcdef")
        v, = self.stage(files, "vehicle")["vehicle"]["vehicles"]
        self.assertEqual(v["ammo"], [{"id": "", "count": 45}])  # no mission: its gun full of its own shell

    def test_a_model_the_game_wont_draw_is_told(self):  # the Ratte's, of an old modding kit: invisible in battle
        from tests.test_models import grp, scene_model
        self.assertNotIn("invisible", self.stage(PACKAGE, "vehicle")["vehicle"]["vehicles"][0])
        mods.forget("abcdef")
        old = grp([(mods.DYNMODEL, "j50", scene_model(0x60)), (mods.DYNMODEL, "j50_dmg", scene_model(0x60))])
        self.assertTrue(self.install({**PACKAGE, "content/pkg_local/res/pkg_local_/j50.grp": old})["vehicles"][0]["invisible"])
        self.assertTrue(mods.vehicle_packages(self.game)[0]["vehicles"][0]["invisible"])  # still said in the list

    def test_its_weapons_for_any_pylon(self):  # the J-50's PL-15: in the pylon catalog under its package, and in My weapons
        pl15 = (b'rocketGun:b=yes\nmesh:t="j50_pl15_flight"\nrocket{\n  bulletName:t="cn_pl15"\n  iconType:t="missile_type_b_air_to_air_midrange"\n'
                b'  mass:r=210.0\n  machMax:r=4.5\n  guidanceType:t="radar"\n  bulletType:t="aam"\n}\n')
        weapons = "content/pkg_local/gameData/Weapons/"
        self.install({**PACKAGE, weapons + "rocketGuns/j50_pl15_internal.blk": pl15,
                      weapons + "rocketGuns/j50_pl15_light.blk": b'include "j50_pl15_internal.blk"\n"@override:rocket"{\n  mass:r=100.0\n}\n',
                      weapons + "containers/j50_pl15_bay.blk": b'container:b=yes\nblk:t="gameData/Weapons/rocketGuns/j50_pl15_internal.blk"\n',
                      weapons + "groundModels_weapons/125mm_2a82_user_cannon.blk": b'bullet{\n  caliber:r=0.125\n}\n',  # a tank's
                      weapons + "rocketGuns/us_aim9l.blk": pl15,  # named like one of the game's
                      "UserMissions/J50/usr_j50.csv": "<ID|readonly|noverify>;English\nj50;J-50\nweapons/j50_pl15_internal/short;PL-15\n".encode()})
        game = {"us_aim9l": {"p": "gameData/Weapons/rocketguns/us_aim9l.blk", "c": "aam_ir", "ic": "missile_type_b_air_to_air_midrange"}}
        got = mods.package_weapons(self.game, game)
        self.assertEqual(sorted(got), ["j50_pl15_internal", "j50_pl15_light"])  # not the bay, the tank's gun, the game's
        w = got["j50_pl15_internal"]
        self.assertEqual({k: w[k] for k in ("p", "c", "g", "t", "m", "ic", "pkg", "name", "md")},
                         {"p": "gamedata/Weapons/rocketGuns/j50_pl15_internal.blk", "c": "aam_radar", "g": "radar", "t": "aam", "m": 210.0,
                          "ic": "missile_type_b_air_to_air_midrange", "pkg": "J50_v014", "name": "PL-15", "md": "j50_pl15_flight"})
        self.assertEqual((got["j50_pl15_light"]["m"], got["j50_pl15_light"]["name"]), (100.0, "J50 PL15 Light"))  # what it includes counts
        self.assertEqual(mods.package_weapon(self.game, "content/pkg_local/gamedata/Weapons/rocketGuns/elsewhere.blk"), {})
        # in WTFTD: the pylon catalog, the page's list, the editor's values
        data = self.root / "data"
        data.mkdir()
        (data / "weapons.json").write_text(json.dumps(game), encoding="utf-8")
        with mock.patch.object(server, "DATA", data), mock.patch.object(server.STATE, "catalog", None), \
                mock.patch.object(server.STATE, "game_dir", return_value=self.game):
            self.assertEqual(sorted(server.STATE.get_catalog()), ["j50_pl15_internal", "j50_pl15_light", "us_aim9l"])
            base = server.weapon_base("j50_pl15_internal")
            self.assertEqual((base["kind"], base["mass"], base["mach"], base["guided"]), ("rocket", 210.0, 4.5, True))
            mods.remove(self.game, "vehicle", "J50_v014")
            server.STATE.forget_vehicles()
            self.assertEqual(sorted(server.STATE.get_catalog()), ["us_aim9l"])  # gone with it: WTFTD leaves its pylons empty
            self.assertIsNone(server.weapon_base("j50_pl15_internal"))

    def test_one_of_its_missions_out_of_the_game(self):  # its vehicle stays; the folder's texts go with its last mission
        self.install()
        self.assertFalse(mods.remove_mission(self.game, "elsewhere/x.blk"))
        self.assertTrue(mods.remove_mission(self.game, "J50/j50_test.blk"))
        self.assertFalse((self.game / "UserMissions").exists())
        self.assertTrue((self.game / "content/pkg_local/gamedata/flightModels/j50.blk").is_file())
        m, = mods.read_manifest()["vehicles"].values()
        self.assertEqual((m["missions"], [f for f in m["files"] if f.startswith("UserMissions")]), ([], []))
        mods.remove(self.game, "vehicle", "J50_v014")
        self.assertFalse((self.game / "content").exists())

    def test_no_vehicle_in_it(self):
        with self.assertRaises(mods.ModsError) as e:
            self.stage({"UserMissions/J50/j50_test.blk": b"mission_settings{}"}, "vehicle")
        self.assertEqual(e.exception.code, "noVehicle")

    def test_in_with_the_game_running_out_only_closed(self):  # new files: read at its next start; in use, removing could stop half way
        self.install(running=True)
        self.assertTrue((self.game / "content/pkg_local/gamedata/flightModels/j50.blk").is_file())
        with self.assertRaises(mods.ModsError) as e:
            mods.remove(self.game, "vehicle", "J50_v014", running=True)
        self.assertEqual(e.exception.code, "running")
        self.assertEqual(list(mods.mod_vehicles()), ["j50"])  # still listed: nothing of it left nobody's
        mods.remove(self.game, "vehicle", "J50_v014")
        self.assertFalse((self.game / "content").exists())

    def test_not_over_what_is_there(self):
        (self.game / "UserMissions/J50").mkdir(parents=True)
        (self.game / "UserMissions/J50/j50_test.blk").write_bytes(b"the player's own")
        self.stage(PACKAGE, "vehicle")
        with self.assertRaises(mods.ModsError) as e:
            mods.install(self.game, "abcdef", "vehicle", ids=IDS)
        self.assertEqual(e.exception.code, "exists")
        self.assertEqual((self.game / "UserMissions/J50/j50_test.blk").read_bytes(), b"the player's own")
        self.assertFalse((self.game / "content").exists())


class SeveralAtOnce(Base):
    """Several .zip picked or dropped together, of any kind: each one's kind told from its files."""

    def kind(self, files: dict, token: str) -> str:
        z = archive(self.root / f"{token}.zip", files)
        with open(z, "rb") as f:
            mods.receive(token, z.name, f, z.stat().st_size, "auto")
        return mods.detect(token)

    def test_each_goes_where_it_belongs(self):
        self.assertEqual(self.kind(PACKAGE, "pack0001"), "vehicle")
        self.assertEqual(self.kind({"FA-22/pkg_local/gameData/flightModels/a.blk": b"model:t=\"a\"\n"}, "pack0002"), "vehicle")
        self.assertEqual(self.kind({"engines/f16.bank": b"bank", "readme.txt": b"x"}, "pack0003"), "sound")
        self.assertEqual(self.kind({"my rafale/rafale_c_f3_c.tga": b"tga", "my rafale/rafale_c_f3.blk": b"x"}, "pack0004"), "skin")

    def test_only_an_archive(self):
        with self.assertRaises(mods.ModsError) as e:
            mods.receive("pack0005", "a.tga", io.BytesIO(b"1"), 1, "auto")
        self.assertEqual(e.exception.code, "type")


class PackageShapes(Base):
    """What the packages players share do (CL-1201, Ratte, T-14, F-22 free flight, FA-22+), each read as the game reads it."""

    def vehicles(self, files: dict, ids=IDS) -> list:
        with open(archive(self.root / "pack.zip", files), "rb") as f:
            mods.receive("abcdef", "pack.zip", f, (self.root / "pack.zip").stat().st_size, "vehicle")
        return mods.inspect("abcdef", "vehicle", ids)["vehicle"]

    def test_one_of_the_games_vehicles_with_changes_of_its_own(self):  # the CL-1201: the B-52H, its model, its flight model
        dm = self.root / "dm" / "aces.vromfs.bin_u" / "gamedata" / "flightmodels"
        (dm / "fm").mkdir(parents=True)
        (dm / "b_52h.blkx").write_text(json.dumps({"model": "b_52h", "fmFile": "fm/b_52h.blk", "gunnerFps": {"pos": [1, 2, 3]},
                                                   "weapon_presets": {"preset": {"name": "b_52h_default"}}}))
        (dm / "fm" / "nt_tu_95m.blkx").write_text(json.dumps(blk.loads(FM.decode())))
        mine = (b'include "b_52h.blk"\n"@override:model":t="cl1201"\n"@override:fmFile":t="fm/cl1201.blk"\n"@delete:gunnerFps"{}\n'
                b'"@override:weapon_presets"{\n  preset{\n    name:t="cl1201_default"\n  }\n}\n')
        fm = b'include "nt_tu_95m.blk"\n"@override:Vne":r="1000.0"\n'
        with mock.patch.object(builder, "DM", self.root / "dm"):
            v, = self.vehicles({"content/pkg_local/gameData/flightModels/cl1201.blk": mine,
                                "content/pkg_local/gameData/flightModels/fm/cl1201.blk": fm})["vehicles"]
        self.assertEqual((v["id"], v["model"], v["preset"]), ("cl1201", "cl1201", "cl1201_default"))
        self.assertEqual((v["lim"]["v"], v["lim"]["m"]), (1000, 2.1))  # its own Vne, the rest the Tu-95's

    def test_a_vehicle_in_a_folder_of_its_own(self):  # the Ratte: the Tetrarch's name, but not the game's Tetrarch
        found = self.vehicles({"content/pkg_local/gameData/units/tankmodels/p1000_ratte/uk_a17_mk_1_tetrarch.blk": '\ufeffmodel:t="p1000"\n'.encode(),
                               "content/pkg_local/gameData/units/tankmodels/p1000_ratte/notes.blk": b"no model here{}"},
                              ids=(*IDS, "uk_a17_mk_1_tetrarch"))
        v, = found["vehicles"]
        self.assertEqual((v["id"], v["unit"], v["name"], v["kind"], v["model"]),
                         ("p1000_ratte.uk_a17_mk_1_tetrarch", "p1000_ratte/uk_a17_mk_1_tetrarch", "p1000_ratte", "ground", "p1000"))

    def test_a_file_that_names_no_model_is_not_a_vehicle(self):  # the T-14's empty flightModels file of its tank's name
        found = self.vehicles({"content/pkg_local/gameData/flightModels/ussr_t_14_armata.blk": b"",
                               "content/pkg_local/gameData/units/tankModels/ussr_t_14_armata.blk": b'model:t="t_14_armata"\n',
                               "content/pkg_local/gameData/units/tankModels/ussr_t_14_armat.blk": b'model:t="t_14_armata"\n',
                               "content/pkg_local/lang/usr.csv": b"<ID|readonly|noverify>;English\nussr_t_14_armata;T-14\nussr_t_14_armat;T-14\n"})
        self.assertEqual([(v["id"], v["kind"], v["name"]) for v in found["vehicles"]],
                         [("ussr_t_14_armat", "ground", "T-14 (ussr_t_14_armat)"), ("ussr_t_14_armata", "ground", "T-14 (ussr_t_14_armata)")])

    def test_without_its_content_folder_and_with_pictures(self):  # the FA-22+'s pkg_local, the F-22's HUD pictures
        self.stage({"pkg_local/gameData/flightModels/j50.blk": AIRCRAFT, "pkg_local/hud/hit.png": b"\x89PNG",
                    "Usermissions/j50_test.blk": J50_MISSION, "Usermissions/template/parts.blk": b'mission_settings{\n  player{\n    wing:t="x"\n  }\n  mission{\n    level:t="levels/avg_training_ground.bin"\n  }\n}\nunits{}\n'},
                   "vehicle")
        mods.install(self.game, "abcdef", "vehicle", ids=IDS)
        self.assertTrue((self.game / "content/pkg_local/gamedata/flightModels/j50.blk").is_file())
        self.assertTrue((self.game / "content/pkg_local/hud/hit.png").is_file())
        m, = mods.read_manifest()["vehicles"].values()
        self.assertEqual(m["missions"], ["UserMissions/j50_test.blk"])  # parts aren't missions

    def test_a_picture_goes_nowhere_else(self):
        self.refused("place", {"content/pkg_local/res/pkg_local_/x.png": b"\x89PNG", "content/pkg_local/gameData/flightModels/j50.blk": AIRCRAFT}, "vehicle")


class ModVehicleInWtftd(unittest.TestCase):
    def test_listed_like_the_games_with_its_details(self):
        v = {"id": "j50", "name": "J-50", "kind": "air", "block": "armada", "preset": "j50_default", "lim": {"v": 1540}, "package": "J50_v014"}
        self.assertEqual({k: server.mod_vehicle(v)[k] for k in ("id", "c", "n", "mod", "name")},
                         {"id": "j50", "c": "air", "n": "other", "mod": "J50_v014", "name": "J-50"})
        d = server.mod_details(v)
        self.assertEqual((d["b"], d["pr"][0]["id"], d["st"]["lim"], d["am"]), ("armada", "j50_default", {"v": 1540}, []))

    def test_a_mission_names_a_vehicle_in_a_folder_by_its_place(self):
        known = {"p1000_ratte.uk_a17_mk_1_tetrarch": {"id": "p1000_ratte.uk_a17_mk_1_tetrarch", "unit": "p1000_ratte/uk_a17_mk_1_tetrarch"},
                 "f_16a": {"id": "f_16a"}}
        self.assertEqual(server.known_vehicle({"vehicle": "p1000_ratte/uk_a17_mk_1_tetrarch", "preset": ""}, known)["vehicle"],
                         "p1000_ratte.uk_a17_mk_1_tetrarch")
        self.assertEqual(server.known_vehicle({"vehicle": "f_16a"}, known)["vehicle"], "f_16a")
        self.assertIsNone(server.known_vehicle({"vehicle": "uk_a17_mk_1_tetrarch"}, known))

    def test_its_model_is_the_one_its_file_names(self):
        found = {"j50": {"id": "j50", "model": "j50_mk2"}, "old": {"id": "old"}}  # old: installed before WTFTD kept it
        with mock.patch.object(mods, "mod_vehicles", return_value=found):
            self.assertEqual((server.mod_model("j50"), server.mod_model("old"), server.mod_model("f_16a")), ("j50_mk2", "old", ""))


class MissionsInTheGame(unittest.TestCase):
    """My missions' Created in the game: WTFTD's own and the vehicle packages', as the game lists them."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.game = Path(d.name)
        um = self.game / "UserMissions"
        (um / "J50").mkdir(parents=True)
        (um / "wtftd_f_16a.blk").write_text("mission")
        (um / "usr_wtftd_f_16a.csv").write_text("texts")
        (um / "usr_wtftd_gone.csv").write_text("texts of a mission deleted before")
        (um / "J50" / "j50_test.blk").write_bytes(J50_MISSION)
        (um / "J50" / "usr_j50.csv").write_text("<ID|readonly|noverify>;English\nmissions/j50_test;J-50 test flight\n")
        manifest = {"skins": {}, "sounds": {}, "vehicles": {"J50_v014": {"files": ["UserMissions/J50/j50_test.blk", "UserMissions/J50/usr_j50.csv"],
                                                                         "vehicles": [], "missions": ["UserMissions/J50/j50_test.blk"]}}}
        for target, name, value in ((server.STATE, "game_dir", lambda: self.game), (server.STATE, "get_vehicles", lambda: {"j50": {"id": "j50"}}),
                                    (mods, "read_manifest", lambda: manifest), (mods, "MANIFEST", self.game / "user" / "m.json"),
                                    (server, "MISSION_SETUPS", self.game / "setups")):
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_packages_missions_are_listed_as_the_game_shows_them(self):
        found = server.list_generated()
        self.assertEqual([m["file"] for m in found], ["wtftd_f_16a.blk", "J50/j50_test.blk"])
        self.assertEqual({k: found[1][k] for k in ("package", "title", "vehicle")}, {"package": "J50_v014", "title": "J-50 test flight", "vehicle": "j50"})

    def test_several_at_once(self):  # the list's picked ones: WTFTD's own with their texts, a package's through its manifest
        (self.game / "setups").mkdir()
        (self.game / "setups" / "wtftd_f_16a.json").write_text("{}")
        (self.game / "UserMissions" / "wtftd_f_16a.imports").mkdir()  # what it imports (imports.for_game)
        (self.game / "UserMissions" / "wtftd_f_16a.imports" / "template_t.blk").write_text("areas{}")
        with mock.patch.object(mods, "remove_mission") as removed:
            for f in ("wtftd_f_16a.blk", "J50/j50_test.blk"):
                server.delete_mission(self.game, f)
        self.assertEqual(sorted(p.name for p in (self.game / "UserMissions").iterdir()), ["J50", "usr_wtftd_gone.csv"])
        self.assertFalse((self.game / "setups" / "wtftd_f_16a.json").exists())
        removed.assert_called_once_with(self.game, "J50/j50_test.blk")

    def test_a_packages_mission_keeps_what_it_imports(self):  # the T-14's template: deleted from the game since, it still loads
        um = self.game / "UserMissions"
        (um / "template").mkdir()
        (um / "template" / "t.blk").write_text("areas{}\n")
        (um / "J50" / "j50_test.blk").write_bytes(J50_MISSION.replace(b"units{", b'imports{\n  import_record{\n    file:t="UserMissions/template/t.blk"\n  }\n}\nunits{', 1))
        with mock.patch.object(imports, "IMPORTED", self.game / "imported"), mock.patch.object(mission, "IMPORTED", self.game / "imported"):
            got, = server.package_missions(self.game, ["UserMissions/J50/j50_test.blk"])
            self.assertEqual(imports.parts(got["scenario"]["id"]), {"UserMissions/template/t.blk": "areas{}\n"})

    def test_a_deleted_missions_texts_go_with_it(self):
        server.list_generated()
        self.assertFalse((self.game / "UserMissions/usr_wtftd_gone.csv").exists())  # left by an older WTFTD
        self.assertTrue((self.game / "UserMissions/usr_wtftd_f_16a.csv").exists())


class Pictures(unittest.TestCase):
    """What the page draws with its 3D view of a package's vehicle or of a skin, for the lists (model3d.js mdCapture)."""
    PNG = base64.b64encode(server.PNG + b"pixels").decode()

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        vehicles = {"j50": {"id": "j50", "mod": "J50_v014"}, "f_16a": {"id": "f_16a"}}
        skins = [{"name": "Desert camo", "files": 2, "bytes": 300}]
        for target, name, value in ((server, "CAPTURES", self.dir), (server.STATE, "get_vehicles", lambda: vehicles),
                                    (server.STATE, "game_dir", lambda: self.dir), (mods, "skins", lambda gd, ids=(): skins)):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_a_package_vehicle_keeps_its_picture(self):
        url = server.save_capture("unit", "j50", self.PNG)
        self.assertTrue(url.startswith("/img/capture/unit-j50.png?v="))
        self.assertEqual((self.dir / "unit-j50.png").read_bytes(), server.PNG + b"pixels")
        self.assertTrue(server.mod_vehicle({"id": "j50"})["pic"])

    def test_a_skin_keeps_its_picture_until_its_files_change(self):
        url = server.save_capture("skin", "Desert camo", self.PNG)
        key = server.skin_key({"name": "Desert camo", "files": 2, "bytes": 300})
        self.assertTrue(url.startswith(f"/img/capture/{key}.png"))
        self.assertNotEqual(key, server.skin_key({"name": "Desert camo", "files": 2, "bytes": 301}))

    def test_only_a_png_of_what_wtftd_lists(self):
        self.assertIsNone(server.save_capture("unit", "f_16a", self.PNG))  # the game's own vehicles: the encyclopedia's pictures
        self.assertIsNone(server.save_capture("skin", "not installed", self.PNG))
        self.assertIsNone(server.save_capture("unit", "j50", base64.b64encode(b"<svg onload=x>").decode()))
        self.assertIsNone(server.save_capture("unit", "j50", "not base64!"))
        self.assertIsNone(server.save_capture("file", "../settings", self.PNG))
        self.assertEqual(list(self.dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
