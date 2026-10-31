"""Base durability from the game's mission templates, and the napalm flag of bombs."""
import unittest

from wtftd import armament, builder


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
