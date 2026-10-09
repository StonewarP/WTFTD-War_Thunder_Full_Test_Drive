"""Units of a game template the mission declares itself (their vehicle can then change); the templates' scripts
stay imported as the game wrote them."""
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


class TakeOverUnits(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        patch = mock.patch.object(mission, "TEMPLATES", Path(self.dir.name))
        patch.start()
        self.addCleanup(patch.stop)
        # a test-flight-like mission: a script template (importing a units set of its own) and a units template
        self.write("gameData/missions/t/script_template.blk", {
            "imports": {"import_record": dict(REC, file="gameData/missions/t/set.blk")},
            "triggers": {"isCategory": True, "init": {"actions": {"unitPutToSleep": {"target": "target_01"}}}},
        })
        self.write("gameData/missions/t/set.blk", {"units": {"air_defence": _unit("aaa", "uk_40mm_bofors")}})
        self.write("gameData/missions/t/units_template.blk", {
            "units": {"armada": [_unit("target_01", "mig-15bis_ns23", 5), _unit("target_02", "b-29"), _unit("gone", "b-29")],
                      "squad": {"name": "targets", "props": {"squad_members": ["target_01", "target_02"]}}},
        })
        self.m = {
            "imports": {"import_record": [dict(REC, file="gameData/missions/t/script_template.blk"),
                                          dict(REC, file="gameData/missions/t/units_template.blk", excludes={"exclude": "gone"})]},
            "triggers": {"isCategory": True, "is_enabled": True},
            "units": {"armada": _unit("armada_01", "f_14b")},
            "objLayers": {"layer": [{"enabled": True}, {"enabled": True}]},
        }

    def write(self, path, doc):
        (Path(self.dir.name) / f"{mission.template_key(path)}.json").write_text(json.dumps(doc), encoding="utf-8")

    def test_swappable(self):
        # units of a template imported directly, without imports of its own; excluded ones left out
        self.assertEqual(mission.swappable_units(self.m), {"target_01", "target_02", "targets"})

    def test_take_over(self):
        brought = mission.take_over_units(self.m, {"target_01"})
        self.assertEqual(brought, {"target_01", "target_02", "targets"})
        recs = self.m["imports"]["import_record"]
        self.assertEqual([r.get("importUnits") for r in recs], [True, False])  # the scripts stay imported
        self.assertEqual([u["name"] for u in self.m["units"]["armada"]], ["armada_01", "target_01", "target_02"])
        self.assertEqual(len(self.m["objLayers"]["layer"]), 6)  # target_01 sits on layer 5
        mission.set_vehicle(self.m["units"]["armada"][1], {"cls": "f_4e"})
        back = blk.loads(blk.dumps(self.m))
        self.assertEqual([u["unit_class"] for u in back["units"]["armada"]], ["f_14b", "f_4e", "b-29"])
        self.assertFalse(back["imports"]["import_record"][1]["importUnits"])

    def test_nothing_to_take(self):
        self.assertEqual(mission.take_over_units(self.m, {"aaa"}), set())  # a units set the script template imports
        self.assertTrue(all(r["importUnits"] for r in self.m["imports"]["import_record"]))
        (Path(self.dir.name) / f"{mission.template_key('gameData/missions/t/units_template.blk')}.json").unlink()
        self.assertEqual(mission.swappable_units(self.m), set())  # template not in the data: nothing changes


if __name__ == "__main__":
    unittest.main()
