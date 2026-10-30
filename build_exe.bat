@echo off
rem Builds dist\WTFTD-<version>.exe: a single-file Windows app (Python and UI; game data comes on first launch).
rem Built from a branch other than main, the branch is added to the name: dist\WTFTD-<version>-<branch>.exe.
title WTFTD - build exe
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
set "VER="
for /f "delims=" %%v in ('python -c "import wtftd; print(wtftd.__version__)"') do set "VER=%%v"
if not defined VER (echo Could not read the version from wtftd\__init__.py & exit /b 1)
set "BRANCH="
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%b"
set "NAME=WTFTD-%VER%"
if defined BRANCH if not "%BRANCH%"=="main" if not "%BRANCH%"=="HEAD" set "NAME=WTFTD-%VER%-%BRANCH:/=-%"
if not exist ".cache\build-venv\Scripts\python.exe" python -m venv .cache\build-venv
.cache\build-venv\Scripts\python -m pip install -q --upgrade pyinstaller || exit /b 1
.cache\build-venv\Scripts\python -c "import compression.zstd" 2>nul || (
  echo.
  echo WARNING: this Python has no compression.zstd ^(it needs 3.14 or newer^): the exe will not offer to read the installed game.
  echo To fix it, install Python 3.14 and delete .cache\build-venv.
  echo.
)
.cache\build-venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed --name "%NAME%" ^
  --icon "%~dp0web\favicon.ico" --add-data "%~dp0web;web" ^
  --distpath dist --workpath .cache\build --specpath .cache\build "%~dp0wtftd_app.py" || exit /b 1
echo.
echo Built dist\%NAME%.exe
