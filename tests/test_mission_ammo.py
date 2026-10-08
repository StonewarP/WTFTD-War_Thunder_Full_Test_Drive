"""The player's bullet slots in a mission: belts as before, countermeasures split between flares and chaff."""
import unittest

from wtftd import mission


def slots(unit):
    return [(unit[f"bullets{i}"], unit[f"bulletsCount{i}"]) for i in range(4)]


class BulletSlots(unittest.TestCase):
    def test_belts_and_shells_unchanged(self):
        unit = {}
        mission.write_bullets(unit, [{"id": "M60_air_targets", "count": 676}, {"id": "", "count": 60}])
        self.assertEqual(slots(unit), [("M60_air_targets", 676), ("", 60), ("", 0), ("", 0)])

    def test_mixed_countermeasures_add_the_chaff_slot(self):
        unit = {}
        mission.write_bullets(unit, [{"id": "", "count": 676},
                                     {"id": "", "count": 40, "chaff": {"id": "countermeasures_launcher_chaff", "count": 20}}])
        self.assertEqual(slots(unit), [("", 676), ("", 40), ("countermeasures_launcher_chaff", 20), ("", 0)])

    def test_no_free_slot_or_bad_id(self):
        unit = {}
        full = [{"id": "", "count": 1}] * 3 + [{"id": "", "count": 5, "chaff": {"id": "x", "count": 5}}]
        mission.write_bullets(unit, full)
        self.assertEqual(slots(unit)[3], ("", 5))
        unit = {}
        mission.write_bullets(unit, [{"id": "", "count": 5, "chaff": {"id": 'a" b', "count": 5}}])
        self.assertEqual(slots(unit)[1], ("", 0))


if __name__ == "__main__":
    unittest.main()
