"""One-click update (selfupdate): the release's file for this system, checked against its published SHA-256, in the place of
the running app, which starts it and closes; the new one removes the old once that one has gone."""
import hashlib
import io
import os
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from wtftd import REPO, __main__ as app, selfupdate, server

BASE = f"https://github.com/{REPO}/releases/download/v9.0.0-beta/"


class Response(io.BytesIO):
    def __init__(self, body: bytes):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}


class Update(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.files: dict = {}  # url -> body, what "GitHub" serves

    def serve(self, name: str, body: bytes, digest: str | None = None):
        self.files[BASE + name] = body
        self.files[BASE + name + ".sha256"] = f"{digest or hashlib.sha256(body).hexdigest()}  {name}\n".encode()
        return BASE + name

    def opened(self, url, ua):
        if url not in self.files:
            raise selfupdate.UpdateError("file")
        return Response(self.files[url])

    def run_update(self, platform: str, app: Path, url: str, start=None):
        with mock.patch.object(selfupdate.sys, "platform", platform), mock.patch.object(selfupdate, "target", lambda: app), \
                mock.patch.object(selfupdate, "_open", self.opened), mock.patch.object(selfupdate, "_start", start or mock.Mock()) as started:
            selfupdate.update(url, "ua", ["prefix"])
        return started

    def test_windows_exe_takes_the_place_of_the_running_one(self):  # same name and place: shortcuts and Steam's line still work
        exe = self.root / "WTFTD-0.32.2-windows.exe"
        exe.write_bytes(b"old")
        started = self.run_update("win32", exe, self.serve("WTFTD-9.0.0-windows.exe", b"new"))
        self.assertEqual(exe.read_bytes(), b"new")
        (_, old, prefix), _ = started.call_args
        self.assertEqual((old.parent, old.read_bytes(), prefix), (self.root, b"old", ["prefix"]))
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), sorted([exe.name, old.name]))  # nothing else left

    def test_linux_binary_from_its_tar(self):
        binary = self.root / "WTFTD"
        binary.write_bytes(b"old")
        started = self.run_update("linux", binary, self.serve("WTFTD-9.0.0-linux.tar.gz", tgz({"WTFTD": b"new"})))
        self.assertEqual(binary.read_bytes(), b"new")
        if os.name != "nt":
            self.assertTrue(os.access(binary, os.X_OK))
        self.assertEqual(started.call_args.args[1].read_bytes(), b"old")

    def test_macos_bundle_from_its_zip(self):
        bundle = self.root / "WTFTD.app"
        (bundle / "Contents" / "MacOS").mkdir(parents=True)
        (bundle / "Contents" / "MacOS" / "WTFTD").write_bytes(b"old")
        url = self.serve("WTFTD-9.0.0-macos.zip", zipped({"WTFTD.app/Contents/MacOS/WTFTD": b"new"}))

        def ditto(args, **kw):  # macOS' own unzip (keeps the bundle's links and modes): its result, here
            self.assertEqual(args[:3], ["ditto", "-x", "-k"])
            with zipfile.ZipFile(args[3]) as z:
                z.extractall(args[4])
        with mock.patch.object(selfupdate.subprocess, "run", ditto):
            started = self.run_update("darwin", bundle, url)
        self.assertEqual((bundle / "Contents" / "MacOS" / "WTFTD").read_bytes(), b"new")
        old = started.call_args.args[1]
        self.assertEqual((old / "Contents" / "MacOS" / "WTFTD").read_bytes(), b"old")
        self.assertTrue(old.name.startswith("."))  # hidden in Applications until it goes

    def test_a_file_that_doesnt_match_its_sha256_changes_nothing(self):
        exe = self.root / "WTFTD.exe"
        exe.write_bytes(b"old")
        with self.assertRaises(selfupdate.UpdateError) as e:
            self.run_update("win32", exe, self.serve("WTFTD-9.0.0-windows.exe", b"new", digest="0" * 64))
        self.assertEqual(e.exception.code, "check")
        self.assertEqual([p.name for p in self.root.iterdir()], ["WTFTD.exe"])
        self.assertEqual(exe.read_bytes(), b"old")

    def test_only_this_repositorys_releases(self):
        exe = self.root / "WTFTD.exe"
        exe.write_bytes(b"old")
        for url in ("https://example.com/WTFTD-9.0.0-windows.exe", f"https://github.com/someone/else/releases/download/v9/WTFTD-9.0.0-windows.exe",
                    BASE + "WTFTD-9.0.0-linux.tar.gz"):  # another system's file
            with self.subTest(url=url), self.assertRaises(selfupdate.UpdateError) as e:
                self.run_update("win32", exe, url)
            self.assertEqual(e.exception.code, "file")
        self.assertFalse(selfupdate._github("https://evil.example.com/x"))
        self.assertFalse(selfupdate._github("http://github.com/x"))  # no plain http on the way
        self.assertTrue(selfupdate._github("https://release-assets.githubusercontent.com/x"))

    def test_a_tar_holding_anything_else_is_refused(self):
        binary = self.root / "WTFTD"
        binary.write_bytes(b"old")
        for body in (tgz({"other": b"x"}), tgz({}, link="WTFTD")):
            with self.subTest(), self.assertRaises(selfupdate.UpdateError) as e:
                self.run_update("linux", binary, self.serve("WTFTD-9.0.0-linux.tar.gz", body))
            self.assertEqual(e.exception.code, "file")
        self.assertEqual(binary.read_bytes(), b"old")

    def test_a_new_one_that_cant_start_gives_the_old_one_back(self):
        exe = self.root / "WTFTD.exe"
        exe.write_bytes(b"old")
        with self.assertRaises(selfupdate.UpdateError) as e:
            self.run_update("win32", exe, self.serve("WTFTD-9.0.0-windows.exe", b"new"), start=mock.Mock(side_effect=OSError))
        self.assertEqual(e.exception.code, "start")
        self.assertEqual([p.name for p in self.root.iterdir()], ["WTFTD.exe"])
        self.assertEqual(exe.read_bytes(), b"old")

    def test_a_folder_it_cant_write_in(self):
        exe = self.root / "WTFTD.exe"
        exe.write_bytes(b"old")
        with mock.patch.object(Path, "mkdir", side_effect=PermissionError), self.assertRaises(selfupdate.UpdateError) as e:
            self.run_update("win32", exe, self.serve("WTFTD-9.0.0-windows.exe", b"new"))
        self.assertEqual(e.exception.code, "folder")

    def test_none_from_the_source_code(self):
        with mock.patch.object(selfupdate.uninstall, "FROZEN", False):
            self.assertIsNone(selfupdate.target())
            with self.assertRaises(selfupdate.UpdateError) as e:
                selfupdate.update(BASE + "WTFTD-9.0.0-windows.exe", "ua")
        self.assertEqual(e.exception.code, "source")

    def test_how_the_new_one_starts(self):
        app_, old = self.root / "WTFTD", self.root / ".WTFTD.1.old"
        with mock.patch.object(selfupdate.subprocess, "Popen") as popen, mock.patch.object(selfupdate.subprocess, "run") as run:
            with mock.patch.object(selfupdate.sys, "platform", "linux"):
                selfupdate._start(app_, old, ["systemd-run", "--"])  # its own service: this one's ends with it
            self.assertEqual(popen.call_args.args[0], ["systemd-run", "--", str(app_), "--updated", str(old)])
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
            with mock.patch.object(selfupdate.sys, "platform", "darwin"):
                selfupdate._start(self.root / "WTFTD.app", old, [])
            self.assertEqual(run.call_args.args[0], ["open", "-n", str(self.root / "WTFTD.app"), "--args", "--updated", str(old)])


class Replaced(unittest.TestCase):
    """The new WTFTD, started by the one it replaced (--updated <old>): that one closes first, then its file goes."""

    def test_only_what_the_update_set_aside_is_removed(self):
        with tempfile.TemporaryDirectory() as d:
            mine, folder, other = Path(d) / ".WTFTD.exe.12.old", Path(d) / ".WTFTD.app.12.old", Path(d) / "settings.json"
            mine.write_bytes(b"x")
            (folder / "Contents").mkdir(parents=True)
            other.write_text("{}")
            for p in (mine, folder, other):
                t = selfupdate.remove_later(str(p))
                if t:
                    t.join(5)
            self.assertEqual([p.name for p in Path(d).iterdir()], ["settings.json"])
            self.assertIsNone(selfupdate.remove_later(""))  # nothing set aside

    def test_it_waits_for_the_old_one_to_close(self):
        with tempfile.TemporaryDirectory() as d:
            running = Path(d) / "running.json"
            held = socket.socket()
            held.bind(("127.0.0.1", 0))
            held.listen()
            running.write_text(f'{{"port": {held.getsockname()[1]}}}')
            threading.Timer(0.6, held.close).start()
            start = time.monotonic()
            with mock.patch.object(app.selfupdate, "remove_later") as removed:
                app.replaced("old", running, wait=10)
            self.assertGreaterEqual(time.monotonic() - start, 0.5)
            removed.assert_called_once_with("old")

    @unittest.skipUnless(sys.platform == "win32", "Windows keeps a running exe's file")
    def test_windows_lets_a_running_exe_be_renamed(self):  # what the update relies on: replaced while it runs
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "ping.exe"
            exe.write_bytes(Path(os.environ["SystemRoot"], "System32", "PING.EXE").read_bytes())
            proc = subprocess.Popen([str(exe), "-n", "4", "127.0.0.1"], stdout=subprocess.DEVNULL)
            try:
                time.sleep(0.3)
                with self.assertRaises(OSError):
                    exe.unlink()  # can't be removed while it runs...
                exe.rename(exe.with_name(".ping.exe.1.old"))  # ...but can be set aside
            finally:
                proc.wait()


class Route(unittest.TestCase):
    def test_the_button_updates_then_this_one_closes(self):
        handler, latest = mock.Mock(), {"tag": "v9.0.0-beta", "exe": BASE + "WTFTD-9.0.0-windows.exe"}
        with mock.patch.object(server, "app_version", lambda: {"newer": True, "latest": latest, "canUpdate": True}), \
                mock.patch.object(server.selfupdate, "update") as updated, mock.patch.object(server.threading, "Timer") as timer:
            server.Handler.post_api(handler, "app-update", {})
        updated.assert_called_once_with(latest["exe"], server.UA, server.outside_steam())
        self.assertEqual(handler.send_json.call_args.args[0], {"ok": True, "version": "v9.0.0-beta"})
        timer.return_value.start.assert_called_once()

    def test_refused_without_a_newer_version(self):
        handler = mock.Mock()
        with mock.patch.object(server, "app_version", lambda: {"newer": False, "latest": None, "canUpdate": True}), \
                mock.patch.object(server.selfupdate, "update") as updated:
            server.Handler.post_api(handler, "app-update", {})
        updated.assert_not_called()
        self.assertEqual(handler.send_json.call_args.args[1], 400)


def tgz(files: dict, link: str | None = None) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as t:
        for name, body in files.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(body), 0o755
            t.addfile(info, io.BytesIO(body))
        if link:
            info = tarfile.TarInfo(link)
            info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            t.addfile(info)
    return out.getvalue()


def zipped(files: dict) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return out.getvalue()


if __name__ == "__main__":
    unittest.main()
