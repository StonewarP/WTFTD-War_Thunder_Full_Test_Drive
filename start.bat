@echo off
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
rem no option: run without a console window (pythonw); the app window's closing stops it, messages go to .cache\wtftd.log
if "%~1"=="" (
  where pythonw >nul 2>nul && (start "" pythonw -m wtftd & exit /b 0)
)
title WTFTD - War Thunder Full Test Drive
python -m wtftd %*
