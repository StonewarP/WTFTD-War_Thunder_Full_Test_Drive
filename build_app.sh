#!/bin/sh
# Builds dist/WTFTD.app and dist/WTFTD-macOS.zip: the macOS app (Python and UI; game data is downloaded on first launch).
set -e
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1; }
[ -x .cache/build-venv/bin/python ] || python3 -m venv .cache/build-venv
.cache/build-venv/bin/python -m pip install -q --upgrade pyinstaller pillow  # pillow: .ico -> .icns
.cache/build-venv/bin/pyinstaller --noconfirm --clean --windowed --name WTFTD \
  --icon "$PWD/web/favicon.ico" --add-data "$PWD/web:web" --osx-bundle-identifier io.github.stonewarp.wtftd \
  --distpath dist --workpath .cache/build --specpath .cache/build "$PWD/wtftd_app.py"
plist=dist/WTFTD.app/Contents/Info.plist
version=$(python3 -c "import wtftd; print(wtftd.__version__)")
plutil -replace CFBundleShortVersionString -string "$version" "$plist"
plutil -replace LSUIElement -bool YES "$plist"  # no Dock icon of its own: the app window is the browser's
codesign --force --deep --sign - dist/WTFTD.app  # ad hoc signature (Info.plist changed)
rm -f dist/WTFTD-macOS.zip
ditto -c -k --keepParent dist/WTFTD.app dist/WTFTD-macOS.zip
echo
echo "Built dist/WTFTD.app and dist/WTFTD-macOS.zip"
