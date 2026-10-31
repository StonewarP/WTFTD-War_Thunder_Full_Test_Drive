"""Bombing a target: HP from the game's mission templates, damage from its explosion table, the napalm flag of bombs."""
import json
import math
import unittest

from wtftd import armament, builder
from wtftd.paths import DATA


def bisect_damage(curve, kg):
    """As the Weapons page does (curveAt, web/app.js): in straight lines between the table's points."""
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if kg <= x1:
            return y0 + (y1 - y0) * (kg - x0) / (x1 - x0)
    return curve[-1][1]


def trigger(hp, mul, *conditions):
    return {"props": {}, "conditions": {"varCompareInt": list(conditions) if len(conditions) > 1 else conditions[0]},
            "actions": {"varSetReal": [{"value": hp, "var": "baseHP"}, {"value": mul, "var": "arcade_HP_mul"}]}}


def cmp(func, value):
    return {"var_value": "level", "value": value, "comparasion_func": func}


# the shape of destroy_bomb_areas_template: the triggers sit one level down, and a range is two conditions
TEMPLATE = {"triggers": {"routine": {
    "low": trigger(6000.0, 2.5, cmp("less", 4)),
    "mid": trigger(8000.0, 3.2, cmp("more", 3), cmp("less", 8)),
    "high": trigger(12000.0, 4.2, cmp("more", 16)),
    "other": {"conditions": {}, "actions": {"varSetReal": {"value": 5.0, "var": "unrelated"}}},
}}}


class Bands(unittest.TestCase):
    def test_levels_hp_and_arcade_multiplier(self):
        self.assertEqual(builder.hp_bands(TEMPLATE, "baseHP", "arcade_HP_mul", "level"),
                         [[0, 3, 6000.0, 2.5], [4, 7, 8000.0, 3.2], [17, None, 12000.0, 4.2]])

    def test_no_multiplier(self):
        t = {"triggers": {"a": {"conditions": {}, "actions": {"varSetReal": {"value": 6100.0, "var": "bdt_base_hp"}}}}}
        self.assertEqual(builder.hp_bands(t, "bdt_base_hp", None, "level"), [[0, None, 6100.0, None]])

    def test_nothing_to_read(self):
        self.assertEqual(builder.hp_bands({}, "baseHP", None, "level"), [])

    def test_a_repeated_key_of_a_game_table(self):
        self.assertEqual(builder.game_curve({"p0": [25.0, 1100.0], "p2": [[1400.0, 49.0], [4200.0, 71.0]], "p1": [40.0, 1500.0]}),
                         [[25.0, 1100.0], [40.0, 1500.0], [1400.0, 49.0], [4200.0, 71.0]])
        self.assertEqual(builder.game_curve(None), [])


@unittest.skipUnless((DATA / "bases.json").exists(), "needs the game database")
class Reference(unittest.TestCase):
    """The game's values, and what players report: 3 Mk 83 for a base at the top, 6 when it respawns, 9 x 60 kg but not
    an 800 kg bomb at 10,000 HP, 28 SC50 + 2 SC250 for an airfield at BR 2."""

    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((DATA / "bases.json").read_text(encoding="utf-8"))
        cls.weapons = {x["id"]: x for x in json.loads((DATA / "armament.json").read_text(encoding="utf-8"))["items"]}

    def hit(self, weapon):
        return bisect_damage(self.data["damage"], self.weapons[weapon]["tnt"])

    def top(self, kind):
        return self.data["kinds"][kind]["bands"][-1][2]

    def test_hp(self):
        self.assertEqual(self.top("base"), 12000)
        self.assertEqual(self.top("respawn"), 25900)
        self.assertEqual(self.data["kinds"]["airfield"]["bands"][0][2], 32000)

    def test_mk83(self):
        n = math.ceil(self.top("base") / self.hit("us_1000lb_mk_83_ldgp"))
        self.assertEqual((n, math.ceil(self.top("respawn") / self.hit("us_1000lb_mk_83_ldgp"))), (3, 6))

    def test_many_small_bombs_beat_a_big_one(self):
        self.assertGreater(9 * self.hit("jp_navy_type97mod6_60kg"), 10000)
        self.assertLess(self.hit("jp_navy_mod80mark1_800kg"), 10000)

    def test_airfield(self):
        self.assertGreater(28 * self.hit("de_sc50") + 2 * self.hit("de_sc250"), 32000)


class Napalm(unittest.TestCase):
    def stats(self, bomb):
        return armament._stats("bomb", "", bomb, {})

    def test_napalm_bomb_is_flagged(self):  # it_250kg_napalm: splash and fire both napalm
        self.assertEqual(self.stats({"mass": 253.0, "explosiveMass": 208.0, "splash": {"damageType": "napalm"},
                                     "fireDamage": {"damageType": "napalm"}}).get("nap"), 1)

    def test_high_explosive_bomb_is_not(self):
        self.assertNotIn("nap", self.stats({"mass": 241.0, "explosiveMass": 87.1}))


if __name__ == "__main__":
    unittest.main()
