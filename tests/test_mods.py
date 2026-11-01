"""Skins and sounds: everything here works in a made-up game folder, with archives made on the spot."""
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock

from wtftd import mods, server, uninstall
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
                     "x" * 300 + ".tga", "/".join("abcdefgh"), "", None, 5):
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

    def test_a_compression_ratio_past_the_limit(self):
        self.refused("ratio", {"s/bomb.tga": b"\0" * (4 << 20)})
        self.stage({"s/rafale_c_f3.blk": BLK, "s/small.tga": b"\0" * 900_000})  # small files can be empty paint

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

    def test_two_vehicles_ask(self):
        g = mods.guess_vehicle("pack", ["f_16a.blk", "rafale_c_f3.blk"], [], IDS)
        self.assertEqual((g["sure"], sorted(g["candidates"])), (False, ["f_16a", "rafale_c_f3"]))


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
            self.assertEqual(mods.read_manifest(), {"skins": {}, "sounds": {}})

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

    def test_not_while_the_game_runs(self):
        self.stage({"a.bank": b"1"}, "sound")
        with self.assertRaises(mods.ModsError) as e:
            mods.install(self.game, "abcdef", "sound", running=True)
        self.assertEqual(e.exception.code, "running")


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
        self.assertEqual(uninstall.info(self.game)["mods"], {"skins": 1, "sounds": 1, "config": True})

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


if __name__ == "__main__":
    unittest.main()
