"""My hangar: what's kept in user/hangar.json, damaged files included, and the battle rating of a lineup."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wtftd import hangar, server, uninstall
from wtftd.paths import WEB


class Files(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(hangar, "FILE", Path(tmp.name) / "user" / "hangar.json")
        p.start()
        self.addCleanup(p.stop)

    def write(self, data: bytes):
        hangar.FILE.parent.mkdir(exist_ok=True)
        hangar.FILE.write_bytes(data)

    def test_no_file_is_an_empty_hangar(self):
        self.assertEqual(hangar.load(), {"owned": [], "ignored": [], "goals": [], "lineups": []})

    def test_what_is_saved_comes_back(self):
        lineup = {"id": "a1", "name": "RB 8.0", "nation": "usa", "mode": "ab", "vehicles": ["us_m4a1", "p-51d-5"]}
        hangar.save({"owned": ["us_m4a1", "p-51d-5"], "goals": ["us_m1a2"], "ignored": ["ussr_t_34"], "lineups": [lineup]})
        self.assertEqual(hangar.load(), {"owned": ["us_m4a1", "p-51d-5"], "ignored": ["ussr_t_34"], "goals": ["us_m1a2"], "lineups": [lineup]})

    def test_a_request_changes_only_its_parts(self):
        hangar.save({"owned": ["a"], "goals": ["b"]})
        hangar.save({"goals": []})
        self.assertEqual(hangar.load()["owned"], ["a"])
        self.assertEqual(hangar.load()["goals"], [])

    def test_a_file_nothing_can_read_is_kept_aside(self):
        for damaged in (b"{ not json", b"\xff\xfe\x00broken"):
            self.write(damaged)
            first = hangar.load()
            self.assertEqual((first["owned"], first["damaged"]), ([], True))  # the page tells the player, once
            self.assertEqual(hangar.FILE.with_suffix(".bad.json").read_bytes(), damaged)
            self.assertFalse(hangar.FILE.exists())
            self.assertNotIn("damaged", hangar.load())

    def test_the_hangar_works_again_after_a_damaged_file(self):
        self.write(b"[[[")
        self.assertEqual(hangar.save({"owned": ["a"]})["owned"], ["a"])
        self.assertEqual(hangar.load(), {"owned": ["a"], "ignored": [], "goals": [], "lineups": []})

    def test_a_file_of_another_shape_is_an_empty_hangar(self):
        for other in (b"[1, 2]", b"null", b'"text"', b'{"owned": 5, "lineups": {"a": 1}, "goals": "x"}'):
            self.write(other)
            self.assertEqual(hangar.load(), {"owned": [], "ignored": [], "goals": [], "lineups": []})

    def test_what_a_file_or_request_can_hold(self):
        data = hangar.clean({"owned": ["ok", "ok", 5, None, "../evil", '"><img src=x>', "x" * 200],
                             "lineups": [{"id": "good", "name": "  N  ", "mode": "zz", "nation": "<b>", "vehicles": ["a", 1, "a"]},
                                         {"id": "../bad"}, "text", {"name": "no id"}]})
        self.assertEqual(data["owned"], ["ok"])
        self.assertEqual(data["lineups"], [{"id": "good", "name": "N", "nation": "", "mode": "rb", "vehicles": ["a"]}])

    def test_sizes_are_bounded(self):
        data = hangar.clean({"owned": [f"v{i}" for i in range(hangar.MAX_IDS + 5)], "goals": [f"v{i}" for i in range(hangar.MAX_GOALS + 5)],
                             "lineups": [{"id": f"l{i}", "name": "n" * 500, "vehicles": [f"v{k}" for k in range(99)]} for i in range(hangar.MAX_LINEUPS + 5)]})
        self.assertEqual((len(data["owned"]), len(data["goals"]), len(data["lineups"])), (hangar.MAX_IDS, hangar.MAX_GOALS, hangar.MAX_LINEUPS))
        self.assertEqual((len(data["lineups"][0]["name"]), len(data["lineups"][0]["vehicles"])), (60, hangar.MAX_LINEUP_SIZE))

    def test_a_request_of_any_shape_changes_nothing(self):
        hangar.save({"owned": ["a"]})
        for body in ([], "text", None, 5):
            hangar.save(body)
        self.assertEqual(hangar.load()["owned"], ["a"])

    def test_routes(self):
        handler = mock.Mock()
        server.Handler.post_api(handler, "hangar", {"owned": ["a"]})
        self.assertEqual(handler.send_json.call_args.args[0]["owned"], ["a"])
        server.Handler.get_api(handler, "hangar")
        self.assertEqual(handler.send_json.call_args.args[0]["owned"], ["a"])

    def test_it_goes_with_the_user_part_of_uninstall_only(self):
        home = hangar.FILE.parent.parent
        cache, data, user = home / ".cache", home / "data", home / "user"
        for d in (cache, data, user):
            d.mkdir()
        hangar.save({"owned": ["a"]})
        with mock.patch.object(uninstall, "CACHE", cache), mock.patch.object(uninstall, "DATA", data), mock.patch.object(uninstall, "USER", user), \
                mock.patch.object(uninstall, "HOME", home):
            uninstall.run(["cache", "data"], None)
            self.assertTrue(hangar.FILE.exists())
            uninstall.run(["user"], None)
        self.assertFalse(hangar.FILE.exists())


RATING = """
const fs = require('fs'), vm = require('vm');
const stub = new Proxy(function () {}, { get: () => stub, apply: () => stub });
globalThis.$ = globalThis.$$ = globalThis.window = stub;
globalThis.store = { get: (k, d) => d, set() {} };
globalThis.debounce = f => f;
vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));
const rating = vm.runInThisContext('lineupRating');
const v = (id, c, ab, rb = ab, sb = ab) => ({ id, c, br: [ab, rb, sb] });
const air = (...brs) => brs.map((b, i) => v('a' + i, 'air', b));
const out = {
  ground: rating([v('t', 'ground', 5.3), v('o', 'ground', 4.3), v('m', 'air', 5.7)], 1, 14.3),
  top: rating([v('t', 'ground', 13.7)], 1, 14.3), bottom: rating([v('t', 'ground', 1.3)], 1, 14.3),
  gap: rating([v('t', 'ground', 5.3), v('o', 'ground', 4.7)], 1, 14.3),
  three: rating(air(5.0, 4.7, 4.3), 0, 14.3), five: rating(air(5.0, 2.0, 2.0, 1.0, 1.0), 0, 14.3), two: rating(air(5.3, 5.0), 0, 14.3), one: rating(air(5.3), 0, 14.3),
  same: rating(air(5.7, 5.7, 5.7), 0, 14.3),
  each: rating(air(5.0, 2.0), 1, 14.3),
  naval: rating([v('s', 'ship', 5.0), v('p', 'air', 5.3), v('q', 'air', 5.7)], 1, 14.3),
  boats: rating([v('s', 'boat', 3.0), v('p', 'air', 3.7)], 0, 14.3),
  sb: rating([v('t', 'ground', 5.3)], 2, 14.3), airsb: rating(air(5.0), 2, 14.3),
  noSb: rating([v('s', 'ship', 5.0, 5.0, null)], 2, 14.3), empty: rating([], 1, 14.3),
};
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "needs node")
class LineupRating(unittest.TestCase):
    """The official wiki's Matchmaking page, rule by rule."""
    got = None

    @classmethod
    def setUpClass(cls):
        cls.got = json.loads(subprocess.run(["node", "-e", RATING, str(WEB / "hangar.js")], capture_output=True, text=True, check=True).stdout)

    def test_ground_goes_by_the_highest_vehicle_aircraft_included(self):
        r = self.got["ground"]
        self.assertEqual((r["rule"], r["br"], r["low"], r["high"]), ("top", 5.7, 4.7, 6.7))

    def test_the_range_stops_at_both_ends_of_the_game(self):
        self.assertEqual(self.got["top"]["high"], 14.3)
        self.assertEqual(self.got["bottom"]["low"], 1.0)

    def test_a_vehicle_a_whole_rating_below_the_top_is_flagged(self):
        self.assertEqual(self.got["ground"]["far"], ["o"])  # 3 steps = 1.0: the game's own warning in a squad
        self.assertEqual(self.got["gap"]["far"], [])

    def test_air_arcade_averages_the_three_highest_rounded_up(self):
        self.assertEqual((self.got["three"]["rule"], self.got["three"]["br"]), ("avg", 5.0))  # 2.5 + 1.175 + 1.075 = 4.75: not a step, 5.0
        self.assertEqual(self.got["two"]["br"], 5.3)  # 5.15
        self.assertEqual(self.got["one"]["br"], 5.3)
        self.assertEqual(self.got["same"]["br"], 5.7)  # the steps round up to themselves

    def test_air_arcade_counts_a_low_aircraft_as_0_6_below_the_top(self):
        self.assertEqual(self.got["five"]["br"], 4.7)  # the wiki's example: 5.0 can't go lower than 4.7

    def test_air_realistic_plays_each_aircraft_on_its_own(self):
        r = self.got["each"]
        self.assertEqual((r["rule"], r["far"]), ("each", []))

    def test_naval_leaves_out_aircraft_over_a_step_above_the_highest_ship(self):
        r = self.got["naval"]
        self.assertEqual((r["rule"], r["br"], r["out"]), ("naval", 5.3, ["q"]))
        self.assertEqual(self.got["boats"]["out"], ["p"])

    def test_simulator_has_no_range(self):
        for r in (self.got["sb"], self.got["airsb"]):
            self.assertEqual((r["rule"], r["low"], r["high"]), ("sb", None, None))

    def test_nothing_to_rate(self):
        self.assertIsNone(self.got["empty"])
        self.assertIsNone(self.got["noSb"])  # ships have no SB


if __name__ == "__main__":
    unittest.main()
