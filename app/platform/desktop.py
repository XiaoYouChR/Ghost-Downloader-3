from __future__ import annotations

import sys
from os import PathLike
from pathlib import Path

from PySide6.QtCore import QProcess, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from loguru import logger


def _sendForegroundInput() -> None:
    # https://github.com/microsoft/PowerToys/pull/14383
    """Send a zero-effect mouse input so Windows grants us foreground rights."""
    if sys.platform != "win32":
        return
    import ctypes
    import ctypes.wintypes

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.wintypes.LONG),
            ("dy", ctypes.wintypes.LONG),
            ("mouseData", ctypes.wintypes.DWORD),
            ("dwFlags", ctypes.wintypes.DWORD),
            ("time", ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _UNION(ctypes.Union):
            _fields_ = [("mi", MOUSEINPUT)]

        _fields_ = [
            ("type", ctypes.wintypes.DWORD),
            ("union", _UNION),
        ]

    inp = INPUT()
    inp.type = 0  # INPUT_MOUSE
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _revealInFolderShell(path: Path) -> bool:
    """Use SHOpenFolderAndSelectItems to reveal *path* in Explorer."""
    import ctypes

    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32

    S_OK = 0
    S_FALSE = 1
    COINIT_APARTMENTTHREADED = 0x2

    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    weInitialized = hr == S_OK
    if hr not in (S_OK, S_FALSE):
        return False

    try:
        pidl = ctypes.c_void_p()
        hr = shell32.SHParseDisplayName(str(path), None, ctypes.byref(pidl), 0, None)
        if hr != S_OK or not pidl.value:
            return False
        try:
            _sendForegroundInput()
            hr = shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
            return hr == S_OK
        finally:
            ole32.CoTaskMemFree(pidl)
    finally:
        if weInitialized:
            ole32.CoUninitialize()


def openFile(path: str | bytes | PathLike[str]) -> None:
    _sendForegroundInput()
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def openFolder(path: str | PathLike[str]) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def revealInFolder(path: str | PathLike[str]) -> None:
    path = Path(path)
    if path.exists():
        match sys.platform:
            case "win32":
                if not _revealInFolderShell(path):
                    QProcess.startDetached("explorer.exe", ["/select,", str(path)])
            case "darwin":
                QProcess.startDetached("open", ["-R", str(path)])
            case _:
                QProcess.startDetached("xdg-open", [str(path.parent)])
    elif path.parent.exists():
        openFolder(path.parent)


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


def requestForeground() -> None:
    if sys.platform != "win32":
        return
    try:
        import win32api
        import win32con
        import win32gui
        import win32process

        hwnd = win32gui.FindWindow(None, "Ghost Downloader")
        if not hwnd:
            return
        foregroundHwnd = win32gui.GetForegroundWindow()
        if not foregroundHwnd or foregroundHwnd == hwnd:
            return
        foregroundThreadId = win32process.GetWindowThreadProcessId(foregroundHwnd)[0]
        currentThreadId = win32api.GetCurrentThreadId()
        attached = False
        try:
            if foregroundThreadId != currentThreadId:
                win32process.AttachThreadInput(currentThreadId, foregroundThreadId, True)
                attached = True
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if attached:
                win32process.AttachThreadInput(currentThreadId, foregroundThreadId, False)
    except Exception:
        pass


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


def launchInstaller(installerPath: str) -> None:
    """启动安装程序

    Args:
        installerPath: 安装程序的完整路径

    Raises:
        OSError: 如果无法启动安装程序
    """
    from subprocess import Popen

    installerPath = Path(installerPath)
    if not installerPath.exists():
        raise OSError(f"Installer not found: {installerPath}")

    logger.info(f"Launching installer: {installerPath}")

    try:
        if sys.platform == "win32":
            # Windows: 直接启动 .exe 或 .msi
            Popen([str(installerPath)], cwd=str(installerPath.parent))
        elif sys.platform == "darwin":
            # macOS: 使用 open 命令启动 .dmg 或 .pkg
            Popen(["open", str(installerPath)])
        else:
            # Linux: 启动 .appimage 或其他可执行文件
            if installerPath.suffix.lower() == ".appimage":
                installerPath.chmod(0o755)  # 确保可执行
            Popen([str(installerPath)], cwd=str(installerPath.parent))
    except Exception as e:
        logger.opt(exception=e).error(f"Failed to launch installer: {installerPath}")
        raise OSError(f"Failed to launch installer: {e}") from e
