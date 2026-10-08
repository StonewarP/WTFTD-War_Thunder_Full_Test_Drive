"""Custom loadouts on aircraft that only have fixed presets: attachment points read from the presets,
the custom preset written as plain weapons on those points (no game files are needed)."""
import unittest
from unittest import mock

from wtftd import builder, cdk

SC50 = "gameData/Weapons/BombGuns/de_sc50.blk"
SC250 = "gameData/Weapons/BombGuns/de_sc250.blk"
PRESETS = {
    "p_4xsc50.blk": {"Weapon": [{"trigger": "bombs", "blk": SC50, "emitter": f"bomb{i}", "bullets": 1} for i in (2, 3, 4, 5)]},
    "p_sc250.blk": {"Weapon": {"trigger": "bombs", "blk": SC250, "emitter": "bomb1", "bullets": 1}},
}
UNIT = {"weapon_presets": {"preset": [{"name": "x_default", "blk": "p_default.blk"},
                                      {"name": "x_4xSC50", "blk": "p_4xsc50.blk"},
                                      {"name": "x_SC250", "blk": "p_sc250.blk"}]}}


class FakeWeapons:
    def weapon_name(self, blk):
        return blk.rsplit("/", 1)[-1].removesuffix(".blk").lower()

    def get(self, blk):
        return None


class LegacyPylons(unittest.TestCase):
    def pylons(self):
        with mock.patch.object(builder, "load", side_effect=lambda p: PRESETS.get(p.name)), \
                mock.patch.object(builder, "blk_to_path", side_effect=lambda b: builder.Path(b)):
            return builder.legacy_pylons(UNIT, FakeWeapons())

    def test_points_from_presets(self):
        pylons, per_preset = self.pylons()
        self.assertEqual([(p["i"], p["e"], [o["n"] for o in p["o"]]) for p in pylons],
                         [(1, "bomb1", ["de_sc250"]), (2, "bomb2", ["de_sc50"]), (3, "bomb3", ["de_sc50"]),
                          (4, "bomb4", ["de_sc50"]), (5, "bomb5", ["de_sc50"])])
        self.assertEqual(per_preset["x_SC250"], {"1": "de_sc250"})
        self.assertEqual(per_preset["x_4xSC50"], {"2": "de_sc50", "3": "de_sc50", "4": "de_sc50", "5": "de_sc50"})
        self.assertNotIn("x_default", per_preset)

    def test_no_points_for_weapon_slot_aircraft(self):
        self.assertEqual(builder.legacy_pylons({"WeaponSlots": {}}, FakeWeapons()), ([], {}))

    def test_custom_preset_written_as_plain_weapons(self):
        pylons, _ = self.pylons()
        details = {"lp": pylons, "am": [], "pr": [], "b": "armada"}
        catalog = {"de_br20": {"p": "gameData/Weapons/rocketGuns/de_br20.blk", "c": "rockets", "t": "rockets"}}
        files, preset, _, _ = cdk.build_files("x", "air", details, {}, "", {"1": "de_sc250", "5": {"w": "de_br20", "n": 1}},
                                              "custom", None, catalog)
        self.assertEqual(preset, cdk.CUSTOM_PRESET)
        text = next(v for k, v in files.items() if "weaponPresets" in k)
        self.assertIn(f'blk:t="{SC250}"\n  emitter:t="bomb1"', text)
        self.assertIn('blk:t="gameData/Weapons/rocketGuns/de_br20.blk"\n  emitter:t="bomb5"', text)
        self.assertNotIn("slot:i=", text)


if __name__ == "__main__":
    unittest.main()
