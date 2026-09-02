@echo off
title Ghost Downloader 3
cd /d "%~dp0"

if not exist ".venv" (
    echo Environment not set up. Launching Installer.exe...
    start "" "%~dp0Installer.exe"
    exit /b
)

echo Starting Ghost Downloader 3...
uv run python Ghost-Downloader-3.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error.
    pause
)


