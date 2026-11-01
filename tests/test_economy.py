"""What a vehicle costs and earns, on made-up records built like wpcost.blkx. The expected numbers come from the official wiki's pages
(2.59.0.92): they are the game's own cards, the raw fields aren't."""
import unittest

from wtftd import builder, patches

WARPOINTS = {"avgRepairMul": 1.0, "freeRepairs": 10, "rewardMulVisual": {"rewardMulVisualArcade": 1.0, "rewardMulVisualHistorical": 1.0,
                                                                         "rewardMulVisualSimulation": 1.0, "premRewardMulVisualPart": 0.5}}
RANKS = {"goldPlaneExpMul": 2.0}


def record(arcade=1.0, historical=1.0, simulation=1.0, repair=(1000, 1000, 1000), exp=1.0, **extra) -> dict:
    return {"rewardMulArcade": arcade, "rewardMulHistorical": historical, "rewardMulSimulation": simulation, "expMul": exp,
            "repairCostArcade": repair[0], "repairCostHistorical": repair[1], "repairCostSimulation": repair[2], **extra}


def economy(wp: dict, cat="ground") -> tuple:
    return builder.vehicle_economy(cat, wp, WARPOINTS, RANKS)


class Rewards(unittest.TestCase):
    def test_tree_vehicle(self):  # Tiger H1
        s = economy(record(0.84, 1.27, 1.4, exp=1.48))[0]
        self.assertEqual((s["slm"], s["rpm"]), ([80, 130, 140], 148))

    def test_multipliers_on_the_rounding_edge_round_like_the_game(self):
        for raw, shown in ((1.45, 150), (4.95, 490), (0.95, 100), (3.05, 310), (2.35, 230)):  # P-51D-5, MiG-29, JAS39D, Su-22M3, Merkava
            self.assertEqual(economy(record(raw))[0]["slm"][0], shown, raw)

    def test_a_premium_vehicle_counts_twice_its_finer_rounded_half(self):  # KV-122: 2 x (120 / 185 / 200) % SL, 2 x 172 % RP
        s = economy(record(2.4, 3.7, 4.0, exp=1.72, costGold=1000, freeRepairs=30))[0]
        self.assertEqual((s["slm"], s["rpm"], s["fr"]), ([240, 370, 400], 344, 30))

    def test_a_squadron_vehicle_is_not_premium(self):  # Oplot-T: 150 / 190 / 200, 250 %, opened with gold but bought in no gold
        s = economy(record(1.5, 1.88, 2.0, exp=2.5, researchType="clanVehicle", openCostGold=500))[0]
        self.assertEqual((s["slm"], s["rpm"], s["fr"]), ([150, 190, 200], 250, 10))


class Repairs(unittest.TestCase):
    def test_all_upgrades_add_what_the_modules_say(self):  # Tiger H1: 1,506 -> 1,955, not the 1,956 of repairCostFullUpgradedArcade
        mods = {"a": {"repairCostCoef": 0.2}, "b": {"repairCostCoef": 0.098}, "c": {"tier": 1}}
        full, stock = economy(record(repair=(1506, 1635, 2265), repairCostFullUpgradedArcade=1956, modifications=mods))
        self.assertEqual((full["rep"], stock["rep"]), ([1955, 2122, 2940], [1506, 1635, 2265]))

    def test_without_modules_there_is_no_stock_value(self):  # a premium vehicle: all modifications unlocked
        full, stock = economy(record(repair=(2437, 2587, 3599), costGold=1000, modifications={"a": {"tier": 1}}))
        self.assertEqual((full["rep"], stock), ([2437, 2587, 3599], {}))

    def test_a_ship_has_no_sb(self):
        s = economy(record(repair=(3327, 4344, 0), repairCostSimulation=0), "boat")[0]
        self.assertEqual((s["rep"], s["slm"][2]), ([3327, 4344, None], None))

    def test_a_reserve_vehicle_repairs_for_free(self):
        s, stock = economy(record(repair=(0, 0, 0)))
        self.assertEqual((s["rep"], stock), ([0, 0, 0], {}))
        self.assertNotIn("fr", s)  # free every time: no count

    def test_free_repairs(self):
        self.assertEqual(economy(record())[0]["fr"], 10)  # the game's default, from warpoints.blkx
        self.assertEqual(economy(record(freeRepairs=30))[0]["fr"], 30)


class Others(unittest.TestCase):
    def test_a_unit_outside_the_shop_has_no_economy(self):
        self.assertEqual(economy({}), ({}, {}))

    def test_old_tables_without_the_rates(self):
        s = builder.vehicle_economy("ground", record(0.84, exp=1.48, costGold=1), {}, {})[0]
        self.assertEqual(s["slm"][0], 80)  # the game's defaults: half for a premium, times 2
        self.assertEqual(s["rpm"], 148)

    def test_what_changed_sees_the_economy(self):
        def db(version, rep, slm, rpm):
            return {"meta": {"version": version, "schema": 33}, "vehicles": [{"id": "tank", "s": {"rep": rep, "slm": slm, "rpm": rpm, "fr": 10}}], "details": {},
                    "armament": {}, "scenarios": [], "names": {}}
        rows = patches.compare(db("2.59.0.92", [1506, 1635, 2265], [80, 130, 140], 148), db("2.60.0.1", [1506, 1700, 2265], [80, 130, 150], 148))["rows"]
        self.assertEqual(rows, [["tank", "reprb", 1635, 1700], ["tank", "slsb", 140, 150]])
        self.assertEqual({patches.GROUP_OF[r[1]] for r in rows}, {"cost"})


if __name__ == "__main__":
    unittest.main()
