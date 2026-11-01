"""My battles: the player's own results from replay files. Synthetic files, plus the real ones when this PC has them."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_vromfs import blk_body, f32
from wtftd import game, paths, replays, server, vromfs

ME = "13672816"
PLANES = "gamedata/missions/cta/planes/historical/bfd/air_afghan_bfd_norespawn.blk"


def blk(root: dict) -> bytes:
    """A dict as the game writes a BLK: blocks breadth first, each one's params in that order."""
    names, params, blocks, data, queue = [], [], [], bytearray(), [("", root)]

    def name(s):
        if s not in names:
            names.append(s)
        return names.index(s)
    for i, (key, d) in enumerate(queue):  # the queue grows: children come after their parent
        kids = [(k, x) for k, v in d.items() for x in (v if isinstance(v, list) else [v]) if isinstance(x, dict)]
        first = len(queue)
        queue += kids
        count = 0
        for k, v in d.items():
            for x in v if isinstance(v, list) else [v]:
                if isinstance(x, dict):
                    continue
                count += 1
                if isinstance(x, str):
                    params.append((name(k), 1, len(data)))
                    data += x.encode() + b"\0"
                elif isinstance(x, bool):
                    params.append((name(k), 9, int(x)))
                elif isinstance(x, int):
                    params.append((name(k), 2, x & 0xFFFFFFFF))
                else:
                    params.append((name(k), 3, f32(x)))
        blocks.append([name(key) + 1 if i else 0, count, len(kids), first])
    return blk_body(names, params, [tuple(b) for b in blocks], bytes(data), own_names=names)


def player(uid, nick, **stats) -> dict:
    return {"name": nick, "clanTag": "=TAG=", "kills": 0, "deaths": 0, "assists": 0, "score": 0, "awardDamage": 0,
            "damageZone": 0, "groundKills": 0, "navalKills": 0, "aiKills": 0, "aiGroundKills": 0, "aiNavalKills": 0,
            "userId": uid, "team": 1, **stats}


def results(status="success", crafts=None, me=None) -> dict:
    players = [player(ME, "Myself", **(me or {})), player("555", "SomeoneElse", kills=9, score=9999)]
    out = {"timePlayed": 404.5, "authorUserId": ME, "author": "=TAG= Myself", "player": players,
           "uiScriptsData": {"playersInfo": {f"__int_{ME}": {"name": "Myself", "crafts": crafts or {"0": "mirage_4000"}},
                                             "__int_555": {"name": "SomeoneElse", "crafts": {"0": "su_33"}}}}}
    return {"status": status, **out} if status else out


def wrpl(comments: dict | None, level="levels/air_afghan.bin", mission=PLANES, cls="base_dom", difficulty=0x75, start=1750000000,
         loc="missions/air_afghan_BfD_norespawn", recording=b"\xAA" * 64) -> bytes:
    head = bytearray(replays.HEADER + 128)
    head[:4] = replays.MAGIC
    for at, text in ((8, level), (136, mission), (780, loc), (968, cls)):
        head[at:at + len(text)] = text.encode()
    head[688] = difficulty
    struct.pack_into("<I", head, 908, start)
    if comments is not None:
        struct.pack_into("<I", head, 684, len(head) + len(recording))
    return bytes(head) + recording + (b"\x01" + blk(comments) if comments is not None else b"")


class Temp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)

    def write(self, name, raw) -> Path:
        path = self.folder / name
        path.write_bytes(raw)
        return path

    def read(self, raw):
        return replays.read_battle(self.write("x.wrpl", raw))


class Reading(Temp):
    def test_a_battle(self):
        row = self.read(wrpl(results(me={"kills": 6, "groundKills": 1, "aiKills": 2, "aiGroundKills": 1, "deaths": 1,
                                         "assists": 3, "score": 3700, "damageZone": 1200}, crafts={"1": "su_30mkk", "0": "j_10c"})))
        self.assertEqual((row["level"], row["kind"], row["diff"], row["result"], row["offline"]), ("air_afghan", "air", "rb", "win", False))
        self.assertEqual((row["start"], row["played"]), (1750000000, 404))
        self.assertEqual(row["vehicles"], ["su_30mkk", "j_10c"])
        self.assertEqual((row["kills"], row["ai"], row["deaths"], row["assists"], row["score"], row["damage"]), (7, 3, 1, 3, 3700, 1200))

    def test_result(self):
        for status, result in (("success", "win"), ("fail", "loss"), ("", "left"), ("anything else", "left")):
            self.assertEqual(self.read(wrpl(results(status)))["result"], result)

    def test_nobody_elses_name_or_numbers(self):
        text = json.dumps(self.read(wrpl(results())))
        for other in ("SomeoneElse", "su_33", "9999", "Myself", ME):
            self.assertNotIn(other, text)

    def test_mode(self):
        cases = (("gamedata/missions/cta/tanks/alps/alps_dom.blk", 0x70, "ground", "ab"), (PLANES, 0x7A, "air", "sb"),
                 ("gamedata/missions/cta/ships/x/y.blk", 0x75, "ship", "rb"), ("gamedata/missions/cta/helicopters/y.blk", 0x75, "heli", "rb"),
                 ("gamedata/missions/cta/stalingrad_ffa.blk", 0x73, "", ""))
        for mission, difficulty, kind, diff in cases:
            row = self.read(wrpl(results(), mission=mission, difficulty=difficulty))
            self.assertEqual((row["kind"], row["diff"]), (kind, diff), mission)

    def test_a_test_drive(self):
        comments = {**results(""), "player": player(ME, "Myself"), "uiScriptsData": {"playersInfo": {}}}
        row = self.read(wrpl(comments, level="levels/firing_range.bin", cls="singleMission", loc="Test Drive: Rafale - Range",
                             mission="D:/Games/tanks/War Thunder/UserMissions/wtftd_rafale_c_f3.blk"))
        self.assertTrue(row["offline"])
        self.assertEqual((row["vehicles"], row["title"], row["kind"], row["result"]), (["rafale_c_f3"], "Test Drive: Rafale - Range", "", "left"))

    def test_offline_by_each_sign(self):
        for extra in ({"cls": "singleMission"}, {"mission": "D:/WT/UserMissions/my_own.blk"}, {"level": "levels/firing_range.bin"}):
            row = self.read(wrpl(results(), **extra))
            self.assertTrue(row["offline"], extra)
        self.assertEqual(self.read(wrpl(results(), cls="singleMission", mission="D:/WT/UserMissions/my_own.blk"))["title"], "missions/air_afghan_BfD_norespawn")
        self.assertEqual(self.read(wrpl(results()))["title"], "")  # a battle's name is its map

    def test_no_vehicle_known(self):
        self.assertEqual(self.read(wrpl({**results(), "uiScriptsData": {}}))["vehicles"], [])

    def test_what_can_not_be_read(self):
        good = wrpl(results())
        stranger = {**results(), "authorUserId": "1"}
        for raw in (b"", b"\xe5\xac", b"not a replay" * 200, b"\0" + good[1:], good[:len(good) - 40], good[:replays.HEADER - 1],
                    wrpl(None), wrpl(stranger), wrpl({"timePlayed": 1.0, "authorUserId": ME}), wrpl({"player": 3, "authorUserId": ME, "timePlayed": 1.0}),
                    good[:684] + struct.pack("<I", len(good) + 500) + good[688:], good[:684] + struct.pack("<I", 12) + good[688:]):
            self.assertIsNone(self.read(raw))


class Index(Temp):
    def test_unchanged_files_are_not_read_again(self):
        self.write("a.wrpl", wrpl(results(), start=100))
        self.write("b.wrpl", wrpl(results("fail"), start=200))
        self.write("c.wrpl", b"being written")
        self.write("notes.txt", b"not a replay")
        first = replays.refresh(self.folder, {})
        self.assertEqual(sorted(first["files"]), ["a.wrpl", "b.wrpl", "c.wrpl"])
        with mock.patch.object(replays, "read_battle", side_effect=AssertionError("read again")):
            self.assertEqual(replays.refresh(self.folder, first), first)
        self.write("b.wrpl", wrpl(results("success"), start=200) + b"\0")  # a replay finishing: read once more
        (self.folder / "a.wrpl").unlink()
        second = replays.refresh(self.folder, first)
        self.assertEqual(sorted(second["files"]), ["b.wrpl", "c.wrpl"])
        self.assertEqual(second["files"]["b.wrpl"]["row"]["result"], "win")

    def test_listing(self):
        self.write("old.wrpl", wrpl(results(), start=100))
        self.write("new.wrpl", wrpl(results(), start=200))
        self.write("broken.wrpl", b"x")
        out = replays.listing(replays.refresh(self.folder, {}))
        self.assertEqual([r["file"] for r in out["rows"]], ["new.wrpl", "old.wrpl"])
        self.assertEqual(out["skipped"], 1)

    def test_an_old_or_odd_index_is_rebuilt(self):
        self.write("a.wrpl", wrpl(results()))
        for index in ({"v": 0, "files": {"a.wrpl": {"size": 0, "mtime": 0, "row": None}}}, [], {"v": replays.VERSION, "files": 3}, None):
            self.assertIn("level", replays.refresh(self.folder, index)["files"]["a.wrpl"]["row"])

    def test_no_folder(self):
        self.assertEqual(replays.refresh(self.folder / "gone", {})["files"], {})
        self.assertEqual(replays.refresh(None, {})["files"], {})


class Route(Temp):
    def setUp(self):
        super().setUp()
        (self.folder / "Replays").mkdir()
        (self.folder / "Replays" / "a.wrpl").write_bytes(wrpl(results()))
        self.index = self.folder / "cache" / "battles.json"
        for target, name, value in ((server, "BATTLES", self.index), (server.STATE, "game_dir", lambda: self.folder)):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_the_index_is_kept_and_used(self):
        self.assertEqual([r["file"] for r in server.battles()["rows"]], ["a.wrpl"])
        self.assertTrue(self.index.exists())
        with mock.patch.object(replays, "read_battle", side_effect=AssertionError("read again")):
            self.assertEqual(server.battles()["skipped"], 0)

    def test_no_game(self):
        with mock.patch.object(server.STATE, "game_dir", lambda: None):
            self.assertEqual(server.battles(), {"game": False, "rows": [], "skipped": 0})

    def test_the_index_goes_with_the_cache(self):
        self.assertEqual(self.index.name, "battles.json")
        mock.patch.stopall()
        self.assertEqual(server.BATTLES.parent, paths.CACHE)


GAME = game.detect_game_dir()


@unittest.skipUnless(GAME and any((GAME / "Replays").glob("*.wrpl")), "needs the game's replays")
class RealReplays(unittest.TestCase):
    def test_every_file_with_results_is_read(self):
        index = replays.refresh(GAME / "Replays", {})
        rows = replays.listing(index)["rows"]
        self.assertTrue(rows)
        for name, item in index["files"].items():
            with open(GAME / "Replays" / name, "rb") as f:
                head = f.read(replays.HEADER)
            if struct.unpack_from("<I", head, 684)[0]:
                self.assertIsNotNone(item["row"], name)
        for row in rows:
            self.assertRegex(row["level"], r"^[a-z0-9_]+$")
            self.assertGreater(row["played"], 0)
            if not row["offline"]:
                self.assertTrue(row["vehicles"], row["file"])
                self.assertTrue(row["kind"] and row["diff"], row["file"])

    def test_no_other_player_in_the_rows(self):
        index = replays.refresh(GAME / "Replays", {})
        rows = {r["file"]: json.dumps(r) for r in replays.listing(index)["rows"]}
        checked = 0
        for name, text in rows.items():
            with open(GAME / "Replays" / name, "rb") as f:
                f.seek(struct.unpack_from("<I", f.read(replays.HEADER), 684)[0] + 1)
                comments = vromfs.parse_blk(f.read(), [])
            players = comments["player"] if isinstance(comments["player"], list) else [comments["player"]]
            for p in players:
                if str(p["userId"]) != str(comments["authorUserId"]) and len(p["name"]) > 3:
                    self.assertNotIn(p["name"], text)
                    checked += 1
        if any(not r["offline"] for r in replays.listing(index)["rows"]):
            self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
