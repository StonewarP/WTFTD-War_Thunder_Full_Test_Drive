"""The game's other maps: a bare scenario (the player alone) facing the way the game's own unit did."""
import unittest

from wtftd import builder


class FreeMaps(unittest.TestCase):
    def test_start_heading_is_levelled(self):
        # a unit facing +z, slightly nose-up: the start keeps the heading, not the pitch
        rot = builder._unit_rot([[0.0, 0.2, 0.98], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [10.0, 5.0, 20.0]])
        self.assertEqual(rot[1], [0.0, 1.0, 0.0])
        self.assertAlmostEqual(rot[0][2], 1.0)
        self.assertAlmostEqual(rot[0][1], 0.0)
        self.assertIsNone(builder._unit_rot(None))

    def test_bare_mission(self):
        m = builder._hangar_mission("avg_ireland", "tankModels", [1.0, 2.0, 3.0], "WTFTD", [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
        self.assertEqual(m["mission_settings"]["mission"]["level"], "levels/avg_ireland.bin")
        unit = m["units"]["tankModels"]
        self.assertEqual(unit["tm"], [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [1.0, 2.0, 3.0]])
        self.assertEqual(list(m["units"]), ["tankModels"])  # the player alone
        air = builder._hangar_mission("air_africa_desert", "armada", [0.0, 1500.0, 0.0], "WTFTD", speed=450.0)
        self.assertEqual(air["units"]["armada"]["props"]["speed"], 450.0)


if __name__ == "__main__":
    unittest.main()
