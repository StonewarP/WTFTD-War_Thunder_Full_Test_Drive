"""Settings → Uninstall: only what WTFTD put on the PC goes, part by part (temporary folders only)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wtftd import cdk, uninstall


class Uninstall(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.home, self.game = root / "home", root / "War Thunder"
        self.cache, self.data, self.user = self.home / ".cache", self.home / "data", self.home / "user"
        for d in (self.cache / "datamine", self.cache / "app-window", self.data, self.user / "missions", self.game / "UserMissions"):
            d.mkdir(parents=True)
        (self.cache / "datamine" / "a.blkx").write_text("x" * 100)
        (self.cache / "app-window" / "Preferences").write_text("{}")
        (self.data / "vehicles.json").write_text("[]")
        (self.user / "settings.json").write_text("{}")
        (self.user / "missions" / "my_custom_name.json").write_text("{}")
        cdk._manifest_path(self.user).write_text(json.dumps([]))
        um = self.game / "UserMissions"
        for name in ("wtftd_f_14b.blk", "my_custom_name.blk", "someone_elses.blk"):
            (um / name).write_text("mission")
        for name, value in (("CACHE", self.cache), ("DATA", self.data), ("USER", self.user), ("HOME", self.home)):
            p = mock.patch.object(uninstall, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(uninstall.game, "user_missions_dir", lambda gd: gd / "UserMissions")
        p.start()
        self.addCleanup(p.stop)

    def test_missions_are_only_wtftd_ones(self):
        names = [p.name for p in uninstall.mission_files(self.game)]
        self.assertEqual(names, ["my_custom_name.blk", "wtftd_f_14b.blk"])  # not someone else's mission

    def test_info(self):
        i = uninstall.info(self.game)
        self.assertEqual(i["missions"]["files"], 2)
        self.assertEqual(i["cache"]["bytes"], 102)
        self.assertFalse(i["app"]["available"])  # from the source code: the app is never removed

    def test_parts(self):
        res = uninstall.run(["missions", "cache", "user"], self.game)
        self.assertFalse(res["quit"])
        self.assertEqual(res["removed"]["missions"], 2)
        self.assertTrue((self.game / "UserMissions" / "someone_elses.blk").exists())
        self.assertFalse((self.cache / "datamine").exists())
        self.assertTrue((self.cache / "app-window").exists())  # in use while the app window is open
        self.assertTrue(self.data.exists())  # not chosen
        # the custom vehicle files stay in the game: their manifest stays too, to remove them later
        self.assertEqual([p.name for p in self.user.iterdir()], ["cdk_manifest.json"])

    def test_user_with_cdk_goes_entirely(self):
        uninstall.run(["cdk", "user"], self.game)
        self.assertFalse(self.user.exists())


@unittest.skipUnless(__import__("sys").platform == "win32", "Windows script")
class AfterExitScript(unittest.TestCase):
    def test_retries_without_console_tools(self):
        launched = []
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(uninstall.subprocess, "Popen", lambda args, **kw: launched.append((args, kw))), \
                mock.patch.object(uninstall.tempfile, "gettempdir", lambda: tmp):
            uninstall._after_exit([Path(tmp) / "WTFTD.exe"], pid=1234)
            args, kw = launched[0]
            text = Path(args[-1]).read_text(encoding="utf-8")
        # a hidden console: without any (DETACHED_PROCESS), Windows opened a visible one for ping (0.17.0)
        self.assertFalse(kw["creationflags"] & 0x00000008)
        self.assertTrue(kw["creationflags"] & 0x08000000)  # CREATE_NO_WINDOW
        self.assertEqual(kw["startupinfo"].wShowWindow, 0)
        self.assertNotIn("tasklist", text)  # hangs in a process without a console
        self.assertNotIn("timeout ", text)  # fails at once there
        self.assertIn(r'"%SystemRoot%\System32\PING.EXE" -n 3', text)
        self.assertIn("WTFTD.exe", text)


@unittest.skipIf(__import__("sys").platform == "win32", "macOS / Linux script")
class AfterExitShell(unittest.TestCase):
    def test_removes_once_the_app_has_closed(self):
        import subprocess
        import sys
        import time
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            app, home = t / "WTFTD.app", t / "home with space's"
            (app / "Contents" / "MacOS").mkdir(parents=True)
            (home / ".cache").mkdir(parents=True)
            (home / ".cache" / "log").write_text("x")
            holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])  # stands for WTFTD
            uninstall._after_exit([app, home], pid=holder.pid)
            time.sleep(1)
            self.assertTrue(app.exists())  # WTFTD still running
            holder.wait()
            for _ in range(20):
                if not app.exists() and not home.exists():
                    break
                time.sleep(0.5)
            self.assertFalse(app.exists())
            self.assertFalse(home.exists())

    def test_translocated_app_is_not_removed(self):
        with mock.patch.object(uninstall, "FROZEN", True), mock.patch.object(uninstall.sys, "platform", "darwin"), \
                mock.patch.object(uninstall.sys, "executable", "/private/var/folders/x/AppTranslocation/ABC/d/WTFTD.app/Contents/MacOS/WTFTD"):
            self.assertTrue(uninstall.translocated())
            self.assertIsNone(uninstall.app_path())
        with mock.patch.object(uninstall, "FROZEN", True), mock.patch.object(uninstall.sys, "platform", "darwin"), \
                mock.patch.object(uninstall.sys, "executable", "/Applications/WTFTD.app/Contents/MacOS/WTFTD"):
            self.assertEqual(uninstall.app_path(), Path("/Applications/WTFTD.app"))
