@echo off
title Ghost Downloader 3
cd /d "%~dp0"
echo Starting Ghost Downloader 3...
uv run python Ghost-Downloader-3.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error.
    pause
)
