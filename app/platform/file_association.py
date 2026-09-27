from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from app.config.constants import DESKTOP_ID
from app.config.paths import EXECUTABLE_DIR, EXECUTABLE_PATH
from app.platform.url_scheme import URL_SCHEME

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


def registerUrlScheme(scheme: str = URL_SCHEME) -> None:
    try:
        if sys.platform == "win32":
            _registerUrlSchemeWindows(scheme)
        elif sys.platform == "linux":
            saveMimeTypes(loadMimeTypes() | {f"x-scheme-handler/{scheme}"})
    except Exception as e:
        logger.opt(exception=e).error("URL scheme 注册失败: {}", scheme)


def unregisterUrlScheme(scheme: str = URL_SCHEME) -> None:
    try:
        if sys.platform == "win32":
            _unregisterUrlSchemeWindows(scheme)
        elif sys.platform == "linux":
            saveMimeTypes(loadMimeTypes() - {f"x-scheme-handler/{scheme}"})
    except Exception as e:
        logger.opt(exception=e).error("URL scheme 注销失败: {}", scheme)


def _registerWindows(fileTypes: list[FileType]) -> None:
    command = f'"{EXECUTABLE_PATH}" "%1"'
    for fileType in fileTypes:
        iconPath = str(EXECUTABLE_DIR / "app" / "assets" / "file_icons" / f"{fileType.icon}.ico").replace("/", "\\")
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


def _registerUrlSchemeWindows(scheme: str) -> None:
    regRoot = rf"Software\Classes\{scheme}"
    command = f'"{EXECUTABLE_PATH}" "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, regRoot) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"Ghost Downloader URL ({scheme})")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{regRoot}\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


def _unregisterUrlSchemeWindows(scheme: str) -> None:
    regRoot = rf"Software\Classes\{scheme}"
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{regRoot}\shell\open\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{regRoot}\shell\open")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{regRoot}\shell")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, regRoot)
    except FileNotFoundError:
        pass


def _registerLinux(fileTypes: list[FileType]) -> None:
    schemes = {m for m in loadMimeTypes() if m.startswith("x-scheme-handler/")}
    saveMimeTypes(schemes | {ft.mimeType for ft in fileTypes})


def loadMimeTypes() -> set[str]:
    desktopFile = Path.home() / ".local/share/applications" / f"{DESKTOP_ID}.desktop"
    if not desktopFile.exists():
        return set()
    for line in desktopFile.read_text(encoding="utf-8").splitlines():
        if line.startswith("MimeType="):
            return {m for m in line[9:].split(";") if m}
    return set()


def saveMimeTypes(mimes: set[str]) -> None:
    desktopDir = Path.home() / ".local/share/applications"
    serviceDir = Path.home() / ".local/share/dbus-1/services"
    desktopFile = desktopDir / f"{DESKTOP_ID}.desktop"
    serviceFile = serviceDir / f"{DESKTOP_ID}.service"

    if mimes:
        desktopDir.mkdir(parents=True, exist_ok=True)
        serviceDir.mkdir(parents=True, exist_ok=True)
        desktopFile.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Ghost Downloader\n"
            f'Exec="{EXECUTABLE_PATH}" %U\n'
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
            f'Exec="{EXECUTABLE_PATH}"\n',
            encoding="utf-8",
        )
    else:
        desktopFile.unlink(missing_ok=True)
        serviceFile.unlink(missing_ok=True)

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
