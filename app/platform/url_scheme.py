from __future__ import annotations

import sys

from loguru import logger
from PySide6.QtCore import QCoreApplication

URL_SCHEME = "ghostdownloader"


def registerUrlScheme(scheme: str = URL_SCHEME) -> None:
    try:
        if sys.platform == "win32":
            _registerWindows(scheme)
        elif sys.platform == "linux":
            _registerLinux(scheme)
    except Exception as e:
        logger.opt(exception=e).error("URL scheme 注册失败: {}", scheme)


def unregisterUrlScheme(scheme: str = URL_SCHEME) -> None:
    try:
        if sys.platform == "win32":
            _unregisterWindows(scheme)
        elif sys.platform == "linux":
            _unregisterLinux(scheme)
    except Exception as e:
        logger.opt(exception=e).error("URL scheme 注销失败: {}", scheme)


def isLaunchUri(uri: str) -> bool:
    return uri.startswith(f"{URL_SCHEME}://")


if sys.platform == "win32":
    import winreg

    def _registerWindows(scheme: str) -> None:
        regRoot = rf"Software\Classes\{scheme}"
        command = f'"{QCoreApplication.applicationFilePath().replace("/", chr(92))}" "%1"'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, regRoot) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"Ghost Downloader URL ({scheme})")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{regRoot}\shell\open\command") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

    def _unregisterWindows(scheme: str) -> None:
        regRoot = rf"Software\Classes\{scheme}"
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{regRoot}\shell\open\command")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{regRoot}\shell\open")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{regRoot}\shell")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, regRoot)
        except FileNotFoundError:
            pass


if sys.platform == "linux":
    import subprocess
    from pathlib import Path

    from app.config.constants import DESKTOP_ID

    def _registerLinux(scheme: str) -> None:
        desktopDir = Path.home() / ".local/share/applications"
        desktopFile = desktopDir / f"{DESKTOP_ID}.desktop"
        mime = f"x-scheme-handler/{scheme}"

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
                ["xdg-mime", "default", f"{DESKTOP_ID}.desktop", mime],
                check=False, capture_output=True,
            )
        except FileNotFoundError:
            pass

    def _unregisterLinux(scheme: str) -> None:
        desktopDir = Path.home() / ".local/share/applications"
        desktopFile = desktopDir / f"{DESKTOP_ID}.desktop"

        if not desktopFile.exists():
            return

        content = desktopFile.read_text(encoding="utf-8")
        mime = f"x-scheme-handler/{scheme}"
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
