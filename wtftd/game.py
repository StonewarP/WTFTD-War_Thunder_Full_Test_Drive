"""War Thunder install detection and launching."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

STEAM_APP_ID = "236390"


def _steam_roots() -> list[Path]:
    roots = []
    try:
        import winreg
        for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                          (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    for name in ("SteamPath", "InstallPath"):
                        try:
                            roots.append(Path(winreg.QueryValueEx(k, name)[0]))
                        except OSError:
                            pass
            except OSError:
                pass
    except ImportError:
        pass
    roots.append(Path(r"C:\Program Files (x86)\Steam"))
    libs = []
    for r in roots:
        vdf = r / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
        libs.append(r)
    seen, out = set(), []
    for p in libs:
        k = str(p).lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def is_game_dir(p: Path) -> bool:
    return (p / "aces.vromfs.bin").exists() or (p / "launcher.exe").exists() and (p / "levels").exists()


def detect_game_dir() -> Path | None:
    candidates = [lib / "steamapps" / "common" / "War Thunder" for lib in _steam_roots()]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "WarThunder")
    for drive in "CDEFG":
        for sub in ("WarThunder", "Games/WarThunder", "Program Files/WarThunder", "Program Files (x86)/WarThunder"):
            candidates.append(Path(f"{drive}:/") / sub)
    for c in candidates:
        try:
            if is_game_dir(c):
                return c
        except OSError:
            pass
    return None


def is_steam_install(game_dir: Path) -> bool:
    return "steamapps" in str(game_dir).lower()


def installed_levels(game_dir: Path | None) -> set[str]:
    if not game_dir:
        return set()
    out = set()
    for folder in (game_dir / "levels",):
        if folder.exists():
            out.update(p.stem.lower() for p in folder.glob("*.bin"))
    return out


def user_missions_dir(game_dir: Path) -> Path:
    return game_dir / "UserMissions"


def launch(game_dir: Path | None) -> str:
    if game_dir and not is_steam_install(game_dir) and (game_dir / "launcher.exe").exists():
        subprocess.Popen([str(game_dir / "launcher.exe")], cwd=str(game_dir))
        return "launcher"
    if sys.platform == "win32":
        os.startfile(f"steam://rungameid/{STEAM_APP_ID}")  # noqa: S606 - Steam URI
        return "steam"
    subprocess.Popen(["xdg-open", f"steam://rungameid/{STEAM_APP_ID}"])
    return "steam"


def open_folder(path: Path):
    if sys.platform == "win32":
        os.startfile(str(path))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(path)])
