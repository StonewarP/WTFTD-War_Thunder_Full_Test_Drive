"""Kinetic penetration, battle map layouts, in-mission keys and custom sights."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wtftd import builder, mission, sights


def demarre(bt, mass, cal, speed, k=1.0, expl=None):
    b = {"bulletType": bt, "mass": mass, "caliber": cal, "speed": speed,
         "damage": {"kinetic": {"demarrePenetrationK": k, "demarreSpeedPow": 1.43, "demarreMassPow": 0.71,
                                "demarreCaliberPow": 1.07}}}
    if expl:
        b["explosiveMass"] = expl
    return b


class KineticPenetration(unittest.TestCase):
    def test_table_wins(self):
        b = {"bulletType": "apds_fs_tungsten_caliber_fins_tank", "speed": 1700.0, "mass": 4.85,
             "armorpower": {"ArmorPower0m": [457.0, 10.0], "ArmorPower1000m": [431.0, 1000.0]}}
        self.assertEqual(builder.kinetic_pen(b), 457)

    def test_demarre_full_calibre(self):
        # 76 mm M62 APCBC (792 m/s, 7 kg, 0.93 % filler): ~150 mm at the muzzle
        self.assertAlmostEqual(builder.kinetic_pen(demarre("apcbc_tank", 7.0, 0.0762, 792.0, expl=0.065)), 149, delta=2)
        # an uncapped AP shell (coefficient 0.9 in its file) gets less
        self.assertLess(builder.kinetic_pen(demarre("ap_tank", 7.0, 0.0762, 792.0, k=0.9)),
                        builder.kinetic_pen(demarre("apcbc_tank", 7.0, 0.0762, 792.0)))

    def test_filler_lowers_penetration(self):
        plain = builder.kinetic_pen(demarre("aphe_tank", 10.0, 0.088, 800.0))
        filled = builder.kinetic_pen(demarre("aphe_tank", 10.0, 0.088, 800.0, expl=0.3))  # 3 %
        self.assertLess(filled, plain)

    def test_lanz_odermatt_rod(self):
        # 105 mm DM63 (tungsten, 535 mm working length, 24 mm rod, 1455 m/s): ~430 mm
        b = {"bulletType": "apds_fs_long_l30_tank", "mass": 4.4, "caliber": 0.105, "damageCaliber": 0.024, "speed": 1455.0,
             "damage": {"kinetic": {"lanzOdermattMaterial": "tungsten", "lanzOdermattWorkingLength": 535.0,
                                    "lanzOdermattDensity": 17500.0}}}
        self.assertAlmostEqual(builder.kinetic_pen(b), 430, delta=10)

    def test_not_kinetic_or_unknown(self):
        self.assertIsNone(builder.kinetic_pen(demarre("he_frag_tank", 40.0, 0.15, 500.0, k=0.15)))
        apcr = demarre("apcr_tank", 4.24, 0.0762, 1036.0, k=0.65)
        apcr["damageCaliber"] = 0.0381
        self.assertIsNone(builder.kinetic_pen(apcr))  # a core's caliber without its mass

    def test_shell_stats_carry_it(self):
        self.assertIn("k", builder.shell_stats(demarre("apcbc_tank", 7.0, 0.0762, 792.0)))

    def test_table_by_distance(self):
        # the Hispano 20 mm table, as in the game files: nearest first, in whole metres and millimetres
        rows = {"ArmorPower1000m": [7.0, 1000.0], "ArmorPower0m": [17.0, 10.0], "ArmorPower500m": [11.0, 500.0]}
        s = builder.shell_stats({"bulletType": "ap_i", "armorpower": rows})
        self.assertEqual(s["pc"], [[10, 17], [500, 11], [1000, 7]])
        self.assertEqual(s["k"], 17)

    def test_no_table_by_distance(self):
        he = {"bulletType": "rocket_tank", "armorpower": {"a": [28.0, 10.0], "b": [20.0, 500.0]}}
        self.assertNotIn("pc", builder.shell_stats(he))  # not armor-piercing: no curve to draw


def shell(bt, speed, mass, cal, cx, core=None, core_cal=None, ballistic=None, expl=None, k=1.0, sp=1.43, mp=0.71):
    b = demarre(bt, mass, cal, speed, k, expl)
    b["damage"]["kinetic"].update(demarreSpeedPow=sp, demarreMassPow=mp)
    if cx:
        b["Cx"] = cx
    if core:
        b.update(damageMass=core, damageCaliber=core_cal, ballisticCaliber=ballistic)
    return b


M829A2 = {"bulletType": "apds_fs_long_l30_tank", "speed": 1680.0, "mass": 4.921, "caliber": 0.12, "ballisticCaliber": 0.022,
          "damageCaliber": 0.022, "Cx": 0.76874, "damage": {"kinetic": {
              "lanzOdermattMaterial": "depletedUranium", "lanzOdermattWorkingLength": 680.0, "lanzOdermattDensity": 18600.0}}}


class PenetrationByDistance(unittest.TestCase):
    """The game's own figures at 10, 100, 500, 1000, 1500 and 2000 m (official wiki), from the shells' files."""

    def check(self, b, game):
        s = builder.shell_stats(b)
        for ours, theirs in zip([p for d, p in s["pc"] if d <= 2000], game, strict=True):
            self.assertAlmostEqual(ours, theirs, delta=1)
        self.assertEqual((s["k"], s["pe"]), (game[0], 1))

    def test_full_calibre(self):
        self.check(shell("apcbc_tank", 773.0, 10.2, 0.088, 0.33, expl=0.064), [165, 162, 151, 139, 127, 117])  # PzGr 39
        self.check(shell("apcbc_tank", 800.0, 25.0, 0.122, 0.35, expl=0.125), [230, 227, 215, 200, 186, 173])  # BR-471D

    def test_no_drag_value_in_the_shell_s_file(self):
        self.check(shell("ap_tank", 792.0, 6.8, 0.0762, None, k=0.9), [134, 132, 121, 109, 99, 89])  # M79

    def test_long_rod_on_its_own_caliber(self):
        self.check(M829A2, [629, 628, 621, 613, 605, 597])

    def test_core_of_any_share(self):
        self.check(shell("apcr_tank", 1036.0, 4.24, 0.0762, 0.28, 1.79, 0.0381, 0.0762, k=0.65),
                   [191, 186, 168, 147, 129, 113])  # M93, 42 % core
        self.check(shell("apcr_tank", 1180.0, 0.9, 0.05, 0.47, 0.335, 0.021, 0.05, k=0.65), [137, 126, 88, 56, 36, 23])  # PzGr 40
        self.check(shell("apcr_tank", 1050.0, 4.99, 0.085, 0.4779, 0.648, 0.028, 0.085, k=0.65),
                   [195, 187, 154, 122, 96, 76])  # BR-365P, 13 % core
        self.check(shell("apds_tank", 1478.3, 4.0, 0.105, 0.15718, 2.7, 0.06, 0.06, k=1.12, sp=1.47, mp=0.74),
                   [350, 347, 333, 317, 302, 287])  # L28A1

    def test_steel_rods(self):
        rod = {"bulletType": "apds_fs_full_body_steel_tank", "mass": 4.0, "caliber": 0.115, "ballisticCaliber": 0.042,
               "damageCaliber": 0.042, "Cx": 0.395, "speed": 1615.0, "damage": {"kinetic": {
                   "lanzOdermattMaterial": "steel", "lanzOdermattWorkingLength": 456.0, "lanzOdermattDensity": 7760.0,
                   "lanzOdermattBrinellHardnessNumber": 500.0}}}
        self.check(rod, [284, 280, 264, 244, 223, 203])  # 3BM4

    def test_explosive_shells_pierce_the_better_of_speed_and_blast(self):
        blast = {"tnt": {"a_ix_2": 1.54}, "pen": [[0.2, 5.0], [2.0, 25.0], [3.0, 35.0], [5.0, 40.0], [6.0, 50.0]]}
        sprgr = shell("he_frag_tank", 820.0, 9.0, 0.088, None, expl=0.9, k=0.15)  # Sprgr L/4.5: its speed, then its blast
        for ours, game in zip([p for d, p in builder.shell_stats(sprgr, blast)["pc"] if d <= 2000], [18, 18, 17, 15, 14, 13], strict=True):
            self.assertAlmostEqual(ours, game, delta=1)
        s = builder.shell_stats({"bulletType": "he_frag_fs_tank", "explosiveMass": 3.402, "explosiveType": "a_ix_2"}, blast)
        self.assertEqual({p for d, p in s["pc"]}, {42})  # 3OF26: the same at any distance
        self.assertNotIn("k", s)  # not an armor-piercing value: Best AP penetration stays what it says
        missile = {"bulletType": "sam_tank", "rocket": {"explosiveMass": 3.402, "explosiveType": "a_ix_2"}}
        self.assertEqual(builder.pen_curve(missile, blast)[0][0], [10, 42])

    def test_fragments_set_the_floor_of_a_small_shell(self):
        blast = {"tnt": {"petn": 1.66}, "pen": [[0.005, 2.0], [0.1, 4.0]],
                 "frag": [(0.02, [[0.01, 3.0]]), (0.07, [[0.01, 4.0]]), (0.18, [[0.01, 1.5]])]}
        aphe = shell("aphe", 720.0, 0.117, 0.02, None, expl=0.00459, k=0.9)  # MG 151's: 4 % explosive, 7.6 g of TNT
        aphe["explosiveType"] = "petn"
        self.assertEqual(builder.pen_curve(aphe, blast)[0][-1], [4000, 4])
        aphe["explosiveMass"] = 0.0023  # under the blast table's first point: no fragments
        self.assertLess(builder.pen_curve(aphe, blast)[0][-1][1], 3)

    def test_shaped_charges_and_missiles_don_t_care_for_distance(self):
        s = builder.shell_stats({"bulletType": "heat_fs_tank", "cumulativeDamage": {"armorPower": 550.0}})
        self.assertEqual(s["pc"], [[10, 550], [4000, 550]])
        self.assertNotIn("pe", s)
        self.assertEqual(builder.pen_curve({"bulletType": "atgm_tandem_tank", "rocket": {"cumulativeDamage": {"armorPower": 700.0}}})[0],
                         [[10, 700], [4000, 700]])

    def test_a_kinetic_missile_speeds_up_first(self):
        rocket = {"guiArmorpower": {"a": [70.0, 59.0, 40.0, 10.0], "b": [775.0, 654.0, 448.0, 1000.0]},  # MGM-166 LOSAT
                  "armorpower": {"c": [775.0, 1000.0], "d": [675.0, 2000.0]}}
        rows, computed = builder.pen_curve({"bulletType": "atgm_ke_tank", "rocket": rocket})
        self.assertEqual(rows, [[10, 70], [1000, 775], [2000, 675]])
        self.assertFalse(computed)

    def test_what_pierces_nothing(self):
        self.assertEqual(builder.pen_curve({"bulletType": "smoke_tank", "explosiveMass": 1.0, "speed": 500.0, "mass": 5.0, "caliber": 0.1}),
                         ([], False))

    def test_a_table_stays_the_game_s_own(self):
        b = {"bulletType": "apds_fs_tungsten_caliber_fins_tank", "speed": 1700.0, "mass": 4.85, "Cx": 0.5, "caliber": 0.125,
             "armorpower": {"a": [457.0, 10.0], "b": [431.0, 1000.0]}}
        s = builder.shell_stats(b)
        self.assertEqual(s["pc"], [[10, 457], [1000, 431]])
        self.assertNotIn("pe", s)


def area(x, z, s=10.0):
    return {"type": "Sphere", "tm": [[s, 0.0, 0.0], [0.0, s, 0.0], [0.0, 0.0, s], [x, 0.0, z]]}


class BattleLayout(unittest.TestCase):
    def test_briefing_markers_first(self):
        d = {"areas": {
            "briefing_dom_t1_spawn_01": area(0, 0), "briefing_dom_t2_spawn_01": area(1000, 0),
            "t1_spawn_01_hardcore": area(-500, 0), "t1_air_spawn": area(0, 9000),
            "dom_capture_area_02_arcade": area(500, 100), "dom_capture_area_01_arcade": area(500, -100),
            "dom_capture_area_01_hardcore": area(9, 9), "briefing_battlearea": {"type": "Box", "tm": area(500, 0, 600)["tm"]},
        }}
        lay = builder.battle_layout(d)
        self.assertEqual(lay["spawn"][1][0], 0.0)
        self.assertEqual(lay["spawn"][2][0], 1000.0)
        self.assertEqual([(k, a["tm"][3][2]) for k, a in lay["zones"]], [("A", -100.0), ("B", 100.0)])
        self.assertIsNotNone(lay["area"])

    def test_team_ab_names_and_missing_side(self):
        d = {"areas": {"teamA_spawn_01": area(0, 0), "teamB_spawn_01": area(10, 0), "capturezone_01": area(5, 5)}}
        self.assertEqual(sorted(builder.battle_layout(d)["spawn"]), [1, 2])
        self.assertIsNone(builder.battle_layout({"areas": {"t1_spawn": area(0, 0), "capture_01": area(1, 1)}}))

    def test_zone_labels(self):
        m = {"areas": {"wtftd_capture_B": area(0, 0), "wtftd_enemy_spawn": area(5, 5), "zone": area(1, 1)}}
        zones = {z["name"]: z for z in mission.scenario_zones("x", m)}
        self.assertEqual(zones["wtftd_capture_B"]["label"], "B")
        self.assertEqual(zones["wtftd_enemy_spawn"]["label"], "@editor.enemySpawn")
        self.assertNotIn("label", zones["zone"])


def bare_mission():
    m = builder._hangar_mission("avg_poland", "tankModels", [0.0, 0.0, 0.0], "t")
    m["units"]["tankModels"] = [m["units"]["tankModels"], {"name": "target", "props": {"army": 2}}]
    return m


class InMissionKeys(unittest.TestCase):
    def test_toggles_and_actions(self):
        m = bare_mission()
        ch = {"hotkeys": True, "immortal": True}
        mission.apply_cheats(m, "t1_player01", ch)
        mission.apply_hotkeys(m, "t1_player01", ch, False, {"on": "{what} ON", "immortal": "Invincible"}, m["units"]["tankModels"][0]["tm"])
        tr = m["triggers"]
        # immortality is no longer applied unconditionally: the key can switch it off
        self.assertNotIn("wtftd_rules_fast", tr)
        self.assertEqual(tr["wtftd_key_immortal"]["conditions"]["playerShortcutPressed"]["control"], "ID_FAST_VOICE_MESSAGE_1")
        sw = tr["wtftd_key_immortal_switch"]
        self.assertFalse(sw["is_enabled"])
        self.assertEqual(sw["actions"]["playHint"]["name"], "Invincible ON")
        self.assertFalse(sw["else_actions"]["unitSetProperties"]["isImmortal"])
        self.assertTrue(m["variables"]["wtftd_hk_immortal"])
        self.assertEqual(tr["wtftd_key_passive"]["conditions"]["playerShortcutPressed"]["control"], "ID_FAST_VOICE_MESSAGE_3")
        self.assertEqual(tr["wtftd_key_targets"]["actions"]["unitRestore"]["target"], ["target"])
        self.assertEqual(tr["wtftd_key_start"]["actions"]["unitRespawn"]["target"], "wtftd_key_start")
        self.assertIn("wtftd_key_start", m["areas"])

    def test_off_by_default_and_targets_back(self):
        m = bare_mission()
        mission.apply_hotkeys(m, "t1_player01", {"targetsBack": True}, False, None, None)
        self.assertEqual([k for k in m["triggers"] if k.startswith("wtftd_")], ["wtftd_respawn", "wtftd_targets_back"])

    def test_texts_are_cleaned(self):
        m = bare_mission()
        mission.apply_hotkeys(m, "t1_player01", {"hotkeys": True}, False, {"help": 'a "quoted"\nhelp'}, None)
        self.assertEqual(m["triggers"]["wtftd_key_help"]["actions"]["playHint"]["name"], "a 'quoted' help")


class CustomSights(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        saves = self.tmp / "Documents" / "My Games" / "WarThunder" / "Saves"
        (saves / "last").mkdir(parents=True)
        (saves / "last" / "lastUid").write_text("123", encoding="utf-8")
        (saves / "123" / "production" / "UserSights" / "all_tanks").mkdir(parents=True)
        (saves / "123" / "production" / "UserSights" / "all_tanks" / "mine.blk").write_text("crosshair_distances{}", encoding="utf-8")
        self.us = saves / "123" / "production" / "UserSights"
        self.user = self.tmp / "user"
        self.patch = mock.patch.object(sights, "_saves_roots", lambda: [saves])
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_list_install_cleanup(self):
        listed = sights.list_sights(self.user)
        self.assertEqual([s["id"] for s in listed["sights"]], ["game/all_tanks/mine.blk"])
        done = sights.install(self.user, "game/all_tanks/mine.blk", ["us_m2a4", "germ_tiger", "../evil"])
        self.assertEqual(done, ["us_m2a4", "germ_tiger"])
        self.assertTrue((self.us / "us_m2a4" / "wtftd.blk").is_file())
        # WTFTD's copies are not offered as sights
        self.assertEqual(len(sights.list_sights(self.user)["sights"]), 1)
        self.assertEqual(sights.cleanup(self.user), 2)
        self.assertFalse((self.us / "us_m2a4").exists())
        self.assertTrue((self.us / "all_tanks" / "mine.blk").is_file())

    def test_import_and_bad_ids(self):
        sid = sights.import_sight(self.user, "../My Sight.blk", "crosshair_distances{}")
        self.assertEqual(sid, "lib/My Sight.blk")
        self.assertIn(sid, [s["id"] for s in sights.list_sights(self.user)["sights"]])
        with self.assertRaises(sights.SightError):
            sights.import_sight(self.user, "x.blk", "not a sight")
        for bad in ("game/../x.blk", "lib/../../x.blk", "other/x.blk"):
            with self.assertRaises(sights.SightError):
                sights.install(self.user, bad, ["us_m2a4"])


if __name__ == "__main__":
    unittest.main()
