"""Routes and waves drawn in the map editor, as the mission writes them."""
import unittest

from wtftd import blk, mission


def tm(x=0.0, y=0.0, z=0.0):
    return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [x, y, z]]


def base():
    return {"units": {"armada": {"name": "me", "tm": tm(), "unit_class": "x", "props": {"army": 1}}}}


def enemy(i, **e):
    return {"block": "tankModels", "cls": "ussr_t_72a", "x": 100.0 * i, "y": 5.0, "z": 0.0, **e}


class Routes(unittest.TestCase):
    def unit(self, **e):
        m = base()
        mission.apply_edits(m, "me", {"add": [enemy(1, **e)]})
        return m["units"]["tankModels"]

    def test_points_in_order_at_the_speed_asked(self):
        u = self.unit(behavior="route", routeSpeed=25, routeLoop=True,
                      route=[{"x": 1, "y": 2, "z": 3}, {"x": 4, "y": 5, "z": 6}])
        self.assertEqual(list(u["way"]), ["wtftd_unit_01_wp_01", "wtftd_unit_01_wp_02"])
        p = u["way"]["wtftd_unit_01_wp_02"]
        self.assertEqual(p["tm"][3], [4.0, 5.0, 6.0])
        self.assertEqual(p["props"]["speed"], 25.0)
        self.assertEqual(p["props"]["moveType"], "MOVETO_STRAIGHT")
        self.assertTrue(u["closed_waypoints"])

    def test_points_only_count_with_the_route_behavior(self):
        self.assertEqual(self.unit(behavior="stay", route=[{"x": 1, "y": 2, "z": 3}])["way"], {})

    def test_bad_points_are_left_out(self):
        u = self.unit(behavior="route", routeSpeed="fast", route=[{"x": "a", "y": 2, "z": 3}, {"x": 1}, {"x": 1, "y": 2, "z": 3}])
        self.assertEqual(len(u["way"]), 1)
        self.assertEqual(next(iter(u["way"].values()))["props"]["speed"], 40.0)

    def test_a_route_stops_at_the_limit(self):
        u = self.unit(behavior="route", route=[{"x": i, "y": 0, "z": 0} for i in range(100)])
        self.assertEqual(len(u["way"]), mission.ROUTE_POINTS)


class Waves(unittest.TestCase):
    def mission(self, *waves, **top):
        m = base()
        mission.apply_edits(m, "me", {"add": [enemy(i + 1, wave=w) for i, w in enumerate(waves)], **top})
        return m

    def names(self, m):
        return {u["name"]: u for u in m["units"]["tankModels"]}

    def test_the_first_wave_is_there_the_others_wait(self):
        u = self.names(self.mission(2, 2, 5))
        self.assertNotIn("isDelayed", u["wtftd_unit_01"]["props"])
        self.assertTrue(u["wtftd_unit_03"]["props"]["isDelayed"])

    def test_each_wave_brings_the_next_when_destroyed(self):
        m = self.mission(1, 2, 3, waveText="Vague {n}")
        t1, t2 = m["triggers"]["wtftd_wave_1_end"], m["triggers"]["wtftd_wave_2_end"]
        self.assertTrue(t1["is_enabled"])
        self.assertFalse(t2["is_enabled"])
        self.assertEqual(t1["conditions"]["unitWhenCountMatches"]["object"], "wtftd_wave_1")
        self.assertEqual(t1["actions"]["unitRespawn"]["object"], "wtftd_unit_02")
        self.assertEqual(t1["actions"]["unitRespawn"]["target"], "wtftd_wave_wtftd_unit_02")
        self.assertIn("wtftd_wave_wtftd_unit_02", m["areas"])
        self.assertEqual(t1["actions"]["triggerEnable"]["target"], ["wtftd_wave_2_end"])
        self.assertEqual(t2["actions"]["playHint"]["name"], "Vague 3")
        self.assertNotIn("triggerEnable", t2["actions"])  # the last wave ends it all
        self.assertNotIn("wtftd_wave_3_end", m["triggers"])
        self.assertEqual(list(t1["actions"])[0], "wait")

    def test_the_numbers_need_not_follow(self):
        m = self.mission(3, 7)
        self.assertEqual(m["triggers"]["wtftd_wave_3_end"]["actions"]["playHint"]["name"], "Wave 2")

    def test_starting_again_brings_the_first_wave_back(self):
        m = self.mission(1, 2, waveLoop=True)
        last = m["triggers"]["wtftd_wave_2_end"]
        self.assertEqual(last["actions"]["unitRespawn"]["object"], "wtftd_unit_01")
        self.assertEqual(last["actions"]["unitRestore"]["target"], ["wtftd_unit_01"])
        self.assertEqual(last["actions"]["triggerEnable"]["target"], ["wtftd_wave_1_end"])
        self.assertIn("wtftd_wave_wtftd_unit_01", m["areas"])

    def test_one_wave_starting_again_repeats_itself(self):
        t = self.mission(4, waveLoop=True)["triggers"]["wtftd_wave_4_end"]
        self.assertTrue(t["props"]["enableAfterComplete"])
        self.assertNotIn("triggerEnable", t["actions"])

    def test_one_wave_alone_needs_no_script(self):
        self.assertNotIn("wtftd_wave_4_end", self.mission(4).get("triggers") or {})

    def test_several_units_in_a_wave(self):
        m = self.mission(1, 2, 2)
        self.assertEqual([a["object"] for a in m["triggers"]["wtftd_wave_1_end"]["actions"]["unitRespawn"]],
                         ["wtftd_unit_02", "wtftd_unit_03"])
        self.assertEqual(m["units"]["squad"][1]["props"]["squad_members"], ["wtftd_unit_02", "wtftd_unit_03"])

    def test_allies_are_in_no_wave(self):
        m = base()
        mission.apply_edits(m, "me", {"add": [enemy(1, wave=1), enemy(2, wave=2, side="ally")]})
        self.assertNotIn("isDelayed", m["units"]["tankModels"][1]["props"])
        self.assertNotIn("wtftd_wave_1_end", m.get("triggers") or {})

    def test_orders_are_given_again_on_coming_in(self):
        m = base()
        mission.apply_edits(m, "me", {"add": [enemy(1, wave=1), enemy(2, wave=2, behavior="stay", attack="hold_fire")]})
        held = m["triggers"]["wtftd_wave_1_end"]["actions"]["unitSetProperties"]
        self.assertEqual(held, [{"object": ["wtftd_unit_02"], "cannotMove": True}, {"object": ["wtftd_unit_02"], "cannotShoot": True}])

    def test_targets_come_back_leaves_the_waves_alone(self):
        m = base()
        mission.apply_edits(m, "me", {"add": [enemy(1, wave=1), enemy(2, wave=2), enemy(3)]})
        mission.apply_hotkeys(m, "me", {"targetsBack": True, "hotkeys": True}, False, None, None)
        self.assertEqual(m["triggers"]["wtftd_targets_back"]["actions"]["unitRestore"]["target"], ["wtftd_unit_03"])
        self.assertEqual(m["triggers"]["wtftd_key_targets"]["actions"]["unitRestore"]["target"], ["wtftd_unit_03"])

    def test_it_all_writes_out_and_reads_back(self):
        m = self.mission(1, 2, waveLoop=True)
        back = blk.loads(blk.dumps(m))
        self.assertEqual(back["triggers"]["wtftd_wave_1_end"]["conditions"]["unitWhenCountMatches"]["func"], "less")
        self.assertEqual(back["areas"]["wtftd_wave_wtftd_unit_02"]["type"], "Sphere")
