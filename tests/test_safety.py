"""Safety rules: custom vehicle files stay in their folders, mission names stay plain, the local server
only answers its own page."""
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from wtftd import cdk, mission, server, uninstall


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

    def test_a_file_of_another_tool_comes_back_at_cleanup(self):  # kept aside when written over, then deleted with ours: lost
        rel = "gameData/units/tankModels/userVehicles/us_m2a4.blk"
        target = self.game / "content" / "pkg_local" / rel
        target.parent.mkdir(parents=True)
        target.write_text("their vehicle\n")
        for _ in range(2):  # the second time over our own file: theirs stays the one kept
            cdk.write_files(self.game, self.user, {rel: f"{cdk.MARKER}\n"})
        self.assertEqual(target.read_text(), f"{cdk.MARKER}\n")
        cdk.cleanup(self.game, self.user)
        self.assertEqual(target.read_text(), "their vehicle\n")
        cdk.cleanup(self.game, self.user)  # once only: nothing else to put back
        self.assertEqual(target.read_text(), "their vehicle\n")

    def test_lower_case_on_every_system(self):  # the Linux client tells cases apart
        files = cdk.build_files("x", "air", {"st": {"fm": "fm/x.blk"}}, {}, "", None, "custom")[0]
        self.assertEqual(sorted(files), ["gamedata/flightModels/fm/wtftd_x.blk", "gamedata/flightModels/wtftd_x.blk"])

    def test_an_old_copy_in_the_other_package_goes_whatever_its_case(self):  # written as gameData until 0.30.0
        old = "gameData/flightModels/fm/wtftd_x.blk"
        cdk.write_files(self.game, self.user, {old: "// WTFTD\n"}, "pkg_local")
        cdk.write_files(self.game, self.user, {"gamedata/flightModels/fm/wtftd_x.blk": "// WTFTD\n"}, "pkg_user")
        self.assertFalse((self.game / "content" / "pkg_local" / old).exists())  # it would shadow the new one
        self.assertEqual(cdk.read_manifest(self.user), ["pkg_user/gamedata/flightModels/fm/wtftd_x.blk"])


class MissionNames(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(mission.safe_name("T-80BVM / Fulda: test"), "T-80BVM_Fulda_test")
        self.assertEqual(mission.safe_name("../../x"), "x")
        self.assertEqual(mission.safe_name("///"), "mission")
        self.assertLessEqual(len(mission.safe_name("a" * 300)), 80)

    def test_names_in_other_alphabets_stay_apart(self):  # "Тигр" and "虎式" both gave mission.blk: the second replaced the first
        names = {mission.safe_name(s) for s in ("Тигр тест", "Пантера", "虎式", "Mission été", "Mission ete", "é" * 300)}
        self.assertEqual(len(names), 6)
        self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", n) for n in names), names)
        self.assertEqual(mission.safe_name("Пантера"), mission.safe_name("Пантера"))  # made again: the same file


class SavedFiles(unittest.TestCase):
    def test_saves_from_two_threads_at_once(self):  # one settings.tmp for both: refused replaces, a short body over a long one
        with tempfile.TemporaryDirectory() as d:
            path, errors, datas = Path(d) / "settings.json", [], ({"k": "x"}, {"k": "x" * 5000})

            def save(data):
                for _ in range(200):
                    try:
                        server.write_json(path, data)
                    except OSError as e:
                        errors.append(e)
            threads = [threading.Thread(target=save, args=(x,)) for x in datas]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            self.assertIn(server.read_json(path, None), datas)

    def test_a_file_held_a_moment_is_saved_after_all(self):  # Windows refuses the replace while a reader or an antivirus holds it
        real, calls = Path.replace, []

        def held(self, target):
            calls.append(target)
            if len(calls) == 1:
                raise PermissionError(13, "held")
            return real(self, target)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(Path, "replace", held), mock.patch.object(server.time, "sleep"):
            server.write_json(Path(d) / "x.json", {"a": 1})
            self.assertEqual(server.read_json(Path(d) / "x.json", None), {"a": 1})
        self.assertEqual(len(calls), 2)

    def test_two_setting_changes_at_once_keep_both(self):  # each read the file, then saved its copy: one change was lost
        handler, real = mock.Mock(), server.STATE.settings

        def slow():
            s = real()
            time.sleep(0.05)
            return s
        with tempfile.TemporaryDirectory() as d, mock.patch.object(server, "USER", Path(d)), mock.patch.object(server.STATE, "settings", slow), \
                mock.patch.object(server, "api_status", dict), mock.patch.object(server, "apply_alarm_settings"):
            threads = [threading.Thread(target=server.Handler.post_api, args=(handler, "settings", b)) for b in ({"theme": "dark"}, {"lang": "fr"})]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(server.read_json(Path(d) / "settings.json", {}), {"theme": "dark", "lang": "fr"})


class AppUninstall(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "the .cmd script is Windows' way")
    def test_paths_with_any_letters_are_removed(self):  # cmd reads a .cmd in the console's code page: C:\Users\Jérôme was missed
        with tempfile.TemporaryDirectory() as d:
            folder, exe = Path(d) / "Jérôme" / "WTFTD", Path(d) / "Тест 100%" / "WTFTD.exe"
            folder.mkdir(parents=True)
            (folder / "settings.json").write_text("{}")
            exe.parent.mkdir()
            exe.write_bytes(b"MZ")
            with mock.patch.object(uninstall, "AFTER_EXIT_DELAY", 0), mock.patch.object(uninstall.tempfile, "gettempdir", lambda: d), \
                    mock.patch.object(uninstall.subprocess, "Popen") as popen:
                uninstall._after_exit([folder, exe], pid=1)
            subprocess.run(popen.call_args.args[0], env=popen.call_args.kwargs.get("env"), timeout=30, stdout=subprocess.DEVNULL)
            self.assertFalse(folder.exists())
            self.assertFalse(exe.exists())


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

    def test_a_network_path_in_a_url_is_never_opened(self):  # any page's <img>: resolve() would reach \\host (NTLM)
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        opened, resolve = [], Path.resolve

        def watch(p, *a, **k):
            if server.on_network(p):
                opened.append(str(p))
                return p  # the test never touches the network
            return resolve(p, *a, **k)

        port = httpd.server_address[1]
        with mock.patch.object(Path, "resolve", watch):
            for url in ("/%5C%5Cevil%5Cs%5Cx", "/data///evil/share/a.json", "/data/%5C%5Cevil%5Cs%5Ca.json"):
                with self.subTest(url), self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}{url}", timeout=10)
                self.assertEqual(e.exception.code, 404)
                e.exception.close()
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()


class ThePage(unittest.TestCase):
    def test_it_runs_only_the_apps_own_scripts(self):
        self.assertIn("script-src 'self';", server.CSP)
        self.assertIn("connect-src 'self';", server.CSP)

    def test_nothing_inline_for_the_policy_to_stop(self):
        web = Path(server.__file__).parent.parent / "web"
        for f in [*web.glob("*.html"), *web.glob("*.js")]:
            text = f.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"""\son[a-z]+=["']""", f.name)
            self.assertNotRegex(text, r"<script(?![^>]*\ssrc=)", f.name)

    def test_network_paths_are_refused(self):
        for p in (r"\\host\share\oo2core_9_win64.dll", "//host/share/a.dll", r"\\host@80\s\a.dll", r"\\?\UNC\host\s\a.dll", r"/\host\s\a.dll"):
            self.assertTrue(server.on_network(p), p)
        for p in (r"C:\Games\oo2core_9_win64.dll", "D:/War Thunder", "~/oodle.dylib", "/Applications/x", "", None):
            self.assertFalse(server.on_network(p), p)


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
        text = files[f"{cdk.game_data_root()}/flightModels/fm/wtftd_x.blk"]
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
        self.assertIn('"@override:EmptyMass":r=600', files[f"{cdk.game_data_root()}/flightModels/fm/wtftd_x.blk"])  # 40 % lighter


class CustomPylonWeapons(unittest.TestCase):
    def test_modified_copy_of_the_weapon(self):
        aim = {"p": "gameData/Weapons/rocketguns/us_aim9l_sidewinder.blk", "c": "aam_ir", "g": "ir", "t": "aam"}
        text = cdk._custom_weapon(aim, {"e": 50, "force": 54000, "g": 100, "gReq": 100}, "x")
        self.assertIn('include "#/develop/gameBase/gameData/Weapons/rocketguns/us_aim9l_sidewinder.blk"', text)
        self.assertIn('"@override:rocket"{', text)
        self.assertIn('"@override:explosiveMass":r=50', text)
        self.assertIn('"@override:loadFactorMax":r=100', text)
        self.assertIn('"@override:reqAccelMax":r=100', text)
        bomb = {"p": "gameData/Weapons/bombguns/us_500lb_mk_82_ldgp.blk", "c": "bombs", "g": "", "t": "bombs"}
        text = cdk._custom_weapon(bomb, {"e": 10000, "g": 100}, "x")
        self.assertIn('"@override:bomb"{', text)
        self.assertIn('"@override:explosionFx":t="bomb_expl_5000kg"', text)  # the explosion of a bomb that size
        text = cdk._custom_weapon(aim, {"e": 500}, "x")
        self.assertIn('"@override:explosionEffect":t="explosion_midair_rocket_big"', text)
        self.assertIn('explosionFx:t="bomb_expl_1000kg"', text)
        self.assertNotIn("loadFactorMax", text)  # unguided: no autopilot to override
        text = cdk._custom_weapon(bomb, {"kt": 20}, "x")
        self.assertIn("yield:r=20", text)  # a nuclear charge: new values, the Mk 82 has none
        self.assertIn("splashFallBySquare:b=yes", text)
        self.assertIsNone(cdk._custom_weapon(bomb, {}, "x"))
        self.assertIsNone(cdk._custom_weapon(dict(bomb, pod=6), {"e": 1}, "x"))  # launchers: not yet
        with self.assertRaises(cdk.CdkError):
            cdk._custom_weapon(bomb, {"e": -1}, "x")



class MyWeapons(unittest.TestCase):
    def test_pylons_take_the_weapons_current_changes(self):
        saved = [{"id": "a1", "w": "us_aim9l_sidewinder", "mod": {"e": 500}}]
        real = server.read_json
        server.read_json = lambda path, default: saved if path.name == "weapons.json" else real(path, default)
        try:
            out = server.custom_weapons({"1": {"w": "us_aim9l_sidewinder", "n": 1, "cw": "a1", "mod": {"e": 50}},
                                         "2": {"w": "x", "n": 1, "cw": "gone", "mod": {"e": 7}}, "3": "aim_9l"})
        finally:
            server.read_json = real
        self.assertEqual(out["1"]["mod"], {"e": 500})  # edited since: the current changes
        self.assertEqual(out["2"]["mod"], {"e": 7})    # deleted: the changes saved with the pylon
        self.assertEqual(out["3"], "aim_9l")

    def test_value_tree_of_a_weapon_file(self):
        tree = server.weapon_tree({"rocket": {"mass": 84.5, "bullets": 1, "on": True, "fx": "a_b", "bad": "x\"y",
                                              "p": [1.0, 2.0], "ints": [1, 2], "rep": [{"a": 1}], "guidance": {"workTime": 20.0}}})
        self.assertIn(["rocket/mass", "r", 84.5], tree)
        self.assertIn(["rocket/bullets", "i", 1], tree)
        self.assertIn(["rocket/on", "b", True], tree)
        self.assertIn(["rocket/p", "p2", [1.0, 2.0]], tree)
        self.assertIn(["rocket/guidance/workTime", "r", 20.0], tree)
        paths = {p for p, _, _ in tree}
        self.assertFalse({"rocket/bad", "rocket/ints", "rocket/rep"} & paths)  # unsafe text, int points, repeated blocks


class AircraftHandling(unittest.TestCase):
    def test_roll_pitch_turn_drag(self):
        from wtftd import cdk
        fm = {"MomentOfInertia": [5500.0, 15500.0, 10000.0], "AileronEffectiveSpeed": 450.0,
              "ElevatorsEffectiveSpeed": [450.0, 450.0], "Areas": {"Aileron": 0.89, "Wing": 16.0},
              "Aerodynamics": {"NoFlaps": {"ClCritHigh": 1.2, "CdMin": 0.01}, "Fuselage": {"ClCritHigh": 0.2, "CdMin": 0.01},
                               "WingPlane": {"FlapsPolar0": {"ClCritHigh": 1.7}}, "HorStabPlane": {"Areas": {"Elevator": 12.0}}}}
        t = cdk._handling_overrides(fm)
        self.assertEqual(t[("MomentOfInertia",)], ("p3", [2200.0, 6200.0, 4000.0]))
        self.assertEqual(t[("ElevatorsEffectiveSpeed",)], ("p2", [900.0, 900.0]))
        self.assertEqual(t[("Areas", "Aileron")], ("r", 0.89 * 1.5))
        self.assertNotIn(("Areas", "Wing"), t)
        self.assertEqual(t[("Aerodynamics", "NoFlaps", "ClCritHigh")], ("r", 1.2 * 1.3))
        self.assertNotIn(("Aerodynamics", "Fuselage", "ClCritHigh"), t)  # the wing's lift only
        self.assertEqual(t[("Aerodynamics", "Fuselage", "CdMin")], ("r", 0.005))
        self.assertIn(("Aerodynamics", "WingPlane", "FlapsPolar0", "ClCritHigh"), t)
        self.assertIn(("Aerodynamics", "HorStabPlane", "Areas", "Elevator"), t)


class AppWindowLifetime(unittest.TestCase):
    """WTFTD serves while its page lives, even when the browser process it started ended at once (Edge handing
    its window to another of its processes)."""

    def test_waits_for_the_page(self):
        import time
        from unittest import mock
        from wtftd import server
        with mock.patch.dict(server.PAGE, {"seen": 0.0, "bye": 0.0}):
            t0 = time.time()
            server.wait_page_gone(first=0.2, silence=60)  # the page never loaded
            self.assertLess(time.time() - t0, 3)
            server.PAGE.update(seen=time.time() - 0.5, bye=time.time() - 0.4)  # it said bye
            with mock.patch.object(server, "page_closed", lambda: True):
                server.wait_page_gone(first=0.2, silence=60)
            server.PAGE.update(seen=time.time() - 120, bye=0.0)  # silent for 2 minutes
            server.wait_page_gone(first=0.2, silence=60)


class FirstDownloadConsent(unittest.TestCase):
    def test_no_data_waits_for_the_user(self):
        from unittest import mock
        from wtftd import server
        started = []
        with mock.patch.object(server, "remote_version", lambda: "2.59.0.61"), \
                mock.patch.object(server, "read_json", lambda p, d=None: {}), \
                mock.patch.object(server.threading, "Thread", lambda **kw: started.append(kw) or mock.Mock()), \
                mock.patch.dict(server.STATE.update, {"running": False}):
            available = server.check_for_update(start=True)["available"]
        self.assertTrue(available)
        self.assertEqual(started, [])  # first install: the welcome screen's button starts it
