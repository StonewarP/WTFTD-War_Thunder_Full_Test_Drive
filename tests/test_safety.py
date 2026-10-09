"""Safety rules: custom vehicle files stay in their folders, mission names stay plain, the local server
only answers its own page."""
import tempfile
import unittest
from pathlib import Path

from wtftd import cdk, mission, server


class CustomVehicleFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.game = Path(self.tmp.name) / "War Thunder"
        self.user = Path(self.tmp.name) / "user"
        (self.game / "content").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_refuses_paths_outside_its_folders(self):
        for rel in ("../aces.vromfs.bin", "../../evil.blk", "../pkg_main/x.blk"):
            with self.assertRaises(cdk.CdkError):
                cdk.write_files(self.game, self.user, {rel: "x"})

    def test_writes_lists_and_cleans_up(self):
        rel = "gameData/units/tankModels/userVehicles/us_m2a4.blk"
        cdk.write_files(self.game, self.user, {rel: "// WTFTD\n"})
        target = self.game / "content" / "pkg_local" / rel
        self.assertTrue(target.exists())
        self.assertIn(f"pkg_local/{rel}", cdk.read_manifest(self.user))
        self.assertGreaterEqual(cdk.cleanup(self.game, self.user), 1)
        self.assertFalse(target.exists())


class MissionNames(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(mission.safe_name("T-80BVM / Fulda: test"), "T-80BVM_Fulda_test")
        self.assertEqual(mission.safe_name("../../x"), "x")
        self.assertEqual(mission.safe_name("///"), "mission")
        self.assertLessEqual(len(mission.safe_name("a" * 300)), 80)


class FakeHandler:
    local_origin = server.Handler.local_origin

    def __init__(self, host, origin=None):
        self.headers = {"Host": host, **({"Origin": origin} if origin else {})}


class LocalServer(unittest.TestCase):
    def test_own_page_is_allowed(self):
        self.assertTrue(FakeHandler("127.0.0.1:8777").local_origin())
        self.assertTrue(FakeHandler("localhost:8777", "http://localhost:8777").local_origin())

    def test_other_sites_are_refused(self):
        self.assertFalse(FakeHandler("evil.example.com").local_origin())  # DNS rebinding
        self.assertFalse(FakeHandler("127.0.0.1:8777", "https://evil.example.com").local_origin())  # cross-site request


if __name__ == "__main__":
    unittest.main()


class UnbreakableAirframe(unittest.TestCase):
    def test_breaking_limits_raised(self):
        from wtftd import cdk
        fm = {"Vne": 760.0, "VneMach": 0.82, "VneControl": 600.0,
              "Mass": {"WingCritOverload": [-87500.0, 150000.0], "GearDestructionIndSpeed": 270.0,
                       "AirbrakeDestructionIndSpeed": -1.0, "FlapsDestructionIndSpeedP1": [0.5, 290.0]},
              "Aerodynamics": {"WingPlaneSweep0": {"Strength": {"VNE": 1021.0, "MNE": 0.96, "CritOverload": [-6.0, 13.0]}}}}
        tree = cdk._structural_overrides(fm)
        self.assertEqual(tree[("Vne",)], ("r", cdk.NO_BREAK_SPEED))
        self.assertEqual(tree[("VneMach",)], ("r", 100.0))
        self.assertEqual(tree[("Aerodynamics", "WingPlaneSweep0", "Strength", "MNE")], ("r", 100.0))  # wings' Mach limit
        self.assertNotIn(("VneControl",), tree)  # control stiffness, not a breaking limit
        self.assertEqual(tree[("Mass", "WingCritOverload")], ("p2", [-8750000.0, 15000000.0]))
        self.assertNotIn(("Mass", "AirbrakeDestructionIndSpeed"), tree)  # -1: never breaks already
        self.assertEqual(tree[("Mass", "FlapsDestructionIndSpeedP1")], ("p2", [0.5, cdk.NO_BREAK_SPEED]))
        self.assertEqual(tree[("Aerodynamics", "WingPlaneSweep0", "Strength", "CritOverload")], ("p2", [-600.0, 1300.0]))
        b = cdk.Blk()
        cdk._write_tree(b, tree)
        text = str(b)
        self.assertEqual(text.count('"@override:Mass"{'), 1)
        self.assertIn('"@override:Aerodynamics"{', text)


class JetThrust(unittest.TestCase):
    def test_thrust_table_base_scaled(self):
        from wtftd import cdk
        det = {"st": {"fm": "fm/x.blk", "thrust": 6000.0}}
        fm = {"EngineType0": {"Main": {"Thrust": 6000.0, "ThrustMax": {"ThrustMax0": 6260.0, "ThrustMaxCoeff_0_0": 0.99}}},
              "Engine0": {"Main": {"FuelSystemNum": 0}}}
        files = cdk.build_files("x", "air", det, {"thrustMul": 3}, "", None, "custom", None, {}, fm_data=fm)[0]
        text = files["gameData/flightModels/fm/wtftd_x.blk"]
        self.assertIn('"@override:ThrustMax0":r=18780', text)  # what the game uses for a jet's maximum thrust
        self.assertNotIn("Engine0", text)


class SuperMobility(unittest.TestCase):
    def test_aircraft_engines_and_mass(self):
        from wtftd import cdk
        fm = {"EngineType0": {"Main": {"Type": "Jet", "Power": 1122.0, "ThrustMax": {"ThrustMax0": 6000.0}}},
              "Engine0": {"Main": {"Type": "Inline", "Power": 900.0},
                          "Compressor": {"Power0": 1020.0, "PowerConstRPM0": 200.0, "PowerAtCeiling0": 500.0,
                                         "PowerConstRPMCurvature0": 0.5}}}
        tree = cdk._power_overrides(fm, 3.0)
        self.assertEqual(tree, {("EngineType0", "Main", "ThrustMax", "ThrustMax0"): ("r", 18000.0),
                                ("Engine0", "Main", "Power"): ("r", 2700.0),
                                ("Engine0", "Compressor", "Power0"): ("r", 3060.0),
                                ("Engine0", "Compressor", "PowerConstRPM0"): ("r", 600.0),
                                ("Engine0", "Compressor", "PowerAtCeiling0"): ("r", 1500.0)})
        det = {"st": {"fm": "fm/x.blk", "mass": 1000.0}}
        files = cdk.build_files("x", "air", det, {"superMobility": True}, "", None, "custom", None, {}, fm_data=fm)[0]
        self.assertIn('"@override:EmptyMass":r=600', files["gameData/flightModels/fm/wtftd_x.blk"])  # 40 % lighter
