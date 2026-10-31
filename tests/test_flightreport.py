"""Flight logs: the position on the map, the Tacview file, the flight report."""
import unittest

from wtftd import alarms, flightlog

MAP = {"map_min": [-65536.0, -65536.0], "map_max": [65536.0, 65536.0]}


def me(x, y, dx, dy):
    return [{"icon": "airfield"}, {"icon": "Player", "x": x, "y": y, "dx": dx, "dy": dy}]


class Position(unittest.TestCase):
    def test_centre_facing_north(self):
        self.assertEqual(alarms.where(MAP, me(0.5, 0.5, 0.0, -1.0)), (0.0, 0.0, 0.0))

    def test_marker_share_of_the_map_and_heading_from_its_direction(self):
        # north-east quarter (y grows southwards), flying east
        self.assertEqual(alarms.where(MAP, me(0.75, 0.25, 1.0, 0.0)), (32768.0, 32768.0, 90.0))
        self.assertEqual(alarms.where(MAP, me(0.5, 0.5, -1.0, 0.0))[2], 270.0)

    def test_nothing_to_say(self):
        self.assertIsNone(alarms.where({"valid": False}, me(0.5, 0.5, 0, -1)))  # no map yet
        self.assertIsNone(alarms.where(MAP, [{"icon": "airfield"}]))  # not flying
        self.assertIsNone(alarms.where(MAP, None))


class Tacview(unittest.TestCase):
    def rows(self):
        return [{"t": float(i), "east": 1113.2 * i, "north": 0.0, "alt": 3000.0, "tas": 360.0, "vy": 10.0, "aoa": 2.0, "hdg": 90.0}
                for i in range(3)]

    def test_file(self):
        text = flightlog.acmi(self.rows(), "su_30mkk", 0)
        lines = text.splitlines()
        self.assertEqual(lines[:2], ["FileType=text/acmi/tacview", "FileVersion=2.2"])
        self.assertIn("0,ReferenceTime=1970-01-01T00:00:00Z", lines)
        self.assertIn("#1.0", lines)
        # 10 m/s climb at 100 m/s: 5.7 degrees of path, plus 2 of incidence; 1113.2 m east = 0.01 degree of longitude
        self.assertIn("1,T=0.0100000|0.0000000|3000.0||7.7|90.0", lines)
        self.assertEqual(sum("Name=su_30mkk" in x for x in lines), 1)  # the object is declared once

    def test_no_position_no_file(self):
        self.assertIsNone(flightlog.acmi([{"t": 0.0, "alt": 100.0}], "x", 0))

    def test_started_from_the_name(self):
        from pathlib import Path
        self.assertGreater(flightlog.started(Path("."), "su_30mkk-2026_10_31_12_00_00.csv"), 1.7e9)


def flight():
    rows = [{"t": float(t), "alt": 100.0 + 50 * t, "ias": 500.0 + t, "vy": 40.0, "g": 1.0, "accel": 1.0, "turn_rate": 2.0,
             "fuel": 5000.0 - t} for t in range(120)]  # climbs 50 m a second from 100 m
    rows += [{"t": 120.0 + i, "alt": 6000.0, "ias": 700.0, "vy": 0.5, "g": 4.0, "accel": 0.1, "turn_rate": 14.0, "fuel": 4880.0 - i}
             for i in range(8)]  # a turn that holds its speed
    rows += [{"t": 128.0 + i, "alt": 6000.0, "ias": 900.0, "vy": 0.5, "g": 7.0, "accel": -3.0, "turn_rate": 25.0, "fuel": 4870.0}
             for i in range(2)]  # a harder one that bleeds speed, and too short
    return rows


class Report(unittest.TestCase):
    def test_peaks_and_context(self):
        r = flightlog.report(flight())
        self.assertEqual(r["s"], 129)
        self.assertEqual(r["ias"], {"v": 900.0, "alt": 6000.0})
        self.assertEqual(r["turn"]["v"], 25.0)
        self.assertIsNone(r["mach"])  # not in the log

    def test_time_to_climb(self):
        # 1000 m after 18 s, 3000 m after 58 s, 5000 m after 98 s; 7000 m never reached
        self.assertEqual(flightlog.report(flight())["climbTo"], [[1000, 18], [3000, 58], [5000, 98]])

    def test_sustained_turn_is_level_steady_and_long_enough(self):
        s = flightlog.report(flight())["sustained"]
        self.assertEqual((s["v"], s["s"], s["g"], s["ias"]), (14.0, 8, 4.0, 700.0))  # not the 25 deg/s that bled speed

    def test_no_turn_no_sustained_turn(self):
        self.assertIsNone(flightlog.report(flight()[:100])["sustained"])

    def test_fuel_used(self):
        self.assertEqual(flightlog.report(flight())["fuel"], 130)

    def test_too_short(self):
        self.assertEqual(flightlog.report([{"t": 0.0}]), {})


if __name__ == "__main__":
    unittest.main()
