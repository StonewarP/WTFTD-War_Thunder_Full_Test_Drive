@echo off
title WTFTD - War Thunder Full Test Drive
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
python -m wtftd %*
