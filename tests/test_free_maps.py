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
        self.assertEqual({"object": ["tpl_tank"], "cannotShoot": True}, props)
        # made to attack: held every 3 s (the templates' scripts set their targets passive when they respawn them)
        attack = m["triggers"]["wtftd_attack"]
        self.assertEqual(attack["actions"]["unitSetProperties"], {"object": ["tpl_aa"], "attack_type": "fire_at_will", "cannotShoot": False})
        self.assertEqual(attack["events"], {"periodicEvent": {"time": 3.0}})
        self.assertTrue(attack["props"]["enableAfterComplete"])
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


    def test_test_flight_air_start_moves_the_scenarios_own_zone(self):
        from wtftd import mission
        ident = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        m = {"imports": {"import_record": [{"file": "test_flight_template.blk"}]},
             "mission_settings": {"mission": {"air_spawn_point": 1, "is_airfield_spawn": True, "is_ship_spawn": False}},
             "units": {"armada": [{"name": "me", "tm": [*ident, [0, 0, 0]], "props": {"army": 1}}]},
             "areas": {"spawn_area01": {"tm": [[200, 0, 0], [0, 230, 0], [0, 0, 200], [1, 2, 3]]},
                       "spawn_area01_heli": {"tm": [*ident, [4, 5, 6]]}, "spawn_area02": {"tm": [*ident, [7, 8, 9]]}},
             "triggers": {"isCategory": True, "is_enabled": True}}
        mission.apply_edits(m, "me", {"player": {"x": 50.0, "y": 3000.0, "z": 60.0, "yaw": 90, "mode": "air", "speed": 600}})
        a = m["areas"]["spawn_area01"]["tm"]
        self.assertEqual(a[3], [50.0, 3000.0, 60.0])
        self.assertAlmostEqual(a[0][2], 200.0)  # turned to the heading, size kept
        self.assertEqual(m["areas"]["spawn_area01_heli"]["tm"][3], [50.0, 3000.0, 60.0])
        self.assertEqual(m["areas"]["spawn_area02"]["tm"][3], [7, 8, 9])  # another start: untouched
        self.assertFalse(m["mission_settings"]["mission"]["is_airfield_spawn"])
        self.assertNotIn("wtftd_start", m["areas"])  # no second spawn: no jump
        self.assertEqual(m["triggers"]["wtftd_start"]["actions"], {"unitSetProperties": {"object": "me", "speed": 600.0}})

    def test_test_flight_ground_start_gets_its_own_runway(self):
        from wtftd import mission
        ident = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        m = {"imports": {"import_record": [{"file": "test_flight_template.blk"}]},
             "mission_settings": {"mission": {"air_spawn_point": 1, "is_airfield_spawn": False, "is_ship_spawn": True}},
             "units": {"armada": [{"name": "me", "tm": [*ident, [0, 0, 0]], "props": {"army": 1}}]},
             "areas": {"spawn_area01": {"tm": [*ident, [1, 2, 3]]}},
             "triggers": {"isCategory": True, "is_enabled": True}}
        mission.apply_edits(m, "me", {"player": {"x": 50.0, "y": 10.0, "z": 60.0, "yaw": 90, "mode": "ground", "speed": 0}})
        ms = m["mission_settings"]["mission"]
        self.assertEqual((ms["is_airfield_spawn"], ms["is_ship_spawn"], ms["is_water_spawn"]), (True, False, False))
        self.assertEqual(m["areas"]["wtftd_runway_spawn"]["tm"][3], [50.0, 10.0, 60.0])
        end = m["areas"]["wtftd_runway_end"]["tm"][3]
        self.assertAlmostEqual(end[0], 50.0, 3)
        self.assertAlmostEqual(end[2], 660.0, 3)  # 600 m down the heading (yaw 90: +z)
        self.assertEqual(m["triggers"]["wtftd_runway"]["actions"]["addAirfield"]["spawnPoint"], "wtftd_runway_spawn")
        use = m["triggers"]["wtftd_runway_use"]
        self.assertTrue(use["props"]["enableAfterComplete"])
        self.assertEqual(use["actions"]["varSetString"][0], {"value": "wtftd_runway", "var": "airfield_spawn"})
        self.assertNotIn("wtftd_start", m["triggers"])  # no respawn: no jump
        self.assertEqual(m["areas"]["spawn_area01"]["tm"][3], [1, 2, 3])

    def test_known_player_zones_move_with_the_start(self):
        from wtftd import mission
        ident = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]

        def scen():
            return {"imports": {"import_record": [{"file": "testFlight_template.blk"}]},
                    "units": {"tankModels": [{"name": "me", "tm": [*ident, [0, 0, 0]], "props": {"army": 1}}]},
                    "areas": {"spawn01": {"tm": [*ident, [1, 2, 3]]}, "tanks": {"tm": [*ident, [4, 5, 6]]}},
                    "triggers": {"isCategory": True, "is_enabled": True}}
        start = {"x": 50.0, "y": 10.0, "z": 60.0, "yaw": 0}
        m = scen()  # tank test drive: respawned in spawn01 after a crash
        mission._hold_start(m, "me", mission._yaw_tm(0, 50.0, 10.0, 60.0), start, {"player": ["spawn01"], "spawns": {"tanks": ["t1"]}})
        self.assertEqual(m["areas"]["spawn01"]["tm"][3], [50.0, 10.0, 60.0])
        self.assertEqual(m["areas"]["tanks"]["tm"][3], [4, 5, 6])
        self.assertNotIn("wtftd_start", m["triggers"])
        m = scen()  # nothing moves the player: nothing to do
        mission._hold_start(m, "me", mission._yaw_tm(0, 50.0, 10.0, 60.0), start, {"player": [], "spawns": {}})
        self.assertEqual(list(m["triggers"]), ["isCategory", "is_enabled"])
        m = scen()  # a zone other units use too: not moved, held by a respawn instead
        mission._hold_start(m, "me", mission._yaw_tm(0, 50.0, 10.0, 60.0), start, {"player": ["spawn01"], "spawns": {"spawn01": ["t1"]}})
        self.assertEqual(m["areas"]["spawn01"]["tm"][3], [1, 2, 3])
        self.assertEqual(m["triggers"]["wtftd_start"]["actions"]["unitRespawn"]["target"], "wtftd_start")


class AiLoadouts(unittest.TestCase):
    def test_added_and_scenario_units_get_their_loadout(self):
        from wtftd import mission
        ident = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]]
        m = {"units": {"armada": [{"name": "me", "tm": ident, "props": {"army": 1}},
                                  {"name": "bandit", "tm": ident, "unit_class": "mig_29_9_13", "weapons": "", "props": {"army": 2}}]}}
        groups = [{"p": "gameData/Weapons/gsh_301.blk"}, {"p": "gameData/Weapons/cm.blk", "n": 2, "trig": "countermeasures"}]
        mission.apply_edits(m, "me", {
            "units": {"bandit": {"loadout": {"vehicle": "mig_29_9_13", "preset": "mig_29_9_13_r73", "ammo": [{"id": "belt_ap", "count": 150}], "_groups": groups}}},
            "add": [{"block": "armada", "cls": "rafale_c_f3", "x": 1, "y": 2, "z": 3, "loadout": {
                "vehicle": "rafale_c_f3", "preset": "wtftd_custom", "_unitClass": "wtftd_rafale_c_f3_ai1", "ammo": []}}]})
        bandit = m["units"]["armada"][1]
        self.assertEqual(bandit["weapons"], "mig_29_9_13_r73")
        self.assertEqual((bandit["bullets0"], bandit["bulletsCount0"], bandit["bulletsWeapon0"]), ("belt_ap", 150, "gsh_301"))
        added = m["units"]["armada"][2]
        self.assertEqual((added["unit_class"], added["weapons"]), ("wtftd_rafale_c_f3_ai1", "wtftd_custom"))


class FreeTanks(unittest.TestCase):
    """Issue #29: a tank added on Free (AI) gets a route to the nearest capture zone, else stays as it was."""

    def test_nearest_zone_after_the_zones_moved(self):
        from wtftd import mission
        at = lambda x, z: [[1, 0, 0], [0, 1, 0], [0, 0, 1], [x, 5.0, z]]
        m = {"units": {"tankModels": [{"name": "me", "tm": at(0, 0), "props": {"army": 1}}]},
             "areas": {"wtftd_capture_A": {"tm": at(100, 0)}, "wtftd_capture_B": {"tm": at(900, 0)}, "wtftd_spawn": {"tm": at(1000, 0)}}}
        mission.apply_edits(m, "me", {"add": [{"block": "tankModels", "cls": "t_72a", "x": 950, "z": 0},
                                              {"block": "tankModels", "cls": "t_72a", "x": 950, "z": 0, "behavior": "stay"},
                                              {"block": "ships", "cls": "us_fletcher", "x": 950, "z": 0},
                                              {"block": "tankModels", "cls": "t_72a", "x": 50, "z": 0, "routeSpeed": 25}],
                                      "areas": {"wtftd_capture_A": {"x": 960, "z": 10}}})
        free, stay, slow = m["units"]["tankModels"][1:]
        self.assertEqual([w["tm"][3] for w in free["way"].values()], [[960.0, 5.0, 10.0]])  # A, moved next to it
        self.assertEqual([w["props"]["speed"] for w in free["way"].values()], [mission.ZONE_SLOW_SPEED])  # already near: slow in
        # far from B: the speed picked up to 60 m before its centre, then slowly into it
        self.assertEqual([w["tm"][3] for w in slow["way"].values()], [[840.0, 5.0, 0.0], [900.0, 5.0, 0.0]])
        self.assertEqual([w["props"]["speed"] for w in slow["way"].values()], [25.0, mission.ZONE_SLOW_SPEED])
        self.assertFalse(stay["way"])
        self.assertFalse(m["units"]["ships"]["way"])

    def test_after_its_zone_the_next_one_not_held(self):
        from wtftd import mission
        at = lambda x, z: [[1, 0, 0], [0, 1, 0], [0, 0, 1], [x, 5.0, z]]
        m = {"units": {"tankModels": [{"name": "me", "tm": at(0, 0), "props": {"army": 1}}]},
             "areas": {f"wtftd_capture_{k}": {"tm": at(x, 0)} for k, x in (("A", 0), ("B", 400), ("C", 1000))}}
        mission.apply_edits(m, "me", {"add": [{"block": "tankModels", "cls": "t_72a", "x": 380, "z": 500}]})
        tr = m["triggers"]
        look = tr["wtftd_wtftd_unit_01_B"]  # in B, B ours: then A (nearer), then C
        self.assertEqual(look["conditions"]["unitWhenInArea"]["target"], "wtftd_capture_B")
        self.assertEqual(look["conditions"]["missionIsZoneCaptured"], {"target": "wtftd_capture_B", "army": 2})
        self.assertEqual(look["actions"]["triggerActivate"]["target"], "wtftd_wtftd_unit_01_B_1")
        first, last = tr["wtftd_wtftd_unit_01_B_1"], tr["wtftd_wtftd_unit_01_B_2"]
        self.assertFalse(first["is_enabled"])
        self.assertEqual(first["conditions"]["missionIsZoneCaptured"]["target"], "wtftd_capture_A")
        self.assertEqual(first["else_actions"]["unitSetRoute"]["route"], "wtftd_wtftd_unit_01_B_to_A")
        self.assertEqual(first["actions"]["triggerActivate"]["target"], "wtftd_wtftd_unit_01_B_2")
        self.assertEqual((last["else_actions"]["unitSetRoute"]["route"], last["actions"]), ("wtftd_wtftd_unit_01_B_to_C", {}))
        way = list(m["wayPoints"]["wtftd_wtftd_unit_01_B_to_C"]["way"].values())  # from B's centre, slowly into C
        self.assertEqual([w["tm"][3] for w in way], [[940.0, 5.0, 0.0], [1000.0, 5.0, 0.0]])
        self.assertEqual([w["props"]["speed"] for w in way], [mission.FREE_SPEED, mission.ZONE_SLOW_SPEED])
        self.assertTrue(all(w["props"]["canUsePathFinder"] for w in way))  # around the walls, not through
        solid = m["triggers"]["wtftd_editor"]["actions"]["unitSetProperties"]
        self.assertIn({"object": ["wtftd_unit_01"], "ignoreCollisions": False, "ignoresObstaclesAfterTime": False, "movementTraceRI": True},
                      solid if isinstance(solid, list) else [solid])

    def test_no_zone_no_route(self):
        from wtftd import mission
        m = {"units": {"tankModels": {"name": "me", "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]], "props": {"army": 1}}}}
        mission.apply_edits(m, "me", {"add": [{"block": "tankModels", "cls": "t_72a", "x": 50, "z": 0}]})
        self.assertFalse(m["units"]["tankModels"][1]["way"])


def battle_map():
    """A ground battle map as builder.build_battle_scenarios writes one (the real ones live in data/, not in CI)."""
    at = lambda x, z: [[40.0, 0, 0], [0, 30.0, 0], [0, 0, 40.0], [x, 8.0, z]]
    return {"mission_settings": {"player": {"army": 1, "wing": "t1_player01"}, "mission": {"type": "singleMission", "level": "levels/x.bin"}},
            "units": {"tankModels": {"name": "t1_player01", "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 8.0, 0]], "unit_class": "",
                                     "props": {"army": 1}, "way": {}}},
            "areas": {"wtftd_spawn": {"tm": at(0, 0)}, "wtftd_capture_A": {"tm": at(350, 500)}, "wtftd_capture_B": {"tm": at(0, 500)},
                      "wtftd_capture_C": {"tm": at(-400, 500)}, "wtftd_enemy_spawn": {"tm": at(0, 1000)}},
            "triggers": {"isCategory": True, "is_enabled": True}}


class CaptureZones(unittest.TestCase):
    """Issue #28: on a ground battle map, in a tank, A, B, C are capture zones with tickets."""

    def test_battle_map_in_a_tank(self):
        from wtftd import mission
        m = battle_map()
        mission.apply_capture_zones(m)
        marks = m["triggers"]["wtftd_capture"]["actions"]["missionMarkAsCaptureZone"]
        self.assertEqual([z["target"] for z in marks], ["wtftd_capture_A", "wtftd_capture_B", "wtftd_capture_C"])
        self.assertTrue(all(z["army"] == 0 and z["useHUDMarkers"] and not z["onlyPlayersCanCapture"] and not z["playAirfieldSound"] for z in marks))
        circles = {u["name"]: u for u in m["units"]["objectGroups"] if u.get("unit_class") == "capture_zone_circle"}
        self.assertEqual([z["markUnits"] for z in marks], ["wtftd_cz_circle_A", "wtftd_cz_circle_B", "wtftd_cz_circle_C"])
        self.assertEqual(circles["wtftd_cz_circle_B"]["tm"][3], m["areas"]["wtftd_capture_B"]["tm"][3])  # on its zone
        self.assertTrue(m["mission_settings"]["mission"]["gt_mp_capture"] and m["mission_settings"]["mission"]["gt_mp_tickets"])
        self.assertEqual(m["mission_settings"]["mission"]["scoreLimit"], mission.TICKETS)
        self.assertNotIn("ctaCaptureZoneDominationPenalty", m["mission_settings"]["mission"])  # the game's own loss
        for loss, got in (("slow", 14), ("vslow", 7), ("none", None), ("x", None)):  # the map's Ticket loss
            m = battle_map()
            mission.apply_capture_zones(m, loss)
            self.assertEqual(m["mission_settings"]["mission"].get("ctaCaptureZoneDominationPenalty"), got)
            self.assertEqual(m["mission_settings"]["mission"]["gt_mp_tickets"], loss != "none")  # none: no tickets at all
            self.assertTrue(m["mission_settings"]["mission"]["gt_mp_capture"])  # the zones still taken

    def test_only_in_a_tank_on_a_map_with_zones(self):
        from unittest import mock
        from wtftd import mission
        with mock.patch.object(mission, "load_scenario", side_effect=lambda sid: battle_map()):
            air = {"scenario": "battle_x_a_air", "vehicle": "p_51d_5", "block": "armada"}
            self.assertNotIn("missionMarkAsCaptureZone", mission.build(air)[1])
            tank = {"scenario": "battle_x_a_ground", "vehicle": "us_m4a2_sherman", "block": "tankModels", "ticketLoss": "none"}
            text = mission.build(tank)[1]
        self.assertIn("missionMarkAsCaptureZone", text)
        self.assertIn("gt_mp_tickets:b=no", text)  # the map's Ticket loss reaches the mission
        m = {"areas": {"spawn": {"tm": []}}, "triggers": {"isCategory": True}}
        mission.apply_capture_zones(m)
        self.assertNotIn("wtftd_capture", m["triggers"])


class Placeholders(unittest.TestCase):
    """Issue #24: an imported multiplayer mission's player slots (dummy_plane) aren't vehicles to edit."""

    def test_player_slots_are_placeholders(self):
        from unittest import mock
        from wtftd import mission
        m = battle_map()
        ident = lambda x: [[1, 0, 0], [0, 1, 0], [0, 0, 1], [x, 5.0, 0]]
        m["units"]["armada"] = [{"name": "t1_player02", "tm": ident(10), "unit_class": "dummy_plane", "props": {"army": 1}},
                                {"name": "bomber", "tm": ident(20), "unit_class": "b_17g", "props": {"army": 2}}]
        with mock.patch.object(mission, "load_scenario", return_value=m), mock.patch.object(mission, "zone_info", return_value=None, create=True):
            units = {u["name"]: u for u in mission.scenario_units("usr_x")["units"]}
        self.assertEqual((units["t1_player02"].get("slot"), units["t1_player02"]["edit"]), (1, False))
        self.assertEqual((units["bomber"].get("slot"), units["bomber"]["edit"]), (None, True))


class ZoneRoles(unittest.TestCase):
    def test_what_each_zone_gets(self):
        from unittest import mock
        ident = [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]]
        mission = {"mission_settings": {"player": {"wing": "me"}},
                   "areas": {n: {"tm": ident} for n in ("spawn_area01", "spawn_area02", "tank_zone", "reload")}}
        template = {
            "variables": {"air_spawn": "spawn_area0", "player": ""},
            "units": {"tankModels": [{"name": "t1"}, {"name": "t2"}], "squad": [{"name": "sq", "props": {"squad_members": ["t1", "t2"]}}]},
            "triggers": {"isCategory": True,
                         "a": {"actions": {"varSetString": {"value": "me", "var": "player"}, "varAddString": {"var": "air_spawn", "input_var": "n"}}},
                         "b": {"actions": {"unitRespawn": {"object": "@player", "target": "@air_spawn"}}},
                         "c": {"actions": {"unitRespawn": {"object": "sq", "target": "tank_zone"}}},
                         "d": {"actions": {"unitRespawn": {"object": "@player", "target": "@later"}}}}}
        with mock.patch.object(builder, "_import_chain", return_value=[mission, template]):
            r = builder.zone_roles(mission)
        self.assertEqual(r["player"], ["spawn_area01", "spawn_area02"])
        self.assertEqual(r["spawns"]["tank_zone"], ["t1", "t2"])
        self.assertTrue(r["playerOther"])  # @later: only known while the mission runs


class FreeTankSpeed(unittest.TestCase):
    """At 200 km/h the Free (AI) tanks drove through walls: the server gives each its own top speed."""

    def test_top_speed_unless_one_is_picked(self):
        from unittest import mock
        from wtftd import server
        vehicles = {"us_m4a2_sherman": {"id": "us_m4a2_sherman", "c": "ground", "s": {"spd": 47}}}
        add = [{"block": "tankModels", "cls": "us_m4a2_sherman"}, {"block": "tankModels", "cls": "us_m4a2_sherman", "routeSpeed": 20},
               {"block": "tankModels", "cls": "us_m4a2_sherman", "behavior": "stay"}, {"block": "tankModels", "cls": "unknown"}]
        with mock.patch.object(server.STATE, "get_vehicles", return_value=vehicles):
            body, _ = server._prepare_ai({"edits": {"add": add}})
        self.assertEqual([a.get("routeSpeed") for a in body["edits"]["add"]], [47, 20, None, None])
        self.assertNotIn("routeSpeed", add[0])  # the saved setup keeps what the app sent


if __name__ == "__main__":
    unittest.main()
