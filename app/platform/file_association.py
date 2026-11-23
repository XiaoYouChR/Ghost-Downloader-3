from __future__ import annotations

import os
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
    progIds = set()
    for fileType in fileTypes:
        iconPath = str(EXECUTABLE_DIR / "app" / "assets" / "file_icons" / f"{fileType.icon}.ico").replace("/", "\\")
        for ext in fileType.extensions:
            progId = f"GhostDownloader{ext}"
            progIds.add(progId)
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

    # 已关闭的文件类型不会传进来，只能按 ProgId 前缀找出旧的注册项
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes") as classes:
        names = [winreg.EnumKey(classes, i) for i in range(winreg.QueryInfoKey(classes)[0])]
    for name in names:
        if name.startswith("GhostDownloader.") and name not in progIds:
            _unregisterProgIdWindows(name)
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)


def _unregisterProgIdWindows(progId: str) -> None:
    ext = progId.removeprefix("GhostDownloader")
    regRoot = rf"Software\Classes\{progId}"
    for regPath in (rf"{regRoot}\shell\open\command", rf"{regRoot}\shell\open", rf"{regRoot}\shell",
                    rf"{regRoot}\DefaultIcon", regRoot):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, regPath)
        except FileNotFoundError:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}\OpenWithProgids",
                            0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, progId)
    except FileNotFoundError:
        pass
    try:
        # 用户已把默认程序改成别的时，扩展名的默认值不归我们管
        if winreg.QueryValue(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") == progId:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}", 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, "")
    except FileNotFoundError:
        pass


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


HANDLER_DESKTOP_NAME = f"{DESKTOP_ID}.handler.desktop"
DESKTOP_FILE = (
    Path(os.environ["XDG_DATA_HOME"])
    if os.environ.get("XDG_DATA_HOME", "").startswith("/")
    else Path.home() / ".local/share"
) / "applications" / HANDLER_DESKTOP_NAME
MIMEAPPS_FILE = (
    Path(os.environ["XDG_CONFIG_HOME"])
    if os.environ.get("XDG_CONFIG_HOME", "").startswith("/")
    else Path.home() / ".config"
) / "mimeapps.list"


def loadMimeTypes() -> set[str]:
    if not DESKTOP_FILE.exists():
        return set()
    for line in DESKTOP_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("MimeType="):
            return {m for m in line[9:].split(";") if m}
    return set()


def deleteMimeDefaults(mimes: set[str]) -> None:
    if not MIMEAPPS_FILE.exists():
        return

    lines: list[str] = []
    isInDefaults = False
    hasChanged = False
    for line in MIMEAPPS_FILE.read_text(encoding="utf-8").splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("["):
            isInDefaults = stripped == "[Default Applications]"
        elif isInDefaults and "=" in line:
            mime, rawValue = line.split("=", 1)
            if mime.strip() in mimes:
                entries = [e for e in rawValue.strip().split(";") if e]
                remaining = [e for e in entries if e != HANDLER_DESKTOP_NAME]
                if len(remaining) != len(entries):
                    hasChanged = True
                    if remaining:
                        lines.append(f"{mime}={';'.join(remaining)};\n")
                    continue
        lines.append(line)

    if hasChanged:
        MIMEAPPS_FILE.write_text("".join(lines), encoding="utf-8")


def saveMimeTypes(mimes: set[str]) -> None:
    desktopText = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Ghost Downloader\n"
        "Comment=The only downloader you need\n"
        f'Exec="{EXECUTABLE_PATH}" %U\n'
        "Icon=ghost-downloader\n"
        "NoDisplay=true\n"
        "Terminal=false\n"
        f"MimeType={';'.join(sorted(mimes))};\n"
    )
    oldText = DESKTOP_FILE.read_text(encoding="utf-8") if DESKTOP_FILE.exists() else None
    # 每次改写都会让桌面重建缓存，反复改写会卡住 KWin #1045
    if oldText == (desktopText if mimes else None):
        return

    removed = loadMimeTypes() - mimes
    if mimes:
        DESKTOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        DESKTOP_FILE.write_text(desktopText, encoding="utf-8")
    else:
        DESKTOP_FILE.unlink(missing_ok=True)
    if removed:
        deleteMimeDefaults(removed)

    try:
        subprocess.run(["update-desktop-database", str(DESKTOP_FILE.parent)], check=False, capture_output=True)
    except FileNotFoundError:
        logger.warning("缺少 update-desktop-database, 跳过")

    for mime in mimes:
        try:
            subprocess.run(["xdg-mime", "default", HANDLER_DESKTOP_NAME, mime], check=False, capture_output=True)
        except FileNotFoundError:
            logger.warning("缺少 xdg-mime, 跳过文件关联")
            break
