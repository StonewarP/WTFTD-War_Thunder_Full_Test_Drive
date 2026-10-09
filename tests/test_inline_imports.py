"""A mission that carries the game templates it imports (their units' vehicles can then change)."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wtftd import blk, mission

REC = {"importAreas": True, "importUnits": True, "importTriggers": True, "importMissionObjectives": True,
       "importWayPoints": True, "importDialogs": True, "excludes": {}}


def _unit(name, cls, layer=1):
    return {"name": name, "unit_class": cls, "objLayer": layer, "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0.0, 0.0, 0.0]],
            "props": {"army": 2, "count": 1}}


class InlineImports(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patch = mock.patch.object(mission, "TEMPLATES", Path(self.dir.name))
        patch.start()
        self.addCleanup(patch.stop)
        # a test-flight-like chain: the mission imports a script template (which imports a units set, minus
        # one of its triggers) and a units template
        self.write("gameData/missions/t/script_template.blk", {
            "imports": {"import_record": dict(REC, file="gameData/missions/t/set.blk", excludes={"exclude": "set_init"})},
            "variables": {"air_spawn": "zone_a"},
            "triggers": {"isCategory": True, "is_enabled": True,
                         "init": {"events": {"initMission": {}}, "actions": {"unitPutToSleep": {"target": "target_01"}}},
                         "routines": {"isCategory": True, "is_enabled": True, "spawn": {"actions": {}}}},
            "mission_objectives": {"isCategory": True, "is_enabled": True, "obj": {"type": "abstractMissionObjective"}},
        })
        self.write("gameData/missions/t/set.blk", {
            "units": {"air_defence": _unit("aaa", "uk_40mm_bofors", 4), "squad": {"name": "aaa_squad", "props": {"squad_members": "aaa"}}},
            "triggers": {"isCategory": True, "is_enabled": True, "set_init": {"actions": {}}, "set_loop": {"actions": {}}},
        })
        self.write("gameData/missions/t/units_template.blk", {
            "units": {"armada": [_unit("target_01", "mig-15bis_ns23"), _unit("target_02", "b-29")]},
            "areas": {"zone_a": {"type": "Sphere", "objLayer": 0, "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [5.0, 0.0, 5.0]]}},
        })
        self.m = {
            "imports": {"import_record": [dict(REC, file="gameData/missions/t/script_template.blk"),
                                          dict(REC, file="gameData/missions/t/units_template.blk")]},
            "variables": {"air_spawn": "zone_mine"},  # the mission's own value wins
            "triggers": {"isCategory": True, "is_enabled": True, "wtftd_editor": {"actions": {}}},
            "units": {"armada": _unit("armada_01", "f_14b")},
            "areas": {"zone_mine": {"type": "Point", "tm": [[1, 0, 0], [0, 1, 0], [0, 0, 1], [1.0, 0.0, 1.0]]}},
            "objLayers": {"layer": [{"enabled": True}, {"enabled": True}]},
        }

    def write(self, path, doc):
        (Path(self.dir.name) / f"{mission.template_key(path)}.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_merge(self):
        self.assertTrue(mission.can_inline(self.m))
        brought = mission.inline_imports(self.m)
        self.assertEqual(brought, {"target_01", "target_02", "aaa", "aaa_squad"})
        self.assertEqual(self.m["imports"], {})
        self.assertEqual([u["name"] for u in self.m["units"]["armada"]], ["armada_01", "target_01", "target_02"])
        self.assertEqual(self.m["variables"]["air_spawn"], "zone_mine")
        self.assertIn("zone_a", self.m["areas"])
        trig = self.m["triggers"]
        self.assertNotIn("set_init", trig)  # excluded by the import record
        # the templates' triggers first (categories kept), then the mission's own (WTFTD's)
        self.assertEqual([k for k in trig if k not in ("isCategory", "is_enabled")], ["init", "routines", "set_loop", "wtftd_editor"])
        self.assertTrue(trig["routines"]["isCategory"])
        self.assertIn("obj", self.m["mission_objectives"])
        self.assertEqual(len(self.m["objLayers"]["layer"]), 5)  # the Bofors sits on layer 4

    def test_missing_template_keeps_the_imports(self):
        (Path(self.dir.name) / f"{mission.template_key('gameData/missions/t/set.blk')}.json").unlink()
        before = copy.deepcopy(self.m)
        self.assertFalse(mission.can_inline(self.m))
        self.assertIsNone(mission.inline_imports(self.m))
        self.assertEqual(self.m, before)

    def test_written_mission_reads_back(self):
        mission.inline_imports(self.m)
        mission.set_vehicle(self.m["units"]["armada"][1], {"cls": "f_4e"})
        back = blk.loads(blk.dumps(self.m))
        self.assertEqual([u["unit_class"] for u in back["units"]["armada"]], ["f_14b", "f_4e", "b-29"])
        self.assertIn("routines", back["triggers"])


if __name__ == "__main__":
    unittest.main()
