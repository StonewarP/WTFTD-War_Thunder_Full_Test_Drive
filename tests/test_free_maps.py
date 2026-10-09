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


class TemplatePlacements(unittest.TestCase):
    """Where the scenario's scripts really put the units of the game templates it imports."""

    def test_teleports_variables_squads_and_sleepers(self):
        from unittest import mock
        start = {"is_enabled": True, "events": {"initMission": {}}, "conditions": {}}
        later = {"is_enabled": True, "events": {"periodicEvent": {"time": 1.0}}, "conditions": {}}
        mission = {"areas": {"zone_a": {"tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [100.0, 5.0, 200.0]]}},
                   "variables": {"where": "zone_a"}}
        template = {
            "variables": {"aa_zone": ""},  # set while the mission runs
            "units": {"squad": [{"name": "targets_squad", "props": {"squad_members": ["t1", "t2"]}}]},
            "triggers": {"isCategory": True,
                         "init": dict(start, actions={"unitPutToSleep": {"target": ["targets_squad"]}}),
                         "move": dict(later, actions={"unitRespawn": {"object": "tank", "target": "@where"}}),
                         "aa": dict(later, actions={"unitRespawn": {"object": "aa", "target": "@aa_zone"}})}}
        with mock.patch.object(builder, "_import_chain", return_value=[mission, template]):
            place = builder.template_placements(mission)
        self.assertEqual(place["tank"], {"area": "zone_a", "x": 100.0, "y": 5.0, "z": 200.0})
        self.assertEqual(place["aa"], {"runtime": 1})
        self.assertEqual(place["t1"], {"runtime": 1})
        self.assertEqual(place["t2"], {"runtime": 1})


class EditorEdits(unittest.TestCase):
    def test_template_unit_made_to_fire_and_zone_moved(self):
        from wtftd import mission
        m = {"units": {"armada": [{"name": "me", "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]], "props": {"army": 1}}]},
             "areas": {"zone_a": {"tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [10.0, 5.0, 20.0]]}},
             "triggers": {"isCategory": True, "is_enabled": True}}
        mission.apply_edits(m, "me", {"units": {"tpl_aa": {"attack": "fire_at_will"}, "tpl_tank": {"attack": "hold_fire"}},
                                      "areas": {"zone_a": {"x": 110.0, "z": 220.0}}})
        props = m["triggers"]["wtftd_editor"]["actions"]["unitSetProperties"]
        self.assertIn({"object": ["tpl_aa"], "attack_type": "fire_at_will", "cannotShoot": False}, props)
        self.assertIn({"object": ["tpl_tank"], "cannotShoot": True}, props)
        self.assertEqual(m["areas"]["zone_a"]["tm"][3], [110.0, 5.0, 220.0])


    def test_start_held_against_template_respawns(self):
        from wtftd import mission
        m = {"imports": {"import_record": [{"file": "x.blk"}]},
             "units": {"armada": [{"name": "me", "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]], "props": {"army": 1}}]},
             "triggers": {"isCategory": True, "is_enabled": True}}
        mission.apply_edits(m, "me", {"player": {"x": 5.0, "y": 3000.0, "z": 7.0, "yaw": 0, "mode": "air", "speed": 600}})
        self.assertEqual(m["areas"]["wtftd_start"]["tm"][3], [5.0, 3000.0, 7.0])
        acts = m["triggers"]["wtftd_start"]["actions"]
        self.assertEqual(acts["unitRespawn"]["target"], "wtftd_start")
        self.assertEqual(acts["unitSetProperties"], {"object": "me", "speed": 600.0})
        # after a crash: noted when killed, back to the start once alive again
        self.assertEqual(m["triggers"]["wtftd_start_killed"]["conditions"]["playersWhenStatus"]["players"], "isKilled")
        back = m["triggers"]["wtftd_start_back"]
        self.assertTrue(back["props"]["enableAfterComplete"])
        self.assertEqual(list(back["actions"]), ["varSetBool", "wait", "unitRespawn", "unitSetProperties"])
        bare = {"units": {"armada": [{"name": "me", "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]], "props": {}}]}}
        mission.apply_edits(bare, "me", {"player": {"x": 1.0, "y": 2.0, "z": 3.0, "yaw": 0}})
        self.assertNotIn("wtftd_start", (bare.get("triggers") or {}))  # nothing else places the player


if __name__ == "__main__":
    unittest.main()
