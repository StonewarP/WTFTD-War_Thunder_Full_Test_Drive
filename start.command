#!/bin/sh
# macOS: double-click to run WTFTD from source (the counterpart of start.bat).
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.10+ is required: https://www.python.org/downloads/"; read -r _; exit 1; }
python3 -m wtftd "$@"
