@echo off
rem Builds dist\WTFTD.exe: a single-file Windows app (Python, UI and game data included).
title WTFTD - build exe
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
if not exist ".cache\build-venv\Scripts\python.exe" python -m venv .cache\build-venv
.cache\build-venv\Scripts\python -m pip install -q --upgrade pyinstaller || exit /b 1
.cache\build-venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed --name WTFTD ^
  --icon "%~dp0web\favicon.ico" --add-data "%~dp0web;web" --add-data "%~dp0data;data" ^
  --distpath dist --workpath .cache\build --specpath .cache\build "%~dp0wtftd_app.py" || exit /b 1
echo.
echo Built dist\WTFTD.exe
