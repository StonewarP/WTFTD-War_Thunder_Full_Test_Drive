"""Settings → Uninstall: removes what WTFTD put on this PC, part by part. War Thunder itself is never touched,
only what WTFTD added to it (the custom vehicle files of its manifest, the missions it created).

  cdk       custom vehicle files in the game's content/pkg_local and pkg_user (cdk.cleanup, from the manifest)
  missions  missions created by WTFTD in the game's UserMissions (wtftd_*.blk, and the other names it saved a setup for)
  cache     .cache: the datamine copy, pictures, maps, logs (the app window's profile goes once WTFTD has closed)
  data      data: the game database built from the game files
  user      user: settings, My vehicles / maps / missions (the custom vehicle manifest stays unless cdk goes too)
  app       the app itself (packaged app only: WTFTD.exe, WTFTD.app), once WTFTD has closed
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import cdk, game
from .paths import CACHE, DATA, FROZEN, HOME, USER

PARTS = ("cdk", "missions", "cache", "data", "user", "app")
WINDOW_PROFILE = "app-window"  # the app window's browser profile: in use while it is open


def _size(path: Path) -> int:
    total = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def app_path() -> Path | None:
    """The packaged app to remove: WTFTD.exe, or the WTFTD.app bundle; None from the source code."""
    if not FROZEN:
        return None
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin":
        for p in exe.parents:
            if p.suffix == ".app":
                return p
        return None
    return exe


def mission_files(game_dir: Path | None) -> list[Path]:
    """The missions WTFTD created in the game's UserMissions folder."""
    if not game_dir:
        return []
    um = game.user_missions_dir(game_dir)
    if not um.is_dir():
        return []
    saved = {p.stem for p in (USER / "missions").glob("*.json")}
    return sorted(p for p in um.glob("*.blk") if p.is_file() and (p.name.startswith("wtftd_") or p.stem in saved))


def info(game_dir: Path | None) -> dict:
    app = app_path()
    return {
        "cdk": {"files": sum(1 for f in cdk.read_manifest(USER) if game_dir and (game_dir / "content" / f).exists())},
        "missions": {"files": len(mission_files(game_dir))},
        "cache": {"bytes": _size(CACHE)},
        "data": {"bytes": _size(DATA)},
        "user": {"bytes": _size(USER)},
        "app": {"available": app is not None, "path": str(app) if app else "", "home": str(HOME),
                "bytes": _size(app) if app and app.is_dir() else (app.stat().st_size if app and app.exists() else 0)},
    }


def _rmtree(path: Path, keep: set[str] = frozenset()) -> None:
    """Removes a folder's content (what can be: files in use stay), keeping the names in keep."""
    if not path.is_dir():
        return
    for child in path.iterdir():
        if child.name in keep:
            continue
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink()
        except OSError:
            pass
    try:
        path.rmdir()  # only when empty
    except OSError:
        pass


def _after_exit(paths: list[Path], pid: int | None = None) -> None:
    """A detached script removes paths once WTFTD has closed: it retries for 10 minutes while they are in use (the
    exe while WTFTD runs, the app window's profile until the window closes). pid: the process to wait for on macOS
    (this one by default)."""
    pid = pid or os.getpid()
    if sys.platform == "win32":
        # no wait on the process itself (tasklist hangs without a console): Windows keeps the exe locked while
        # WTFTD runs, and the window's profile while the window is open, so the script just retries until all
        # is gone. The pause is ping, by its full path: timeout fails at once without a console.
        ping = r'"%SystemRoot%\System32\PING.EXE"'
        lines = ["@echo off", "for /l %%i in (1,1,300) do ("]
        for p in paths:
            lines.append(f'  if exist "{p}\\*" (rmdir /s /q "{p}" 2>nul) else (del /f /q "{p}" 2>nul)')
        checks = " ".join(f'if not exist "{p}"' for p in paths)
        lines += [f"  {checks} goto done", f"  {ping} -n 3 127.0.0.1 >nul", ")", ":done", '(goto) 2>nul & del "%~f0"']
        script = Path(tempfile.gettempdir()) / f"wtftd_uninstall_{pid}.cmd"
        script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        try:  # out of this process's job too (a launcher's job would end the script with WTFTD)
            subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags | 0x01000000, close_fds=True)  # CREATE_BREAKAWAY_FROM_JOB
        except OSError:  # the job forbids it
            subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)
    else:
        quoted = " ".join("'" + str(p).replace("'", "'\\''") + "'" for p in paths)
        sh = (f"while kill -0 {pid} 2>/dev/null; do sleep 1; done; "
              f"for i in $(seq 1 300); do rm -rf {quoted}; ok=1; for p in {quoted}; do [ -e \"$p\" ] && ok=0; done; "
              f"[ $ok = 1 ] && break; sleep 2; done")
        subprocess.Popen(["/bin/sh", "-c", sh], start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run(parts: list[str], game_dir: Path | None) -> dict:
    """Removes the chosen parts. Returns {removed: {part: count}, quit: WTFTD must close now (the app goes)}."""
    parts = [p for p in PARTS if p in parts]
    removed: dict = {}
    if "cdk" in parts:
        removed["cdk"] = cdk.cleanup(game_dir, USER) if game_dir else 0
    if "missions" in parts:
        n = 0
        for p in mission_files(game_dir):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
        removed["missions"] = n
    if "cache" in parts:
        _rmtree(CACHE, keep={WINDOW_PROFILE})
        removed["cache"] = 1
    if "data" in parts:
        _rmtree(DATA)
        removed["data"] = 1
    if "user" in parts:
        # without its manifest, the custom vehicle files left in the game could no longer be removed
        _rmtree(USER, keep=set() if "cdk" in parts else {cdk._manifest_path(USER).name})
        removed["user"] = 1
    later: list[Path] = []
    app = app_path()
    if "app" in parts and app:
        later.append(app)
        if all(p in parts for p in ("cache", "data", "user")):
            later.append(HOME)  # everything: the whole folder, the window's profile and the log included
        elif "cache" in parts:
            later.append(CACHE / WINDOW_PROFILE)
    if later:
        _after_exit(later)
    return {"removed": removed, "quit": "app" in parts and app is not None}
