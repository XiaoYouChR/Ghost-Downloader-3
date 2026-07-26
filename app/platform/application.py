from __future__ import annotations

import sys
from pathlib import Path
from signal import signal, SIGINT

from PySide6.QtCore import QSharedMemory, QEvent
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication
from loguru import logger

from app.config.constants import DESKTOP_ID, DESKTOP_OBJECT_PATH
from app.platform.android import IS_ANDROID
from app.platform.url_scheme import isLaunchUri
from app.signal_bus import signalBus


def fileUrisFromArgv(argv: list[str]) -> list[str]:
    uris = []
    for arg in argv[1:]:
        if arg.startswith("-") or isLaunchUri(arg):
            continue
        path = Path(arg)
        if path.is_file():
            uris.append(path.resolve().as_uri())
    return uris


class SingletonApplication(QApplication):

    def __init__(self, argv: list[str], key: str):
        super().__init__(argv)
        self._key = key
        self._memory: QSharedMemory | None = None
        self._lockSingleInstance()

        try:
            signal(SIGINT, self._onInterrupt)
        except Exception as e:
            logger.warning("Failed to register SIGINT handler: {}", e)

        if sys.platform == "win32":
            self._registerIpcReceiver()
        elif sys.platform == "linux" and not IS_ANDROID:
            self._registerDbusReceiver()

    def exec(self) -> int:
        try:
            return super().exec()
        finally:
            self._unlockSingleInstance()

    def quit(self) -> None:
        self._unlockSingleInstance()
        super().quit()

    def event(self, e: QEvent) -> bool:
        if isinstance(e, QFileOpenEvent):
            uri = e.url().toString() if not e.url().isEmpty() else Path(e.file()).as_uri()
            if uri and isLaunchUri(uri):
                signalBus.activationRequested.emit()
            elif uri:
                signalBus.openFileRequested.emit([uri])
            return True

        if sys.platform == "darwin" and e.type() == QEvent.Type.ApplicationActivate:
            signalBus.activationRequested.emit()

        return super().event(e)

    def _lockSingleInstance(self) -> None:
        if IS_ANDROID:
            return

        try:
            cleanup = QSharedMemory(self._key)
            if cleanup.attach():
                cleanup.detach()
        except Exception:
            pass

        self._memory = QSharedMemory()
        self._memory.setKey(self._key)

        if self._memory.attach():
            if sys.platform == "win32":
                _sendToRunningWindows()
            elif sys.platform == "linux":
                _sendToRunningLinux()
            sys.exit(-1)

        if not self._memory.create(1):
            try:
                self._memory.attach()
                self._memory.detach()
                if not self._memory.create(1):
                    raise RuntimeError(self._memory.errorString())
            except Exception as e:
                logger.opt(exception=e).error("Failed to create shared memory")
                raise

    def _unlockSingleInstance(self) -> None:
        if self._memory is not None and self._memory.isAttached():
            try:
                self._memory.detach()
            except Exception as e:
                logger.warning("Failed to detach shared memory: {}", e)

    def _onInterrupt(self, _signum, _frame) -> None:
        logger.error("KeyboardInterrupt, quitting")
        self.quit()

    def _registerIpcReceiver(self) -> None:
        self._ipcHwnd = _createIpcWindow()

    def _registerDbusReceiver(self) -> None:
        from PySide6.QtDBus import QDBusConnection

        bus = QDBusConnection.sessionBus()
        if not bus.registerService(DESKTOP_ID):
            return
        self._dbusReceiver = _DesktopBusReceiver()
        bus.registerObject(
            DESKTOP_OBJECT_PATH,
            self._dbusReceiver,
            QDBusConnection.RegisterOption.ExportAllSlots,
        )


# --- IPC: second instance → running instance ---

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    import win32api
    import win32gui

    IPC_CLASS_NAME = "GhostDownloaderIPC"
    COPYDATA_OPEN_FILES = 0x4744
    WM_COPYDATA = 0x004A
    WM_USER_WAKE = 1025

    class _CopyDataStruct(ctypes.Structure):
        _fields_ = [
            ("dwData", ctypes.c_void_p),
            ("cbData", wintypes.DWORD),
            ("lpData", ctypes.c_void_p),
        ]

    def _onIpcWake(hWnd, msg, wParam, lParam):
        signalBus.activationRequested.emit()
        return 0

    def _onIpcCopyData(hWnd, msg, wParam, lParam):
        payload = _CopyDataStruct.from_address(lParam)
        if payload.dwData == COPYDATA_OPEN_FILES:
            raw = ctypes.string_at(payload.lpData, payload.cbData)
            uris = [line for line in raw.decode("utf-16-le").rstrip("\x00").split("\n") if line]
            if uris:
                signalBus.openFileRequested.emit(uris)
        return 1

    _IPC_MESSAGE_MAP = {
        WM_USER_WAKE: _onIpcWake,
        WM_COPYDATA: _onIpcCopyData,
    }

    def _createIpcWindow() -> int:
        hInstance = win32api.GetModuleHandle(None)
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = _IPC_MESSAGE_MAP
        wc.hInstance = hInstance
        wc.lpszClassName = IPC_CLASS_NAME
        win32gui.RegisterClass(wc)
        return win32gui.CreateWindow(
            IPC_CLASS_NAME, IPC_CLASS_NAME, 0,
            0, 0, 0, 0,
            0, 0, hInstance, None,
        )

    def _sendToRunningWindows() -> None:
        hWnd = win32gui.FindWindow(IPC_CLASS_NAME, None)
        if not hWnd:
            return
        uris = fileUrisFromArgv(sys.argv)
        if uris:
            blob = "\n".join(uris).encode("utf-16-le") + b"\x00\x00"
            data = ctypes.create_string_buffer(blob, len(blob))
            payload = _CopyDataStruct(COPYDATA_OPEN_FILES, len(blob), ctypes.cast(data, ctypes.c_void_p))
            ctypes.windll.user32.SendMessageW(hWnd, WM_COPYDATA, 0, ctypes.byref(payload))
        else:
            win32gui.SendMessage(hWnd, WM_USER_WAKE, 0, 0)
        win32gui.SetForegroundWindow(hWnd)


if sys.platform == "linux":
    from PySide6.QtCore import QObject, Slot, ClassInfo

    @ClassInfo({"D-Bus Interface": "org.freedesktop.Application"})
    class _DesktopBusReceiver(QObject):
        @Slot("QStringList", "QVariantMap")
        def Open(self, uris, platformData):
            if any(isLaunchUri(u) for u in uris):
                signalBus.activationRequested.emit()
                return
            uris = [uri for uri in uris if uri]
            if uris:
                signalBus.openFileRequested.emit(uris)

        @Slot("QVariantMap")
        def Activate(self, platformData):
            signalBus.activationRequested.emit()

    def _sendToRunningLinux() -> None:
        from PySide6.QtDBus import QDBusConnection, QDBusInterface

        uris = fileUrisFromArgv(sys.argv)
        interface = QDBusInterface(
            DESKTOP_ID, DESKTOP_OBJECT_PATH,
            "org.freedesktop.Application",
            QDBusConnection.sessionBus(),
        )
        if uris:
            interface.call("Open", uris, {})
        else:
            interface.call("Activate", {})
