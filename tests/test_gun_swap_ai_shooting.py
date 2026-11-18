"""An aircraft's gun replaced by another (issue #23) and how AI units shoot, set in the map editor (issue #21)."""
import unittest
from unittest import mock

from wtftd import cdk, mission

NS23 = {"p": "gameData/Weapons/cannonns23.blk", "c": "gun", "t": "machine gun", "gun": 500}
TANK_GUN = {"p": "gameData/Weapons/groundModels_weapons/120mm_l44.blk", "c": "gun"}


class AircraftGunSwap(unittest.TestCase):
    def test_which_weapon_can_take_a_guns_place(self):
        self.assertTrue(cdk.gun_swap_ok(True, NS23))
        self.assertFalse(cdk.gun_swap_ok(True, TANK_GUN))  # a tank's gun on an aircraft: no
        self.assertFalse(cdk.gun_swap_ok(True, {"p": "gameData/Weapons/rockets/hvar.blk", "c": "rockets"}))
        self.assertTrue(cdk.gun_swap_ok(False, TANK_GUN))
        self.assertFalse(cdk.gun_swap_ok(False, NS23))
        self.assertFalse(cdk.gun_swap_ok(True, {}))

    def test_both_guns_of_a_pair_are_replaced(self):  # a pair of MG 151 is one group, two Weapon blocks
        mg = "gameData/Weapons/cannonMG151.blk"
        unit = {"commonWeapons": {"Weapon": [{"blk": mg}, {"blk": "gameData/Weapons/gunMG131.blk"}, {"blk": mg}]}}
        det = {"st": {"fm": "fm/x.blk"}, "am": [{"p": mg, "wi": 1, "n": 2}]}
        files = cdk.build_files("x", "air", det, {"guns": {"0": {"swap": "ns23"}}}, "", None, "custom", unit, {"ns23": NS23})[0]
        text = "".join(files.values())
        self.assertEqual(text.count('"@override:blk":t="gameData/Weapons/cannonns23.blk"'), 2)
        self.assertIn("Weapon[1]", text)
        self.assertIn("Weapon[3]", text)
        self.assertNotIn("Weapon[2]", text)  # the MG 131 stays
        # without the unit's file: the group's first, as before
        files = cdk.build_files("x", "air", det, {"guns": {"0": {"swap": "ns23"}}}, "", None, "custom", None, {"ns23": NS23})[0]
        self.assertEqual("".join(files.values()).count("cannonns23.blk"), 1)

    def test_the_new_guns_slot_carries_its_name_on_its_default_belt(self):  # the game binds a slot to a gun by its name
        from wtftd import server
        am = [{"p": "gameData/Weapons/cannonMG151.blk", "wi": 1}, {"p": "gameData/Weapons/flares.blk"}]
        groups = [{"p": am[0]["p"], "n": 2, "trig": "cannon"}, {"p": am[1]["p"], "n": 1, "trig": "countermeasures"}]
        ammo = [{"id": "mg151_stealth", "count": 400}, {"id": "", "count": 30}]
        out, gr = server.swapped_ammo(ammo, groups, am, {"0": NS23, "1": NS23})  # the launcher has no wi: left as it is
        self.assertEqual(out, [{"id": "", "count": 400}, {"id": "", "count": 30}])
        self.assertEqual([g["p"] for g in gr], [NS23["p"], am[1]["p"]])
        self.assertEqual(ammo[0]["id"], "mg151_stealth")  # the setup itself is not changed
        mission_unit = {}
        mission.write_bullets(mission_unit, out, gr)
        self.assertEqual((mission_unit["bulletsWeapon0"], mission_unit["bullets0"]), ("cannonns23", ""))

    def test_a_tank_gun_offered_to_an_aircraft_is_ignored(self):
        det = {"st": {"fm": "fm/x.blk"}, "am": [{"p": "gameData/Weapons/cannonMG151.blk", "wi": 1, "n": 1}]}
        files = cdk.build_files("x", "air", det, {"guns": {"0": {"swap": "l44"}}}, "", None, "custom", None, {"l44": TANK_GUN})[0]
        self.assertNotIn("120mm_l44", "".join(files.values()))


def tm(x=0.0):
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [x, 0.0, 0.0]]


def base():
    return {"units": {"tankModels": [{"name": "me", "tm": tm(), "unit_class": "x", "props": {"army": 1}},
                                     {"name": "t1", "tm": tm(100), "unit_class": "y", "props": {"army": 2}},
                                     {"name": "t2", "tm": tm(200), "unit_class": "y", "props": {"army": 2}}],
                      "objectGroups": {"name": "crate", "tm": tm(300), "unit_class": "z", "props": {"army": 2}}}}


def shooting(m):
    acts = m["triggers"]["wtftd_editor"]["actions"]["unitSetProperties"]
    return sorted((sorted(a.pop("object")), a) for a in mission._as_list(acts))


class AiShooting(unittest.TestCase):
    def test_values_are_checked(self):
        self.assertEqual(mission.ai_props({"accuracy": 3, "effShootingRate": -1, "targetChangeInterval": 0, "adaptiveAccuracyTime": "10",
                                           "checkVisibilityTarget": 1, "cannotShoot": True}),
                         {"accuracy": 1.0, "effShootingRate": 0.0, "targetChangeInterval": 0.5})
        self.assertEqual(mission.ai_props({"accuracy": True, "checkVisibilityTarget": False}), {"checkVisibilityTarget": False})
        self.assertEqual(mission.ai_props({"accuracy": float("nan")}), {})
        self.assertEqual(mission.ai_props("x"), {})

    def test_the_maps_setting_on_every_ai_unit_a_units_own_over_it(self):
        m = base()
        mission.apply_edits(m, "me", {"ai": {"accuracy": 0.9, "checkVisibilityTarget": True},
                                      "units": {"t2": {"ai": {"accuracy": 0.2, "adaptiveAccuracyTime": 5}}},
                                      "add": [{"block": "tankModels", "cls": "y", "x": 1, "z": 1}]})
        self.assertEqual(shooting(m), [
            (["t1", "wtftd_unit_01"], {"accuracy": 0.9, "checkVisibilityTarget": True}),  # not the player, not an asset
            (["t2"], {"accuracy": 0.2, "adaptiveAccuracyTime": 5.0, "checkVisibilityTarget": True})])
        self.assertEqual(m["triggers"]["wtftd_editor"]["events"], {"initMission": {}})

    def test_a_units_own_alone_and_an_added_ones(self):
        m = base()
        mission.apply_edits(m, "me", {"units": {"t1": {"ai": {"effShootingRate": 0.1}}},
                                      "add": [{"block": "tankModels", "cls": "y", "x": 1, "z": 1, "ai": {"accuracy": 1}}]})
        self.assertEqual(shooting(m), [(["t1"], {"effShootingRate": 0.1}), (["wtftd_unit_01"], {"accuracy": 1.0})])

    def test_nothing_set_nothing_written(self):
        m = base()
        mission.apply_edits(m, "me", {"ai": {}, "units": {"t1": {"ai": {"accuracy": None}}}})
        self.assertNotIn("triggers", m)

    def test_template_units_too_and_not_those_removed(self):
        m = base()
        with mock.patch.object(mission, "_template_names", return_value={"tpl_1", "tpl_2"}):
            mission.apply_edits(m, "me", {"ai": {"accuracy": 0.5}, "units": {"tpl_2": {"remove": True}}}, "some_scenario")
        self.assertEqual(shooting(m), [(["t1", "t2", "tpl_1"], {"accuracy": 0.5})])

    def test_a_wave_gets_it_again_on_coming_in(self):
        m = base()
        mission.apply_edits(m, "me", {"ai": {"accuracy": 0.3},
                                      "add": [{"block": "tankModels", "cls": "y", "x": 1, "z": 1, "wave": w} for w in (1, 2)]})
        held = mission._as_list(m["triggers"]["wtftd_wave_1_end"]["actions"]["unitSetProperties"])
        self.assertIn({"object": ["wtftd_unit_02"], "accuracy": 0.3}, held)


if __name__ == "__main__":
    unittest.main()
