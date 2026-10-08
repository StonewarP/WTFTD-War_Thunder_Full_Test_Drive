"""Reference values from the real game files. Runs only where the datamine has been downloaded
(.cache/datamine, after a first build); skipped elsewhere (e.g. on GitHub)."""
import json
import unittest

from wtftd import armament as A
from wtftd.builder import DM

W = DM / "aces.vromfs.bin_u" / "gamedata" / "weapons"


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
        self.assertEqual(s["gl"], 40)

    def test_magic2_has_irccm(self):
        self.assertIn("ccm", item("rocketguns", "fr_r_550_magic_2", "aam_ir"))

    def test_aim9m_flare_rejection(self):
        self.assertEqual(item("rocketguns", "us_aim9m_sidewinder", "aam_ir")["ccmt"], "r")

    def test_aim54c_is_not_mach_57(self):
        self.assertLess(item("rocketguns", "us_aim_54c", "aam_radar")["v"], 1200)

    def test_s8ko(self):
        s = item("rocketguns", "su_s_8ko_rocket", "rocket")
        self.assertEqual((s["v"], s["pen"]), (650, 420))

    def test_b61_yield(self):
        self.assertEqual(item("bombguns", "us_b61_30kt", "nuke")["yld"], 30.0)


if __name__ == "__main__":
    unittest.main()
