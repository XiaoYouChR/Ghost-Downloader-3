import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication


def setRunAtLogin(enabled: bool) -> None:
    if sys.platform == "win32":
        _setWindows(enabled)
    elif sys.platform == "darwin":
        _setMacOS(enabled)
    elif sys.platform == "linux":
        _setLinux(enabled)


def _setWindows(enabled: bool) -> None:
    import winreg

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_WRITE,
    )
    if enabled:
        exePath = QCoreApplication.applicationFilePath().replace("/", "\\")
        winreg.SetValueEx(key, "GhostDownloader", 0, winreg.REG_SZ, f'"{exePath}" --silence')
    else:
        try:
            winreg.DeleteValue(key, "GhostDownloader")
        except FileNotFoundError:
            pass
    winreg.CloseKey(key)


def _setMacOS(enabled: bool) -> None:
    from pwd import getpwuid
    plistPath = Path(f"/Users/{getpwuid(os.getuid()).pw_name}/Library/LaunchAgents/com.xiaoyouchr.ghostdownloader.plist")

    if enabled:
        plistPath.parent.mkdir(parents=True, exist_ok=True)
        appPath = QCoreApplication.applicationFilePath()
        plistPath.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            '<key>Label</key>\n<string>com.xiaoyouchr.ghostdownloader</string>\n'
            '<key>ProgramArguments</key>\n<array>\n'
            f'<string>{appPath}</string>\n<string>--silence</string>\n'
            '</array>\n<key>RunAtLoad</key>\n<true/>\n'
            '</dict>\n</plist>\n',
            encoding="utf-8",
        )
    else:
        plistPath.unlink(missing_ok=True)


def _setLinux(enabled: bool) -> None:
    from app.config.constants import DESKTOP_ID, VERSION

    autoStartDir = Path.home() / ".config/autostart"
    desktopFile = autoStartDir / f"{DESKTOP_ID}.desktop"

    if enabled:
        autoStartDir.mkdir(parents=True, exist_ok=True)
        desktopFile.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Version={VERSION}\n"
            "Name=Ghost Downloader 3\n"
            "Comment=A multi-threading downloader with QThread based on PySide6\n"
            f'Exec="{QCoreApplication.applicationFilePath()}" --silence\n'
            "StartupNotify=false\n"
            "Terminal=false\n",
            encoding="utf-8",
        )
    else:
        desktopFile.unlink(missing_ok=True)
