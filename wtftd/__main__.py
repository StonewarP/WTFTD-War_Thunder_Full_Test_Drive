"""Entry point: python -m wtftd [--browser] [--port N]

Opens the UI in a chromeless Edge/Chrome app window when available and stops the
server when that window is closed. --browser uses the default browser instead.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from .server import ROOT, serve


def find_app_browser() -> str | None:
    pf = [os.environ.get(k) for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
    candidates = []
    for base in filter(None, pf):
        candidates += [
            Path(base) / "Microsoft/Edge/Application/msedge.exe",
            Path(base) / "Google/Chrome/Application/chrome.exe",
        ]
    for c in candidates:
        if c.exists():
            return str(c)
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


def main():
    port = 8777
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    httpd, url = serve(port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"WTFTD running at {url}  (Ctrl+C to quit)")

    exe = None if "--browser" in sys.argv or "--no-window" in sys.argv else find_app_browser()
    try:
        if exe:
            profile = ROOT / ".cache" / "app-window"
            # our dedicated profile: drop its favicon cache so a new app icon shows up in the taskbar
            for name in ("Favicons", "Favicons-journal"):
                try:
                    (profile / "Default" / name).unlink()
                except OSError:
                    pass
            proc = subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1500,920",
                                     "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"])
            proc.wait()  # window closed -> quit
        else:
            if "--no-window" not in sys.argv:
                webbrowser.open(url)
            threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
