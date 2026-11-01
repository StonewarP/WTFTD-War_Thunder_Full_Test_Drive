"""Reference values from the real game files. Runs only where the datamine has been downloaded
(.cache/datamine, after a first build); skipped elsewhere (e.g. on GitHub)."""
import json
import unittest

from wtftd import armament as A
from wtftd import blk
from wtftd import cdk
from wtftd.builder import DM, base_stats, build_battle_words, flight_limits, launched_missile, load

W = DM / "aces.vromfs.bin_u" / "gamedata" / "weapons"
FM = DM / "aces.vromfs.bin_u" / "gamedata" / "flightmodels" / "fm"


def item(folder, stem, cat):
    d = json.loads((W / folder / f"{stem}.blkx").read_text(encoding="utf-8"))
    kind, p = A._payloads(d)[0]
    assert A._category(kind, p, folder, stem) == cat
    return A._stats(cat, A._guidance(cat, p), p, {})


@unittest.skipUnless(W.exists(), "game data not downloaded")
class ReferenceWeapons(unittest.TestCase):
    def test_r73_tracking_gate(self):
        s = item("rocketguns", "su_r_73", "aam_ir")
        self.assertEqual(s["ccmt"], "g")
        self.assertIn(s["gl"], (40, 60))  # 2.59, 2.60: the data can come from either, the game or the datamine

    def test_magic2_has_irccm(self):
        self.assertIn("ccm", item("rocketguns", "fr_r_550_magic_2", "aam_ir"))

    def test_aim9m_flare_rejection(self):
        self.assertEqual(item("rocketguns", "us_aim9m_sidewinder", "aam_ir")["ccmt"], "r")

    def test_aim54c_is_not_mach_57(self):
        self.assertLess(item("rocketguns", "us_aim_54c", "aam_radar")["v"], 1200)

    def test_s8ko(self):
        s = item("rocketguns", "su_s_8ko_rocket", "rocket")
        self.assertEqual((s["v"], s["pen"]), (650, 420))

    def test_the_s300s_missile_as_an_aircraft_carries_it(self):
        missile = launched_missile(load(W / "groundmodels_weapons" / "508mm_s300ps_5v55_rocket_launcher.blkx"))
        self.assertEqual((missile["bulletName"], missile["mass"]), ("508mm_5v55r", 1664.0))
        text = cdk._air_copy({"p": "gameData/Weapons/groundModels_weapons/508mm_s300ps_5v55_rocket_launcher.blk", "c": "sam"}, "test")
        air = blk.loads(text.split("\n", 1)[1])
        self.assertTrue(air["rocketGun"])
        self.assertEqual((air["mesh"], air["rocket"]["bulletType"], air["rocket"]["mass"]), ("s300ps_missile_5v55r", "aam", 1664.0))
        self.assertIn("radarSeeker", air["rocket"]["guidance"])
        self.assertNotIn("mesh", air["rocket"])

    def test_b61_yield(self):
        self.assertEqual(item("bombguns", "us_b61_30kt", "nuke")["yld"], 30.0)


@unittest.skipUnless(FM.exists(), "game data not downloaded")
class ReferenceLimits(unittest.TestCase):
    def test_su_30mkk(self):
        self.assertEqual(flight_limits(load(FM / "su_30mkk.blkx"), "air"),
                         {"v": 1540, "m": 2.1, "gear": 700, "flaps": [[0.2, 1018], [1, 600]], "fuel": [9400, 9400], "eng": 2, "mass": 17520, "jet": True})

    def test_j_10c(self):
        self.assertEqual(flight_limits(load(FM / "j_10c.blkx"), "air"),
                         {"v": 1543, "m": 2.1, "gear": 620, "flaps": [[0.1, 550], [1, 400]], "fuel": [5945, 6220.02], "eng": 1, "mass": 9045, "jet": True})

    def test_f_14a_variable_sweep(self):
        lim = flight_limits(load(FM / "f_14a_early.blkx"), "air")
        self.assertEqual(lim["sw"], [[0, 1021, 0.96], [0.5, 1360, 2.0], [1, 1555, 2.25]])
        self.assertEqual((lim["v"], lim["m"]), (1555, 2.25))

    def test_propellers_are_no_jets(self):
        self.assertNotIn("jet", flight_limits(load(FM / "il-10.blkx"), "air"))

    def test_a_4_has_one_engine(self):
        self.assertEqual(flight_limits(load(FM / "a_4e_early.blkx"), "air")["eng"], 1)

    def test_helicopter(self):
        lim = flight_limits(load(FM / "ah_1g.blkx"), "heli")
        self.assertEqual((lim["v"], lim["gear"], lim["eng"]), (450, 420, 1))
        self.assertNotIn("flaps", lim)

    def test_flight_model_named_after_the_aircraft(self):  # il-10 has no fmFile
        self.assertIn("lim", base_stats("il-10", {}, "air"))

    def test_fm_file_without_extension(self):
        st = base_stats("f_16a_block_10_norway", {"fmFile": "fm/f_16a_block_10_norway"}, "air")
        self.assertIn("lim", st)
        self.assertIn("mass", st)

    def test_the_battle_log_s_crash_line(self):
        words = build_battle_words()["crashed"]
        self.assertIn("hascrashed.", words)
        self.assertIn("s'est\u00e9cras\u00e9.", words)
        self.assertGreater(len(words), 10)

    def test_every_flight_model_reads(self):
        for path in FM.glob("*.blkx"):
            fm = load(path)
            if isinstance(fm, dict) and fm.get("Mass"):
                self.assertTrue(flight_limits(fm, "air"), path.stem)


if __name__ == "__main__":
    unittest.main()
