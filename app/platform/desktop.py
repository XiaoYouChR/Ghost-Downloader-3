from __future__ import annotations

import sys
from os import PathLike
from pathlib import Path

from PySide6.QtCore import QProcess, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from loguru import logger


def openFile(path: str | bytes | PathLike[str]) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def openFolder(path: str | PathLike[str]) -> None:
    path = Path(path)
    if path.exists():
        folder = str(path.parent)
        target = str(path)
        match sys.platform:
            case "win32":
                QProcess.startDetached("explorer.exe", ["/select,", target])
            case "darwin":
                QProcess.startDetached("open", ["-R", target])
            case _:
                QProcess.startDetached("xdg-open", [folder])
    elif path.parent.exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


def shutdown() -> None:
    from subprocess import Popen
    match sys.platform:
        case "win32":
            Popen(["shutdown", "/s", "/t", "0"])
        case "darwin":
            Popen(["osascript", "-e", 'tell app "System Events" to shut down'])
        case _:
            Popen(["shutdown", "-h", "now"])


def restart() -> None:
    from subprocess import Popen
    match sys.platform:
        case "win32":
            Popen(["shutdown", "/r", "/t", "0"])
        case "darwin":
            Popen(["osascript", "-e", 'tell app "System Events" to restart'])
        case _:
            Popen(["shutdown", "-r", "now"])


def openChromiumUrl(url: str) -> bool:
    import shutil
    import subprocess

    def toBrowserUrl(scheme):
        if url.startswith("chrome://"):
            return f"{scheme}://{url[9:]}"
        return url

    match sys.platform:
        case "darwin":
            for app, scheme in [
                ("Google Chrome", "chrome"),
                ("Microsoft Edge", "edge"),
                ("Brave Browser", "brave"),
                ("Chromium", "chrome"),
            ]:
                if subprocess.run(
                    ["open", "-a", app, toBrowserUrl(scheme)], capture_output=True
                ).returncode == 0:
                    return True
        case "win32":
            import winreg
            for exe, scheme in [
                ("chrome.exe", "chrome"),
                ("msedge.exe", "edge"),
                ("brave.exe", "brave"),
                ("chromium.exe", "chrome"),
            ]:
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        rf"Software\Microsoft\Windows\CurrentVersion\App Paths\{exe}",
                    ) as key:
                        path = winreg.QueryValue(key, None)
                        if path and Path(path).is_file():
                            subprocess.Popen([path, toBrowserUrl(scheme)])
                            return True
                except OSError:
                    continue
        case _:
            for cmd, scheme in [
                ("google-chrome", "chrome"),
                ("google-chrome-stable", "chrome"),
                ("microsoft-edge-stable", "edge"),
                ("microsoft-edge", "edge"),
                ("brave-browser", "brave"),
                ("chromium-browser", "chrome"),
                ("chromium", "chrome"),
            ]:
                if shutil.which(cmd):
                    try:
                        subprocess.Popen([cmd, toBrowserUrl(scheme)])
                        return True
                    except OSError:
                        continue
    return False


def raiseWindow(window) -> None:
    window.show()
    window.setWindowState(
        (window.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive
    )
    window.raise_()
    window.activateWindow()

    if sys.platform == "win32":
        try:
            import win32api
            import win32con
            import win32gui
            import win32process

            hwnd = int(window.winId())
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

            foregroundHwnd = win32gui.GetForegroundWindow()
            foregroundThreadId = (
                win32process.GetWindowThreadProcessId(foregroundHwnd)[0]
                if foregroundHwnd
                else 0
            )
            currentThreadId = win32api.GetCurrentThreadId()
            attached = False
            try:
                if foregroundThreadId and foregroundThreadId != currentThreadId:
                    win32process.AttachThreadInput(currentThreadId, foregroundThreadId, True)
                    attached = True
                win32gui.BringWindowToTop(hwnd)
                win32gui.SetForegroundWindow(hwnd)
                flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
                win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
                win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)
            finally:
                if attached:
                    win32process.AttachThreadInput(currentThreadId, foregroundThreadId, False)
        except Exception as e:
            logger.opt(exception=e).warning("Failed to raise window on Windows")
