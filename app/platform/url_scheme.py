from __future__ import annotations

import sys

from loguru import logger
from PySide6.QtCore import QCoreApplication

URL_SCHEME = "ghostdownloader"


def registerUrlScheme() -> None:
    try:
        if sys.platform == "win32":
            _registerWindows()
        elif sys.platform == "linux":
            _registerLinux()
    except Exception as e:
        logger.opt(exception=e).error("URL scheme 注册失败")


def unregisterUrlScheme() -> None:
    try:
        if sys.platform == "win32":
            _unregisterWindows()
        elif sys.platform == "linux":
            _unregisterLinux()
    except Exception as e:
        logger.opt(exception=e).error("URL scheme 注销失败")


def isLaunchUri(uri: str) -> bool:
    return uri.startswith(f"{URL_SCHEME}://")


if sys.platform == "win32":
    import winreg

    _REG_ROOT = rf"Software\Classes\{URL_SCHEME}"

    def _registerWindows() -> None:
        command = f'"{QCoreApplication.applicationFilePath().replace("/", chr(92))}" "%1"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_ROOT) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "Ghost Downloader URL")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{_REG_ROOT}\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

    def _unregisterWindows() -> None:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{_REG_ROOT}\shell\open\command")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{_REG_ROOT}\shell\open")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{_REG_ROOT}\shell")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _REG_ROOT)
        except FileNotFoundError:
            pass


if sys.platform == "linux":
    import subprocess
    from pathlib import Path

    from app.config.constants import DESKTOP_ID

    def _registerLinux() -> None:
        desktopDir = Path.home() / ".local/share/applications"
        desktopFile = desktopDir / f"{DESKTOP_ID}.desktop"
        mime = f"x-scheme-handler/{URL_SCHEME}"

        if desktopFile.exists():
            content = desktopFile.read_text(encoding="utf-8")
            if mime not in content:
                content = content.replace("MimeType=", f"MimeType={mime};", 1)
                if "MimeType=" not in content:
                    content = content.rstrip("\n") + f"\nMimeType={mime};\n"
                desktopFile.write_text(content, encoding="utf-8")
        else:
            desktopDir.mkdir(parents=True, exist_ok=True)
            appPath = QCoreApplication.applicationFilePath()
            desktopFile.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Ghost Downloader\n"
                f"Exec={appPath} %U\n"
                "Icon=ghost-downloader\n"
                "Terminal=false\n"
                "Categories=Network;Utility;\n"
                f"MimeType={mime};\n",
                encoding="utf-8",
            )

        try:
            subprocess.run(
                ["update-desktop-database", str(desktopDir)],
                check=False, capture_output=True,
            )
        except FileNotFoundError:
            pass
        try:
            subprocess.run(
                ["xdg-mime", "default", f"{DESKTOP_ID}.desktop",
                 f"x-scheme-handler/{URL_SCHEME}"],
                check=False, capture_output=True,
            )
        except FileNotFoundError:
            pass

    def _unregisterLinux() -> None:
        desktopDir = Path.home() / ".local/share/applications"
        desktopFile = desktopDir / f"{DESKTOP_ID}.desktop"

        if not desktopFile.exists():
            return

        content = desktopFile.read_text(encoding="utf-8")
        mime = f"x-scheme-handler/{URL_SCHEME}"
        if mime in content:
            content = content.replace(f"{mime};", "").replace(mime, "")
            desktopFile.write_text(content, encoding="utf-8")
            try:
                subprocess.run(
                    ["update-desktop-database", str(desktopDir)],
                    check=False, capture_output=True,
                )
            except FileNotFoundError:
                pass
