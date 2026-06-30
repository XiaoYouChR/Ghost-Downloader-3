from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QCoreApplication

from app.config.constants import DESKTOP_ID
from app.config.paths import executableDir

if sys.platform == "win32":
    import ctypes
    import winreg

if TYPE_CHECKING:
    from app.models.pack import FileType


def register(fileTypes: list[FileType]) -> None:
    try:
        if sys.platform == "win32":
            _registerWindows(fileTypes)
        elif sys.platform == "linux":
            _registerLinux(fileTypes)
    except Exception as e:
        logger.opt(exception=e).error("文件关联注册失败")


def _registerWindows(fileTypes: list[FileType]) -> None:
    command = f'"{QCoreApplication.applicationFilePath().replace("/", chr(92))}" "%1"'
    for fileType in fileTypes:
        iconPath = str(executableDir / "app" / "assets" / "file_icons" / f"{fileType.icon}.ico").replace("/", "\\")
        for ext in fileType.extensions:
            progId = f"GhostDownloader{ext}"
            for regPath, regValue in (
                (rf"Software\Classes\{progId}", fileType.displayName),
                (rf"Software\Classes\{progId}\DefaultIcon", iconPath),
                (rf"Software\Classes\{progId}\shell\open\command", command),
                (rf"Software\Classes\{ext}", progId),
            ):
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, regPath) as key:
                    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, regValue)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}\OpenWithProgids") as key:
                winreg.SetValueEx(key, progId, 0, winreg.REG_NONE, b"")
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def _registerLinux(fileTypes: list[FileType]) -> None:
    desktopDir = Path.home() / ".local/share/applications"
    serviceDir = Path.home() / ".local/share/dbus-1/services"
    desktopFile = desktopDir / f"{DESKTOP_ID}.desktop"
    serviceFile = serviceDir / f"{DESKTOP_ID}.service"

    mimes = {ft.mimeType for ft in fileTypes}

    # Preserve URL scheme handlers registered by url_scheme.py
    if desktopFile.exists():
        for line in desktopFile.read_text(encoding="utf-8").splitlines():
            if line.startswith("MimeType="):
                for m in line[9:].rstrip(";").split(";"):
                    if m.startswith("x-scheme-handler/"):
                        mimes.add(m)

    if not mimes:
        desktopFile.unlink(missing_ok=True)
        serviceFile.unlink(missing_ok=True)
        return

    desktopDir.mkdir(parents=True, exist_ok=True)
    serviceDir.mkdir(parents=True, exist_ok=True)
    appPath = QCoreApplication.applicationFilePath()

    desktopFile.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Ghost Downloader\n"
        f"Exec={appPath} %U\n"
        "Icon=ghost-downloader\n"
        "Terminal=false\n"
        "Categories=Network;Utility;\n"
        "DBusActivatable=true\n"
        f"MimeType={';'.join(sorted(mimes))};\n",
        encoding="utf-8",
    )
    serviceFile.write_text(
        "[D-BUS Service]\n"
        f"Name={DESKTOP_ID}\n"
        f"Exec={appPath}\n",
        encoding="utf-8",
    )

    try:
        subprocess.run(["update-desktop-database", str(desktopDir)], check=False, capture_output=True)
    except FileNotFoundError:
        logger.warning("缺少 update-desktop-database, 跳过")

    for mime in mimes:
        try:
            subprocess.run(["xdg-mime", "default", f"{DESKTOP_ID}.desktop", mime], check=False, capture_output=True)
        except FileNotFoundError:
            logger.warning("缺少 xdg-mime, 跳过文件关联")
            break
