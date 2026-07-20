from __future__ import annotations

import sys
from os import PathLike
from pathlib import Path

from PySide6.QtCore import QMimeData, QProcess, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QDrag
from PySide6.QtWidgets import QWidget
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


def sleep() -> None:
    from subprocess import Popen
    match sys.platform:
        case "win32":
            Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"])
        case "darwin":
            Popen(["pmset", "sleepnow"])
        case _:
            Popen(["systemctl", "suspend"])


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


def findVlcBinary() -> str | None:
    """Return the path to the VLC executable, or None if not found."""
    import shutil
    import subprocess
    from app.config.cfg import cfg

    if cfg.vlcPath.value and Path(cfg.vlcPath.value).is_file():
        return cfg.vlcPath.value

    match sys.platform:

        case "win32":
            import winreg
            import os
            # App Paths lookup
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root, r"Software\Microsoft\Windows\CurrentVersion\App Paths\vlc.exe") as key:
                        path = winreg.QueryValue(key, None)
                        if path and Path(path).is_file():
                            return path
                except OSError:
                    pass

            # VideoLAN registry lookup (path is in InstallDir value)
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(root, r"Software\VideoLAN\VLC") as key:
                        path, _ = winreg.QueryValueEx(key, "InstallDir")
                        if path:
                            candidate = Path(path) / "vlc.exe"
                            if candidate.is_file():
                                return str(candidate)
                except OSError:
                    pass

            # Fallback: check standard environment variables
            for env_var in ["ProgramFiles", "ProgramFiles(x86)", "LocalAppData"]:
                base = os.environ.get(env_var)
                if base:
                    candidate = Path(base) / "VideoLAN" / "VLC" / "vlc.exe"
                    if candidate.is_file():
                        return str(candidate)

            # hardcoded fallback
            for candidate in [
                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
            ]:
                if Path(candidate).is_file():
                    return candidate

        case "darwin":
            candidates = [
                "/Applications/VLC.app/Contents/MacOS/VLC",
                str(Path.home() / "Applications/VLC.app/Contents/MacOS/VLC"),
            ]
            for candidate in candidates:
                if Path(candidate).is_file():
                    return candidate
            # Also check if `vlc` is on PATH
            found = shutil.which("vlc")
            if found:
                return found
        case _:
            found = shutil.which("vlc")
            if found:
                return found
    return None


def playInVlc(filePath: str) -> None:
    """Open *filePath* in VLC. Falls back to the OS default player if VLC is not found."""
    import subprocess
    vlc = findVlcBinary()
    if vlc:
        try:
            subprocess.Popen([vlc, filePath])
            return
        except OSError as e:
            logger.warning("playInVlc: failed to launch VLC ({}): {}", vlc, e)
    # Fallback to system default association
    openFile(filePath)


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


def startFileDrag(paths: list[Path], source: QWidget) -> None:
    if sys.platform == "win32":
        try:
            hwnd = int(source.window().winId())
            _startFileDragWin32([str(p) for p in paths], hwnd)
            return
        except Exception as e:
            logger.opt(exception=e).debug("COM drag failed, falling back to Qt")
    _startFileDragQt(paths, source)


def _startFileDragQt(paths: list[Path], source: QWidget) -> None:
    from PySide6.QtCore import QFileInfo, QPoint
    from PySide6.QtWidgets import QFileIconProvider

    mimeData = QMimeData()
    mimeData.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    drag = QDrag(source)
    drag.setMimeData(mimeData)
    pixmap = QFileIconProvider().icon(QFileInfo(str(paths[0]))).pixmap(32, 32)
    drag.setPixmap(pixmap)
    drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
    drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)


def _startFileDragWin32(paths: list[str], hwnd: int) -> None:
    import ctypes
    import uuid

    shell32 = ctypes.windll.shell32
    shell32.SHParseDisplayName.restype = ctypes.HRESULT
    shell32.SHCreateShellItemArrayFromIDLists.restype = ctypes.HRESULT
    shell32.SHDoDragDrop.restype = ctypes.HRESULT
    shell32.SHDoDragDrop.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
    ]

    def toGuid(text: str) -> ctypes.Array:
        return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(text).bytes_le)

    def release(pUnknown: ctypes.c_void_p) -> None:
        vtable = ctypes.cast(
            ctypes.cast(pUnknown, ctypes.POINTER(ctypes.c_void_p))[0],
            ctypes.POINTER(ctypes.c_void_p),
        )
        ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtable[2])(pUnknown)

    # 拖拽图标与 DropDescription 靠 IDataObject::SetData 私有格式传递，
    # 剪贴板数据对象不支持 SetData，必须从 shell item 构建数据对象
    pidls: list[ctypes.c_void_p] = []
    try:
        for p in paths:
            pidl = ctypes.c_void_p()
            shell32.SHParseDisplayName(p, None, ctypes.byref(pidl), 0, None)
            pidls.append(pidl)

        pidlArray = (ctypes.c_void_p * len(pidls))(*(p.value for p in pidls))
        pItemArray = ctypes.c_void_p()
        shell32.SHCreateShellItemArrayFromIDLists(
            len(pidls), pidlArray, ctypes.byref(pItemArray))
        try:
            vtable = ctypes.cast(
                ctypes.cast(pItemArray, ctypes.POINTER(ctypes.c_void_p))[0],
                ctypes.POINTER(ctypes.c_void_p),
            )
            BindToHandler = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
            )(vtable[3])
            pDataObj = ctypes.c_void_p()
            BindToHandler(
                pItemArray, None,
                toGuid("B8C0BD9F-ED24-455C-83E6-D5390C4FE8C4"),  # BHID_DataObject
                toGuid("0000010E-0000-0000-C000-000000000046"),  # IID_IDataObject
                ctypes.byref(pDataObj),
            )
            try:
                dwEffect = ctypes.c_ulong(0)
                # 至此拖拽会话已托付给 Shell；失败不再上抛回退 Qt，
                # 否则会在鼠标已松开后再启动一次幽灵拖拽
                try:
                    shell32.SHDoDragDrop(hwnd, pDataObj, None, 7, ctypes.byref(dwEffect))
                except OSError as e:
                    logger.opt(exception=e).debug("SHDoDragDrop failed")
            finally:
                release(pDataObj)
        finally:
            release(pItemArray)
    finally:
        for pidl in pidls:
            shell32.ILFree(pidl)
