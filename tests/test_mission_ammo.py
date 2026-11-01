"""The player's bullet slots in a mission: belts as before, countermeasures split between flares and chaff."""
import types
import unittest
from unittest import mock

from wtftd import builder, mission, server


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


    def test_second_weapon_takes_a_free_slot(self):
        # the panel's slots are the main gun's: a missile beside the gun gets its named set, full (Gepard 1A2)
        groups = [{"n": 2, "trig": "gunner0"}, {"n": 1, "trig": "gunner1", "set": "70mm_stinger_block1_aam", "cap": 4}]
        unit = {}
        mission.write_bullets(unit, [{"id": "", "count": 640}, {"id": "35mm_HE", "count": 0}, {"id": "", "count": 0}, {"id": "", "count": 0}],
                              groups)
        self.assertEqual(slots(unit), [("", 640), ("70mm_stinger_block1_aam", 4), ("", 0), ("", 0)])

    def test_group_keys_for_a_mission(self):
        gun = {"n": 1, "trig": "gunner0", "cap": 640, "opts": [{"id": ""}, {"id": "35mm_HE"}]}
        missile = {"n": 1, "trig": "gunner1", "cap": 4, "opts": [{"id": "not_here", "x": 1}, {"id": "70mm_stinger_block1_aam"}]}
        self.assertEqual(server._ammo_groups({"b": "tankModels", "am": [gun, missile]}),
                         [{"n": 1, "trig": "gunner0", "cap": 640, "set": ""},
                          {"n": 1, "trig": "gunner1", "cap": 4, "set": "70mm_stinger_block1_aam"}])
        self.assertNotIn("set", server._ammo_groups({"b": "armada", "am": [gun]})[0])


MISSILE = {"bullet": {"bulletType": "sam_tank"}, "notUseDefaultBulletInGui": True, "aster_aam": {"bullet": {"bulletName": "x"}},
           "aster_aam_ammo_pack": {"bullet": {"bulletName": "x"}}}
GUN = {"bullet": {"bulletType": "ap_t"}, "notUseDefaultBulletInGui": True, "gun_he": {"bullet": {"bulletName": "x"}}}
LAUNCHER = "gameData/Weapons/groundModels_weapons/380mm_aster_30_user_cannon.blk"


class FakeWeapons:
    """Just what vehicle_ammo reads of the weapon files."""
    lang = types.SimpleNamespace(put=lambda *a, **k: None)
    files = {LAUNCHER: MISSILE, "gun.blk": GUN}

    def get(self, blk):
        return self.files.get(blk)

    def weapon_name(self, blk):
        return blk.rsplit("/", 1)[-1][:-4]

    def bullet_sets(self, blk):
        d = self.files.get(blk) or {}
        sets = {k: {"b": [k]} for k, v in d.items() if isinstance(v, dict) and k != "bullet"}
        return ({"b": ["default"], "t": [d["bullet"]["bulletType"]]} if d else None), sets


def ammo(unit, mods=("aster_aam", "gun_he")):
    return builder.vehicle_ammo(unit, "ground", set(mods), FakeWeapons())


class GroundAmmo(unittest.TestCase):
    def test_missiles_only_have_their_named_set(self):
        # as the game's own missions: bullets0="127mm_MIM72A_aam" (tank_sam_ir_caged_tft), never the default set
        dummy = {"dummy": True, "trigger": "gunner0", "blk": "gameData/Weapons/dummy_weapon.blk", "bullets": 1}
        unit = {"commonWeapons": {"Weapon": [dummy, {"trigger": "gunner1", "blk": LAUNCHER, "bullets": 8}]}}
        self.assertEqual([o["id"] for o in ammo(unit)[0]["opts"]], ["aster_aam"])

    def test_default_set_stays_for_guns_and_without_a_named_set(self):
        unit = {"commonWeapons": {"Weapon": {"trigger": "gunner0", "blk": "gun.blk", "bullets": 40}}}
        self.assertEqual([o["id"] for o in ammo(unit)[0]["opts"]], ["", "gun_he"])
        unit = {"commonWeapons": {"Weapon": {"trigger": "gunner0", "blk": LAUNCHER, "bullets": 8}}}
        self.assertEqual([o["id"] for o in ammo(unit, mods=())[0]["opts"]], ["", "aster_aam"])

    def test_battery_radar_holds_its_launchers_missiles(self):
        # FSAF SAMP/T: 2 launchers of 8 Aster-30, 16 on the radar (wpcost: ammoCount 16)
        radar = {"supportPlanes": {"plane": [{"class": "tankModels/fr_samp_t_launcher", "isSlave": True, "count": 1}] * 2}}
        launcher = {"commonWeapons": {"Weapon": [{"dummy": True, "blk": "gun.blk"}, {"trigger": "gunner1", "blk": LAUNCHER, "bullets": 8}]}}
        with mock.patch.object(builder, "load", return_value=launcher) as load:
            groups = ammo(radar)
        self.assertIn("fr_samp_t_launcher", str(load.call_args[0][0]))
        self.assertEqual([(g["cap"], [o["id"] for o in g["opts"]]) for g in groups], [(16, ["aster_aam"])])
        self.assertNotIn("wi", groups[0])  # the radar has no such Weapon block for a custom vehicle to change

    def test_support_plane_that_is_not_a_launcher(self):
        with mock.patch.object(builder, "load") as load:
            self.assertEqual(ammo({"supportPlanes": {"plane": {"class": "tankModels/drone", "count": 1}}}), [])
        load.assert_not_called()

    def test_pilon_missiles(self):
        # Pantsir-SM: no missile in commonWeapons, one preset per missile in WeaponPilons
        unit = {"commonWeapons": {"Weapon": {"trigger": "gunner0", "blk": "gun.blk", "bullets": 351}},
                "WeaponPilons": {"WeaponSlot": [{"index": 0, "WeaponPreset": {"name": "aster_aam", "Weapon": {
                    "trigger": "gunner1", "blk": LAUNCHER, "bullets": 12}}}]}}
        self.assertEqual([(g["trig"], g["cap"], g["opts"][0]["id"]) for g in ammo(unit)],
                         [("gunner0", 351, ""), ("gunner1", 12, "aster_aam")])


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
