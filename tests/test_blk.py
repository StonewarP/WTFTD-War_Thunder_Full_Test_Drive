"""BLK text format: what WTFTD writes must read back the same (types included)."""
import unittest

from wtftd import blk


class ModFiles(unittest.TestCase):
    """What mods' files hold that the game reads: an include, numbers in quotes, comments inside comments."""

    def test_an_include_is_kept_for_the_reader(self):
        self.assertEqual(blk.loads('include "b_52h.blk"\n"@override:model":t="cl1201"\n'), {"@include": "b_52h.blk", "@override:model": "cl1201"})

    def test_a_number_in_quotes(self):
        self.assertEqual(blk.loads('Vne:r="1000.0"\nangles:p2="10.0, 10.0"\n'), {"Vne": 1000.0, "angles": [10.0, 10.0]})

    def test_comments_inside_a_comment(self):
        text = 'a{\n  /*b{\n    /*c{ x:i=1 }*/\n    y:i=2\n  }*/\n  z:i=3\n}\n'
        self.assertEqual(blk.loads(text), {"a": {"z": 3}})

    def test_a_parameter_named_include(self):
        self.assertEqual(blk.loads('include:t="x"\n'), {"include": "x"})


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
