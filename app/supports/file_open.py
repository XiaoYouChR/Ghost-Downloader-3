"""跨实例打开文件的传输层: 第二个实例把本次启动交给运行中的实例 (sendToRunningInstance);
运行中的实例从 argv / WM_COPYDATA / D-Bus 收下, 归一成 file:// URI 经 signalBus 投递。
"""

import sys
from pathlib import Path

from app.supports.signal_bus import signalBus

COPYDATA_OPEN_FILES = 0x4744


def fileUrisFromArgv(argv: list[str]) -> list[str]:
    # 归一成 file:// URI: 裸路径会被 featureService._toUrl 当成 http:// 而失效
    uris = []
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        path = Path(arg)
        if path.is_file():
            uris.append(path.resolve().as_uri())
    return uris


if sys.platform == "win32":
    import ctypes
    import win32gui
    from ctypes import wintypes

    WM_COPYDATA = 0x004A
    WM_USER_WAKE = 1024 + 1

    class _CopyDataStruct(ctypes.Structure):
        _fields_ = [
            ("dwData", ctypes.c_void_p),
            ("cbData", wintypes.DWORD),
            ("lpData", ctypes.c_void_p),
        ]

    def sendToRunningInstance() -> None:
        hWnd = win32gui.FindWindow(None, "Ghost Downloader")
        if not hWnd:
            return
        uris = fileUrisFromArgv(sys.argv)
        if uris:
            # WM_COPYDATA 要传结构体指针, 只能走 ctypes
            blob = "\n".join(uris).encode("utf-16-le") + b"\x00\x00"
            data = ctypes.create_string_buffer(blob, len(blob))
            payload = _CopyDataStruct(COPYDATA_OPEN_FILES, len(blob), ctypes.cast(data, ctypes.c_void_p))
            ctypes.windll.user32.SendMessageW(hWnd, WM_COPYDATA, 0, ctypes.byref(payload))
        else:
            win32gui.SendMessage(hWnd, WM_USER_WAKE, 0, 0)
        win32gui.SetForegroundWindow(hWnd)

    def fileUrisFromCopyData(lParam: int) -> list[str]:
        payload = _CopyDataStruct.from_address(lParam)
        if payload.dwData != COPYDATA_OPEN_FILES:
            return []
        raw = ctypes.string_at(payload.lpData, payload.cbData)
        return [line for line in raw.decode("utf-16-le").rstrip("\x00").split("\n") if line]


if sys.platform == "linux":
    from PySide6.QtCore import QObject, Slot, ClassInfo

    from app.supports.config import DESKTOP_ID, DESKTOP_OBJECT_PATH

    @ClassInfo({"D-Bus Interface": "org.freedesktop.Application"})
    class DesktopBusReceiver(QObject):
        @Slot("QStringList", "QVariantMap")
        def Open(self, uris, platformData):
            uris = [uri for uri in uris if uri]
            if uris:
                signalBus.openFileRequested.emit(uris)

        @Slot("QVariantMap")
        def Activate(self, platformData):
            signalBus.showMainWindow.emit()

    def sendToRunningInstance() -> None:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface

        uris = fileUrisFromArgv(sys.argv)
        interface = QDBusInterface(
            DESKTOP_ID, DESKTOP_OBJECT_PATH, "org.freedesktop.Application", QDBusConnection.sessionBus()
        )
        if uris:
            interface.call("Open", uris, {})
        else:
            interface.call("Activate", {})
