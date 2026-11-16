"""New version in one click: the release's file for this system, from this repository's GitHub releases only and checked
against the SHA-256 published beside it, in the place of the running app (same name, same folder: shortcuts and Steam's
launch line keep working). The new one is started at once and waits for this one to close (__main__.replaced), then
removes it. Packaged app only: from the source code, git pull.

  Windows  WTFTD-<v>-windows.exe: a running exe can't be removed or written over, but it can be set aside (renamed)
  macOS    WTFTD-<v>-macos.zip: WTFTD.app, unpacked by ditto (a zip of Python's would lose the bundle's links and modes);
           downloaded by the app, it carries no quarantine flag. A copy macOS runs from AppTranslocation can't be replaced
  Linux    WTFTD-<v>-linux.tar.gz: the one binary WTFTD
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import REPO, uninstall

ASSET = {"win32": ".exe", "darwin": "-macos.zip", "linux": "-linux.tar.gz"}  # the release's file for each system
MAX_BYTES = 500 * 1024 * 1024
TIMEOUT = 30  # s, for each read
WORK = ".WTFTD-update"  # beside the app: the same drive, where a rename is enough


class UpdateError(Exception):
    """code: source (from the source code), file (no such file, or not what a release holds), offline, check (SHA-256),
    folder (can't write beside the app), start (the new one didn't start: the old one is back)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def target() -> Path | None:
    """What the update replaces: WTFTD.exe, the WTFTD.app bundle or the Linux binary; None from the source code or a
    translocated copy on macOS."""
    return uninstall.app_path()


def update(url: str, ua: str, prefix: list[str] | tuple = ()) -> None:
    """url: the release's file (app_version's latest.exe). The new app is in place and started, or nothing changed.
    prefix: what starts it apart from this process (Linux: systemd-run, server.outside_steam)."""
    app = target()
    if app is None:
        raise UpdateError("source")
    if not url.startswith(f"https://github.com/{REPO}/releases/download/") or not url.endswith(ASSET.get(sys.platform, "\0")):
        raise UpdateError("file")
    want = _published(url, ua)
    work = app.parent / WORK
    shutil.rmtree(work, ignore_errors=True)
    try:
        work.mkdir()
        got = work / url.rsplit("/", 1)[-1]
        if _download(url, ua, got) != want:
            raise UpdateError("check")
        old = _swap(_unpack(got, work), app)
        try:
            _start(app, old, list(prefix))
        except (OSError, subprocess.SubprocessError):
            shutil.rmtree(app) if app.is_dir() else app.unlink()
            old.rename(app)
            raise UpdateError("start") from None
    except OSError:
        raise UpdateError("folder") from None
    finally:
        shutil.rmtree(work, ignore_errors=True)


def alone_env() -> dict:
    """The environment of a WTFTD started from this one that outlives it. PyInstaller's variables passed on, a onefile exe at
    the same path runs in this one's unpacked files, which this one deletes on closing: the page gives 404."""
    return {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}


def start_alone(old: str, prefix: list[str] | tuple = ()) -> bool:
    """In the new WTFTD, first thing: 0.33.0 and 0.33.1 started it without alone_env, so it runs in their unpacked files with
    no bootloader of its own, its parent the old app (the pid in old's name). True: started again on its own, this one ends."""
    m = re.fullmatch(r"\..+\.(\d+)\.old", Path(old).name)
    app = target()
    if app is None or not m or int(m.group(1)) != os.getppid():
        return False
    try:
        _start(app, Path(old), list(prefix))
    except (OSError, subprocess.SubprocessError):  # this one runs on, as before
        return False
    return True


def remove_later(old: str) -> threading.Thread | None:
    """In the new WTFTD: the app it replaced (update's set-aside copy only), retried until that one has closed (Windows
    keeps a running exe's file)."""
    p = Path(old) if old else None
    if p is None or not (p.name.startswith(".") and p.name.endswith(".old")):
        return None

    def remove():
        for _ in range(240):
            try:
                shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
                return
            except OSError:
                time.sleep(0.5)
    t = threading.Thread(target=remove, daemon=True)
    t.start()
    return t


def _github(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" and (u.hostname == "github.com" or (u.hostname or "").endswith(".githubusercontent.com"))


class _GitHubOnly(urllib.request.HTTPRedirectHandler):
    """A release's download link sends to GitHub's own file servers: anywhere else, the download stops."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _github(newurl):
            raise UpdateError("file")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url: str, ua: str):
    try:
        return urllib.request.build_opener(_GitHubOnly).open(urllib.request.Request(url, headers={"User-Agent": ua}), timeout=TIMEOUT)
    except urllib.error.HTTPError as e:
        e.close()
        raise UpdateError("file") from None
    except (urllib.error.URLError, OSError):
        raise UpdateError("offline") from None


def _published(url: str, ua: str) -> str:
    """The SHA-256 the release lists for its file (<file>.sha256: "<hash>  <name>")."""
    with _open(url + ".sha256", ua) as r:
        try:
            text = r.read(1024)
        except OSError:
            raise UpdateError("offline") from None
    m = re.match(rb"\s*([0-9a-fA-F]{64})\b", text)
    if not m:
        raise UpdateError("file")
    return m.group(1).decode().lower()


def _download(url: str, ua: str, dest: Path) -> str:
    """The file into dest; its SHA-256 back."""
    h, size = hashlib.sha256(), 0
    with open(dest, "wb") as f, _open(url, ua) as r:
        if int(r.headers.get("Content-Length") or 0) > MAX_BYTES:
            raise UpdateError("file")
        while True:
            try:
                chunk = r.read(1 << 16)
            except OSError:
                raise UpdateError("offline") from None
            if not chunk:
                return h.hexdigest()
            size += len(chunk)
            if size > MAX_BYTES:
                raise UpdateError("file")
            h.update(chunk)
            f.write(chunk)


def _unpack(got: Path, work: Path) -> Path:
    """The app out of the release's file: the exe itself, WTFTD.app from the zip, the binary WTFTD from the tar."""
    if sys.platform == "win32":
        return got
    if sys.platform == "darwin":
        try:
            subprocess.run(["ditto", "-x", "-k", str(got), str(work / "new")], check=True, timeout=600, capture_output=True)
        except subprocess.SubprocessError:
            raise UpdateError("file") from None
        new = work / "new" / "WTFTD.app"
        if not (new / "Contents" / "MacOS").is_dir():
            raise UpdateError("file")
        return new
    new = work / "WTFTD"
    try:
        with tarfile.open(got, "r:gz") as t:
            m = t.getmember("WTFTD")
            if not m.isfile() or m.size > MAX_BYTES:  # a link, a folder: not the app
                raise UpdateError("file")
            with t.extractfile(m) as src, open(new, "wb") as f:
                shutil.copyfileobj(src, f)
    except (KeyError, tarfile.TarError, EOFError):
        raise UpdateError("file") from None
    new.chmod(0o755)
    return new


def _swap(new: Path, app: Path) -> Path:
    """new in app's place, app set aside (hidden on macOS and Linux) under a name remove_later takes: that one, back."""
    old = app.with_name(f".{app.name}.{os.getpid()}.old")
    app.rename(old)
    try:
        new.rename(app)
    except OSError:
        old.rename(app)
        raise
    return old


def _start(app: Path, old: Path, prefix: list[str]) -> None:
    """The new app, apart from this process (it outlives it), told what it replaced."""
    args = ["--updated", str(old)]
    if sys.platform == "darwin":
        subprocess.run(["open", "-n", str(app), "--args", *args], check=True, timeout=60, capture_output=True)
    elif sys.platform == "win32":
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        try:  # out of this process's job too (a launcher's job would end it with this one)
            subprocess.Popen([str(app), *args], creationflags=flags | 0x01000000, close_fds=True, env=alone_env())  # CREATE_BREAKAWAY_FROM_JOB
        except OSError:  # the job forbids it
            subprocess.Popen([str(app), *args], creationflags=flags, close_fds=True, env=alone_env())
    else:
        subprocess.Popen([*prefix, str(app), *args], start_new_session=True, close_fds=True, env=alone_env(),
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
