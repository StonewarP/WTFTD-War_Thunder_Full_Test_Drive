"""Game missions imported into My maps (Import): read and checked, kept as scenarios of their own, played as their
creator made them or with another vehicle."""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from wtftd import blk, imports, mission

MISSION = """mission_settings{
  player{
    army:i=1
    wing:t="_player"
  }
  mission{
    name:t="my_range"
    type:t="campaign"
    level:t="levels/avg_training_ground.bin"
  }
}
imports{}
triggers{
  isCategory:b=yes
  is_enabled:b=yes
  restore_targets{
    is_enabled:b=yes
  }
}
units{
  tankModels{
    name:t="_player"
    tm:m=[[1, 0, 0] [0, 1, 0] [0, 0, 1] [100, 20, 200]]
    unit_class:t="germ_leopard_2pl"
    weapons:t="germ_leopard_2pl_default"
    bullets0:t="120mm_dm53"
    bulletsCount0:i=30
    applyAllMods:b=yes
    props{
      army:i=1
      count:i=1
    }
  }
  tankModels{
    name:t="target_1"
    tm:m=[[1, 0, 0] [0, 1, 0] [0, 0, 1] [300, 20, 200]]
    unit_class:t="ussr_t_72av_turms"
    props{
      army:i=2
      count:i=1
    }
  }
}
areas{}
"""
TEXTS = '"<ID|readonly|noverify>";"<English>";"<Russian>";\r\n"missions/my_range";"My Range - Rank VII";"Полигон";\r\n' \
        '"missions/my_range/objective";"Shoot   them all";"";\r\n'


def archive(files: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return out.getvalue()


class Read(unittest.TestCase):
    def test_a_mission_its_texts_and_its_creators_vehicle(self):
        data = archive({"my_range/my_range.blk": MISSION, "my_range/usr_my_range.csv": TEXTS,
                        "my_range/my_range_tutorial.blk": MISSION, "my_range/usr_my_range_tutorial.csv": TEXTS})
        found = {f["sid"]: f for f in imports.read("my_range.zip", data)}
        self.assertEqual(sorted(found), ["usr_my_range", "usr_my_range_tutorial"])
        f = found["usr_my_range"]
        self.assertEqual((f["name"], f["description"], f["map"], f["block"], f["wing"]),
                         ("My Range - Rank VII", "Shoot them all", "avg_training_ground", "tankModels", "_player"))
        self.assertEqual(list(f["texts"]), ["usr_my_range.csv"])  # its own, not the tutorial's
        self.assertNotIn("\r", f["texts"]["usr_my_range.csv"])  # Windows ends as read_text gives them: not doubled once written
        self.assertEqual(imports.vehicle(f) | {"mods": {}, "cheats": {}},
                         {"vehicle": "germ_leopard_2pl", "block": "tankModels", "preset": "germ_leopard_2pl_default",
                          "ammo": [{"id": "120mm_dm53", "count": 30}], "allMods": True, "start": "scenario", "altitude": 1500,
                          "speed": 450, "fuel": 0, "mods": {}, "cheats": {}})

    def test_unlimited_ammo_in_the_mission_gives_the_vehicle_the_games_load(self):  # WT Smart Test Drive: 5 shells
        f, = imports.read("x.blk", MISSION.replace('level:t="levels/', 'isLimitedAmmo:b=no\n    level:t="levels/').encode())
        self.assertEqual((imports.vehicle(f)["ammo"], imports.vehicle(f)["preset"]), ([], "germ_leopard_2pl_default"))

    def test_a_map_the_game_doesnt_have(self):  # a terrain of its own, shipped beside the mission
        with self.assertRaises(imports.ImportFailed) as e:
            imports.read("x.blk", MISSION.encode(), {"air_afghan": {}})
        self.assertEqual(e.exception.code, "map")
        self.assertTrue(imports.read("x.blk", MISSION.encode(), {"avg_training_ground": {}}))

    def test_one_blk_without_texts(self):
        f, = imports.read("..\\..\\x/my_range.blk", MISSION.encode())  # a path in the name: only its file name counts
        self.assertEqual((f["sid"], f["name"], f["texts"]), ("usr_my_range", "my range", {}))

    def test_its_title_from_its_loc_name(self):  # the T-14's: locName:t="[T-14] Test Drive", a text or a key of its texts
        named = MISSION.replace('    name:t="my_range"\n', '    name:t="my_range"\n    locName:t="[T-14] Test Drive"\n', 1)
        self.assertEqual(imports.read("my_range.blk", named.encode())[0]["name"], "[T-14] Test Drive")
        keyed = MISSION.replace('    name:t="my_range"\n', '    name:t="my_range"\n    locName:t="missions/town"\n', 1)
        files = {"my_range.blk": keyed, "usr_my_range.csv": "<ID|readonly|noverify>;English\nmissions/town;Clear the town\n"}
        self.assertEqual(imports.read_files(files)[0]["name"], "Clear the town")

    def test_what_it_imports_of_user_missions_is_kept(self):  # the T-14's template, its own import too; the game's stay its
        imported = MISSION.replace("imports{}", 'imports{\n  import_record{\n    file:t="UserMissions/template/testflight_template.blk"\n  }\n'
                                   '  import_record{\n    file:t="gameData/missions/templates/x.blk"\n  }\n}')
        template = 'imports{\n  import_record{\n    file:t="UserMissions/template/sound_areas.blk"\n  }\n}\nareas{}\n'
        data = archive({"Armata/my_range.blk": imported, "template/testflight_template.blk": template, "template/sound_areas.blk": "areas{}\n",
                        "template/granitograd_airfields.blk": MISSION.replace('wing:t="_player"', 'wing:t="nobody"')})  # no player: a part
        f, = imports.read("t_14.zip", data)
        self.assertEqual(f["parts"], {"UserMissions/template/testflight_template.blk": template, "UserMissions/template/sound_areas.blk": "areas{}\n"})
        self.assertEqual(imports.read("x.blk", imported.encode())[0]["parts"], {})  # not at hand: nothing kept
        bad = MISSION.replace("imports{}", 'imports{\n  import_record{\n    file:t="UserMissions/../../config.blk"\n  }\n}')
        self.assertEqual(imports.read_files({"x.blk": bad}, find=lambda p: "x")[0]["parts"], {})

    def test_what_isnt_a_mission_to_import(self):
        cases = {"file": ("x.zip", b"not a zip"), "empty": ("x.zip", archive({"readme.txt": "hi", "sight.blk": "crosshair{}"})),
                 "parse": ("x.blk", b"mission_settings{ broken"),
                 "level": ("x.blk", MISSION.replace("levels/avg_training_ground.bin", "../../x").encode()),
                 "player": ("x.blk", MISSION.replace('wing:t="_player"', 'wing:t="nobody"').encode())}
        for code, (name, data) in cases.items():
            with self.subTest(code), self.assertRaises(imports.ImportFailed) as e:
                imports.read(name, data)
            self.assertEqual(e.exception.code, code)
        with self.assertRaises(imports.ImportFailed) as e:
            imports.read("x.exe", b"MZ")
        self.assertEqual(e.exception.code, "file")

    def test_an_archive_too_big_unpacked_is_refused_before_reading(self):
        with mock.patch.object(imports, "MAX_TOTAL", 100), self.assertRaises(imports.ImportFailed) as e:
            imports.read("x.zip", archive({"a.blk": MISSION}))
        self.assertEqual(e.exception.code, "size")


class Kept(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "imported"
        for module in (imports, mission):
            patcher = mock.patch.object(module, "IMPORTED", self.dir)
            patcher.start()
            self.addCleanup(patcher.stop)
        found = imports.read("my_range.zip", archive({"my_range.blk": MISSION, "usr_my_range.csv": TEXTS}))
        self.entry, = imports.save(found)
        self.cfg = imports.vehicle(found[0])

    def test_listed_and_read_back_as_a_scenario(self):
        self.assertEqual({k: self.entry[k] for k in ("id", "map", "kind", "block", "wing", "pos", "units", "title")},
                         {"id": "usr_my_range", "map": "avg_training_ground", "kind": "ground", "block": "tankModels",
                          "wing": "_player", "pos": [100, 20, 200], "units": 2, "title": "My Range - Rank VII"})
        self.assertEqual(imports.entries(), [self.entry])
        self.assertEqual(mission.load_scenario("usr_my_range")["mission_settings"]["mission"]["name"], "my_range")
        self.assertEqual([p.name for p in imports.texts("usr_my_range")], ["usr_my_range.csv"])
        self.assertEqual(imports.texts("../x"), [])

    def test_another_mission_under_the_same_file_name_is_kept_apart(self):
        other, = imports.save(imports.read("my_range.blk", MISSION.replace('name:t="my_range"', 'name:t="their_range"').encode()))
        self.assertEqual(other["id"], "usr_my_range_2")
        self.assertEqual(sorted(e["id"] for e in imports.entries()), ["usr_my_range", "usr_my_range_2"])
        self.assertEqual(mission.load_scenario("usr_my_range")["mission_settings"]["mission"]["name"], "my_range")

    def test_forgotten_with_its_texts(self):
        self.assertTrue(imports.remove("usr_my_range"))
        self.assertEqual((imports.entries(), imports.texts("usr_my_range"), sorted(p.name for p in self.dir.iterdir())), ([], [], ["index.json"]))
        with self.assertRaises(mission.MissionError):
            mission.load_scenario("usr_my_range")
        self.assertFalse(imports.remove("../index"))

    def test_its_texts_as_one_file_for_the_mission_made_of_it(self):  # the game reads usr_<mission file>.csv
        (self.dir / "usr_my_range" / "more.csv").write_text('"<ID|readonly|noverify>";"<English>"\n"extra_key";"Extra"\n', encoding="utf-8")
        lines = imports.texts_for("usr_my_range").splitlines()
        self.assertEqual(sum(x.startswith('"<ID') for x in lines), 1)
        self.assertIn('"extra_key";"Extra"', lines)
        self.assertIn('"missions/my_range";"My Range - Rank VII";"Полигон";', lines)
        self.assertIsNone(imports.texts_for("usr_nothing"))

    def test_what_it_imports_goes_beside_the_mission_made_of_it(self):  # deleted from UserMissions since, it still loads
        found = imports.read_files({"armata.blk": MISSION.replace("imports{}", 'imports{\n  import_record{\n    file:t="UserMissions/template/t.blk"\n  }\n}')},
                                   find={"UserMissions/template/t.blk": 'imports{\n  import_record{\n    file:t="UserMissions/template/u.blk"\n  }\n}\n',
                                         "UserMissions/template/u.blk": "areas{}\n"}.get)
        imports.save(found)
        um = self.dir.parent / "UserMissions"
        text, parts = imports.for_game("usr_armata", "wtftd_usr_armata", 'file:t="UserMissions/template/t.blk"', um)
        self.assertEqual(text, 'file:t="UserMissions/wtftd_usr_armata.imports/template_t.blk"')
        self.assertEqual(parts, {"template_t.blk": 'imports{\n  import_record{\n    file:t="UserMissions/wtftd_usr_armata.imports/template_u.blk"\n  }\n}\n',
                                 "template_u.blk": "areas{}\n"})
        self.assertTrue(imports.remove("usr_armata"))
        self.assertFalse((self.dir / "usr_armata").exists())

    def test_what_it_imports_and_wtftd_hasnt_must_be_in_the_game(self):  # imported before WTFTD kept them (the T-14's)
        um = self.dir.parent / "UserMissions"
        with self.assertRaises(imports.MissingPart) as e:
            imports.for_game("usr_my_range", "wtftd_usr_my_range", 'file:t="UserMissions/template/t.blk"', um)
        self.assertEqual(str(e.exception), "UserMissions/template/t.blk")
        (um / "template").mkdir(parents=True)
        (um / "template" / "t.blk").write_text("areas{}\n")
        self.assertEqual(imports.for_game("usr_my_range", "x", 'file:t="UserMissions/template/t.blk"', um), ('file:t="UserMissions/template/t.blk"', {}))
        self.assertEqual(imports.for_game("usr_my_range", "x", 'file:t="gameData/missions/x.blk"', um), ('file:t="gameData/missions/x.blk"', {}))

    def test_imported_again_it_replaces_itself(self):
        imports.save(imports.read("my_range.blk", MISSION.encode()))
        self.assertEqual([e["id"] for e in imports.entries()], ["usr_my_range"])
        self.assertEqual(imports.texts("usr_my_range"), [])  # the new one came without texts

    def units(self, cfg: dict) -> dict:
        m = blk.loads(mission.build({**cfg, "scenario": "usr_my_range", "cheats": {}})[1])
        return {u["name"]: u for u in m["units"]["tankModels"]}, m

    def test_played_as_its_creator_made_it(self):
        units, m = self.units(self.cfg)
        me = units["_player"]
        self.assertEqual((me["unit_class"], me["weapons"], me["bullets0"], me["bulletsCount0"]),
                         ("germ_leopard_2pl", "germ_leopard_2pl_default", "120mm_dm53", 30))
        self.assertEqual(units["target_1"]["unit_class"], "ussr_t_72av_turms")
        self.assertIn("restore_targets", m["triggers"])  # its own rules stay

    def test_its_own_vehicle_with_no_shells_picked_keeps_the_missions(self):  # a mod's T-14: empty slots gave it one round
        units, _ = self.units({**self.cfg, "ammo": []})
        self.assertEqual((units["_player"]["bullets0"], units["_player"]["bulletsCount0"]), ("120mm_dm53", 30))
        units, _ = self.units({**self.cfg, "vehicle": "us_m1_abrams", "preset": "", "ammo": []})
        self.assertEqual((units["_player"]["bullets0"], units["_player"]["bulletsCount0"]), ("", 0))  # another one: the game's load
        units, _ = self.units({**self.cfg, "vehicle": "ussr_t_14_armata", "preset": "", "ammo": [], "_shells": [{"id": "", "count": 45}]})
        self.assertEqual((units["_player"]["bullets0"], units["_player"]["bulletsCount0"]), ("", 45))  # a package's tank: its own

    def test_or_with_another_vehicle(self):
        units, m = self.units({**self.cfg, "vehicle": "us_m1_abrams", "preset": "us_m1_abrams_default", "ammo": []})
        self.assertEqual((units["_player"]["unit_class"], units["target_1"]["unit_class"]), ("us_m1_abrams", "ussr_t_72av_turms"))
        self.assertIn("restore_targets", m["triggers"])


if __name__ == "__main__":
    unittest.main()
