"""The player's bullet slots in a mission: belts as before, countermeasures split between flares and chaff."""
import unittest

from wtftd import mission


def slots(unit):
    return [(unit[f"bullets{i}"], unit[f"bulletsCount{i}"]) for i in range(4)]


class BulletSlots(unittest.TestCase):
    def test_belts_and_shells_unchanged(self):
        unit = {}
        mission.write_bullets(unit, [{"id": "M60_air_targets", "count": 676}, {"id": "", "count": 60}])
        self.assertEqual(slots(unit), [("M60_air_targets", 676), ("", 60), ("", 0), ("", 0)])

    def test_mixed_countermeasures_add_the_chaff_slot(self):
        unit = {}
        mission.write_bullets(unit, [{"id": "", "count": 676},
                                     {"id": "", "count": 40, "chaff": {"id": "countermeasures_launcher_chaff", "count": 20}}])
        self.assertEqual(slots(unit), [("", 676), ("", 40), ("countermeasures_launcher_chaff", 20), ("", 0)])

    def test_aircraft_slots_tagged_with_their_weapon(self):
        # as the game spawns aircraft (respawn.nut): sets one after the other, bulletsWeapon<i> = weapon name
        gun = {"p": "gameData/Weapons/cannonGSh_301.blk", "n": 1, "trig": "cannon"}
        cm = {"p": "gameData/Weapons/rocketGuns/countermeasure_split_launcher_jet.blk", "n": 2, "trig": "countermeasures"}
        unit = {}
        mission.write_bullets(unit, [{"id": "GSh_301_stealth", "count": 150},
                                     {"id": "", "count": 20, "chaff": {"id": "countermeasures_launcher_chaff", "count": 40}}],
                              [gun, cm])
        tagged = [(unit[f"bullets{i}"], unit[f"bulletsCount{i}"], unit[f"bulletsWeapon{i}"]) for i in range(6)]
        self.assertEqual(tagged, [("GSh_301_stealth", 150, "cannonGSh_301"),
                                  ("", 10, "countermeasure_split_launcher_jet"),  # per launcher
                                  ("countermeasures_launcher_chaff", 20, "countermeasure_split_launcher_jet"),
                                  ("", 0, ""), ("", 0, ""), ("", 0, "")])
        # all chaff on 4 launchers: one set, per-launcher count; no flare set
        unit = {}
        mission.write_bullets(unit, [{"id": "", "count": 250}, {"id": "countermeasures_launcher_chaff", "count": 256}],
                              [dict(gun, p="gameData/Weapons/cannonGSh_30_2.blk"), dict(cm, n=4)])
        self.assertEqual((unit["bullets1"], unit["bulletsCount1"], unit["bulletsWeapon1"]),
                         ("countermeasures_launcher_chaff", 64, "countermeasure_split_launcher_jet"))
        self.assertEqual(unit["bulletsWeapon2"], "")
        # all chaff given as a mix with no flares: the flare set is left out
        unit = {}
        mission.write_bullets(unit, [{"id": "", "count": 0, "chaff": {"id": "countermeasures_launcher_chaff", "count": 60}}],
                              [dict(cm, n=1)])
        self.assertEqual((unit["bullets0"], unit["bulletsCount0"]), ("countermeasures_launcher_chaff", 60))

    def test_no_free_slot_or_bad_id(self):
        unit = {}
        full = [{"id": "", "count": 1}] * 3 + [{"id": "", "count": 5, "chaff": {"id": "x", "count": 5}}]
        mission.write_bullets(unit, full)
        self.assertEqual(slots(unit)[3], ("", 5))
        unit = {}
        mission.write_bullets(unit, [{"id": "", "count": 5, "chaff": {"id": 'a" b', "count": 5}}])
        self.assertEqual(slots(unit)[1], ("", 0))


class Cheats(unittest.TestCase):
    def rules(self, air):
        m = {"mission_settings": {"mission": {}}, "units": {}, "triggers": {"isCategory": True, "is_enabled": True}}
        mission.apply_cheats(m, "armada_01", {"immortal": True}, air=air)
        return m["triggers"]["wtftd_rules_fast"]["actions"]

    def test_immortal_aircraft_without_the_repair_loop(self):
        # the full repair every second restarts aircraft engines (MiG-29SMT could not take off)
        fast = self.rules(air=True)
        self.assertNotIn("unitRestore", fast)
        self.assertTrue(fast["unitSetProperties"]["isImmortal"])
        self.assertTrue(self.rules(air=False)["unitRestore"]["fullRestore"])


    def test_targets_shoot(self):
        def unit(name, army, attack):
            return {"name": name, "props": {"army": army, "attack_type": attack}}
        m = {"units": {"tankModels": [unit("aa", 2, "hold_fire"), unit("set_in_editor", 2, "hold_fire"),
                                      unit("ally", 1, "hold_fire"), unit("tank", 2, "return_fire")]}}
        changed = mission.make_hostile(m, {"units": {"set_in_editor": {"attack": "hold_fire"}}})
        self.assertEqual(changed, ["aa"])
        self.assertEqual([u["props"]["attack_type"] for u in m["units"]["tankModels"]],
                         ["fire_at_will", "hold_fire", "hold_fire", "return_fire"])


if __name__ == "__main__":
    unittest.main()
