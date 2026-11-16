"""The overlay's text painted by GDI+ (Windows) or cairo (Linux): laid out as the Tk overlay was, smooth letters with a
dark halo when no outline is set, see-through backgrounds, blinking lines; no window, into memory."""
import sys
import unittest

from tests.test_alarms import WORDS
from wtftd import alarms, cairopaint

PAINTER = sys.platform == "win32" or (sys.platform.startswith("linux") and cairopaint.available())


def painter():
    """This system's painter: GDI+ on Windows, cairo on Linux."""
    if sys.platform == "win32":
        from wtftd import mappaint
        return mappaint.Painter()
    return cairopaint.Painter()


def line(text, color="#E6E6E6", size=40, blinks=False, block=0, parts=None):
    return (text, color, size, blinks, block, parts or [(text, color)])


@unittest.skipUnless(PAINTER, "GDI+ or cairo")
class Text(unittest.TestCase):
    def setUp(self):
        self.painter = painter()
        self.cfg = {**alarms.clean({}, WORDS), "x": 100, "y": 50, "font": "Consolas", "bold": True, "outline": 0}

    def alpha(self, px, box, x, y):
        return px[((y - box[1]) * box[2] + (x - box[0])) * 4 + 3]

    def test_spaces_count_and_parts_follow_each_other(self):
        parts, _ = self.painter.text_layout(self.cfg, [line("IAS    771", parts=[("IAS    ", "#E6E6E6"), ("771", "#FF0000")])])
        (x0, _, a, *_), (x1, _, b, *_) = parts
        self.assertEqual((a, b), ("IAS    ", "771"))
        self.assertGreater(x1 - x0, 6 * 18)  # 7 characters of a 40 px Consolas: the spaces are kept

    def test_columns_and_lines_go_down(self):
        cfg = {**self.cfg, "blocks": [], "columns": 2}
        parts, boxes = self.painter.text_layout(cfg, [line("A"), line("B"), line("C")])
        ys = [p[1] for p in parts]
        self.assertEqual(ys[0], ys[2])  # C starts the second column, at the top
        self.assertGreater(ys[1], ys[0])
        self.assertGreater(parts[2][0], parts[0][0])
        self.assertEqual(len(boxes), 1)

    def test_a_table_lines_its_names_and_values_up(self):
        rows = [line("", parts=[("IAS ", "#E6E6E6"), ("512", "#E6E6E6"), (" / ", "#E6E6E6"), ("900", "#E6E6E6"), (" km/h", "#E6E6E6")]),
                line("", parts=[("MACH ", "#E6E6E6"), ("0.82", "#E6E6E6"), (" / ", "#E6E6E6"), ("1.10", "#E6E6E6")]),
                line("A long title, out of the table"), line("", parts=[("", "#E6E6E6"), ("Su-27SM", "#E6E6E6")])]
        width = lambda text: self.painter._width(text, self.painter._text_font(self.cfg, 40)[0])
        for names, values in (("left", "right"), ("right", "left")):
            parts, _ = self.painter.text_layout({**self.cfg, "table": True, "nameAlign": names, "valueAlign": values}, rows)
            at = {p[2]: p[0] for p in parts}
            ends = lambda *texts: {round(at[x] + width(x), 3) for x in texts}
            self.assertEqual(len({at["IAS "], at["MACH "]} if names == "left" else ends("IAS ", "MACH ")), 1, names)
            self.assertEqual(len(ends("512", "0.82") if values == "right" else {at["512"], at["0.82"]}), 1, values)
            self.assertEqual(len(ends("900", "1.10") if values == "right" else {at["900"], at["1.10"]}), 1, values)
            self.assertEqual(at["A long title, out of the table"], 100)  # a line without values: as it is, not in a cell
            self.assertEqual(at["Su-27SM"], 100)  # nor one without a name ({vehicle}): from the left
            self.assertLess(at["512"], 100 + width("A long title, out of the table"))
        parts, _ = self.painter.text_layout(self.cfg, rows)  # off: each line's parts follow each other
        self.assertAlmostEqual(parts[1][0], 100 + width("IAS "))
        for table in (True, False):  # a line out of the table, to the right: it ends where the widest line ends
            right = [*rows[:2], (*line("", parts=[("", "#E6E6E6"), ("Su-27SM", "#E6E6E6")]), "right")]
            parts, (( _, box),) = self.painter.text_layout({**self.cfg, "table": table}, right)
            self.assertAlmostEqual(parts[-1][0] + width("Su-27SM"), box[2], places=3)
            self.assertGreater(parts[-1][0], 100)

    def test_a_dark_halo_round_light_text(self):
        px, box = self.painter.text_pixels(self.cfg, [line("I")])
        alphas = [self.alpha(px, box, x, y) for y in range(box[1], box[1] + box[3]) for x in range(box[0], box[0] + box[2])]
        self.assertTrue(any(a == 255 for a in alphas))  # the letter
        dark = [px[i:i + 3] for i in range(0, len(px), 4) if 100 < px[i + 3] < 255 and max(px[i:i + 3]) < 60]
        self.assertTrue(dark)  # the halo: dark and partly see-through

    def test_an_outline_instead_of_the_halo(self):
        px, _ = self.painter.text_pixels({**self.cfg, "outline": 2, "outlineColor": "#FF0000"}, [line("I")])
        reds = [i for i in range(0, len(px), 4) if px[i + 2] > 200 and px[i] < 40 and px[i + 3] > 200]  # B, G, R, A
        self.assertTrue(reds)

    def test_a_see_through_background(self):
        cfg = {**self.cfg, "background": "#000000", "bgOpacity": 50}
        px, box = self.painter.text_pixels(cfg, [line("I")])
        self.assertIn(self.alpha(px, box, 100 - 8, 50 - 8), range(120, 136))  # inside the padding: half see-through

    def test_a_flashing_part_out_of_its_turn_keeps_its_place_in_another_colour(self):
        lines = [line("W", parts=[("W", "#FF0000", True, "#00FF00")])]
        lit, box = self.painter.text_pixels(self.cfg, lines, True)
        dark, box2 = self.painter.text_pixels(self.cfg, lines, False)
        self.assertEqual(box, box2)
        self.assertEqual([i for i in range(3, len(lit), 4) if lit[i]], [i for i in range(3, len(dark), 4) if dark[i]])  # the same pixels
        self.assertNotEqual(lit, dark)  # in another colour

    def test_a_blinking_line_out_of_its_turn(self):
        lines = [line("W", blinks=True)]
        lit, box = self.painter.text_pixels(self.cfg, lines, True)
        dark, _ = self.painter.text_pixels(self.cfg, lines, False)
        self.assertGreater(max(lit[3::4]), 0)
        self.assertEqual(max(dark[3::4]), 0)

    def test_nothing_to_show(self):
        self.assertIsNone(self.painter.text_box(self.cfg, []))


if __name__ == "__main__":
    unittest.main()
