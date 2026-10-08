"""BLK text format: what WTFTD writes must read back the same (types included)."""
import unittest

from wtftd import blk


class BlkRoundTrip(unittest.TestCase):
    def test_types_survive_a_round_trip(self):
        d = {
            "name": "Test drive",
            "isImmortal": True,
            "cannotShoot": False,
            "count": 3,
            "speed": 250.5,
            "pos": [1.0, 2.5, -3.0],
            "grid": [4, 5],
            "tm": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [10.0, 20.0, 30.0]],
            "unit": {"class": "germ_leopard_2a6", "army": 1},
        }
        back = blk.loads(blk.dumps(d))
        self.assertEqual(back, d)
        self.assertIsInstance(back["count"], int)
        self.assertIsInstance(back["speed"], float)
        self.assertIs(back["isImmortal"], True)

    def test_repeated_keys_become_a_list(self):
        d = {"Weapon": [{"blk": "a.blk"}, {"blk": "b.blk"}]}
        self.assertEqual(blk.loads(blk.dumps(d)), d)

    def test_written_types(self):
        text = blk.dumps({"a": 1, "b": 1.5, "c": True, "d": "x", "e": [1.0, 2.0, 3.0]})
        for line in ('a:i=1', 'b:r=1.5', 'c:b=yes', 'd:t="x"', 'e:p3=1, 2, 3'):
            self.assertIn(line.replace(" ", ""), text.replace(" ", ""))

    def test_quotes_inside_strings(self):
        d = {"hint": 'Press "J" to rearm'}
        self.assertEqual(blk.loads(blk.dumps(d)), d)

    def test_comments_are_ignored(self):
        text = '// note\na:i=1 /* block */\nb:t="x" // end\nc:r=2.5// tight\n'
        self.assertEqual(blk.loads(text), {"a": 1, "b": "x", "c": 2.5})


if __name__ == "__main__":
    unittest.main()
