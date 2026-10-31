"""Research (RP) and purchase (SL) costs from the game's economy table."""
import unittest

from wtftd import builder


class ResearchCosts(unittest.TestCase):
    def test_costs_from_wpcost(self):
        # T-55A in wpcost.blkx (2.59): 135,000 RP, 380,000 SL
        s = builder.vehicle_stats("ground", {}, {"reqExp": 135000, "value": 380000, "reqAir": "ussr_t_54_1947"}, {}, {}, [])
        self.assertEqual((s["rp"], s["sl"]), (135000, 380000))

    def test_free_or_missing_costs_are_left_out(self):
        s = builder.vehicle_stats("ground", {}, {"reqExp": 0}, {}, {}, [])
        self.assertNotIn("rp", s)
        self.assertNotIn("sl", s)


if __name__ == "__main__":
    unittest.main()
