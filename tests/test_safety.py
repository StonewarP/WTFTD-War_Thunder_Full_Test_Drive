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
