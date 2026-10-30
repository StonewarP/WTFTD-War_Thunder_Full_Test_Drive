@echo off
cd /d "%~dp0"
rem reading the installed game needs Python 3.14+: use it when it's there, even if it isn't the default python
set "PY=python"
set "PYW=pythonw"
py -3.14 -c "import compression.zstd" >nul 2>nul && (set "PY=py -3.14" & set "PYW=pyw -3.14")
if "%PY%"=="python" (where python >nul 2>nul || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1))
rem no option: run without a console window (pythonw); the app window's closing stops it, messages go to .cache\wtftd.log
if "%~1"=="" (
  if not "%PY%"=="python" (start "" %PYW% -m wtftd & exit /b 0)
  where pythonw >nul 2>nul && (start "" pythonw -m wtftd & exit /b 0)
)
title WTFTD - War Thunder Full Test Drive
%PY% -m wtftd %*
