"""Windows / macOS differences: where the game files are, which Oodle runtime file names count."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wtftd import game, maptex


class GameFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "War Thunder"

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, rel: Path) -> Path:
        files = self.root / rel
        files.mkdir(parents=True)
        (files / "aces.vromfs.bin").write_bytes(b"")
        return files

    def test_windows_layout(self):
        files = self.install(Path("."))
        self.assertEqual(game.resolve_game_dir(self.root), files)

    def test_mac_layout_from_any_level(self):
        files = self.install(game.MAC_GAME)
        for start in (self.root, self.root / "WarThunderLauncher.app",
                      self.root / "WarThunderLauncher.app/Contents/WarThunder.app", files):
            self.assertEqual(game.resolve_game_dir(start), files, start)

    def test_not_a_game_folder(self):
        self.root.mkdir()
        self.assertIsNone(game.resolve_game_dir(self.root))

    def test_mac_launcher_app(self):
        files = self.install(game.MAC_GAME)
        self.assertEqual(game._mac_app(files), self.root / "WarThunderLauncher.app")
        self.assertIsNone(game._mac_app(self.root))


class OodleNames(unittest.TestCase):
    def test_windows(self):
        with mock.patch.object(sys, "platform", "win32"):
            self.assertEqual(maptex.oodle_version("oo2core_9_win64.dll"), 9)
            self.assertIsNone(maptex.oodle_version("liboo2coremac64.2.9.dylib"))

    def test_mac(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(maptex.oodle_version("liboo2coremac64.2.9.dylib"), 9)
            self.assertEqual(maptex.oodle_version("liboo2coremac64.2.9.10.dylib"), 9)
            self.assertIsNone(maptex.oodle_version("oo2core_9_win64.dll"))
            self.assertIsNone(maptex.oodle_version("libfoo.dylib"))


if __name__ == "__main__":
    unittest.main()
