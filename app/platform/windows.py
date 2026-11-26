from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes

from loguru import logger
from PySide6.QtCore import QAbstractNativeEventFilter, QOperatingSystemVersion


def isGreaterEqualWin10() -> bool:
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() >= 10


def isWin10() -> bool:
    return isGreaterEqualWin10() and sys.getwindowsversion().build < 22000


def isLessThanWin10() -> bool:
    cv = QOperatingSystemVersion.current()
    return sys.platform == "win32" and cv.majorVersion() < 10


def isGreaterEqualWin11() -> bool:
    return isGreaterEqualWin10() and sys.getwindowsversion().build >= 22000


def emptyWorkingSet() -> bool:
    if sys.platform != "win32":
        return False

    from ctypes import WinDLL, wintypes

    kernel32 = WinDLL("kernel32", use_last_error=True)
    psapi = WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
    psapi.EmptyWorkingSet.restype = wintypes.BOOL
    return bool(psapi.EmptyWorkingSet(kernel32.GetCurrentProcess()))


def setAnimationFrameRate(frameRate: float) -> None:
    if frameRate <= 60:
        return
    from ctypes import WinDLL, c_int, c_void_p

    from loguru import logger

    try:
        qtCore = WinDLL("Qt6Core.dll")
        instance = getattr(qtCore, "?instance@QUnifiedTimer@@SAPEAV1@XZ")
        setTimingInterval = getattr(qtCore, "?setTimingInterval@QUnifiedTimer@@QEAAXH@Z")
    except (OSError, AttributeError) as e:
        logger.warning("无法调整 Qt 动画间隔，保持默认: {}", e)
        return
    instance.restype = c_void_p
    setTimingInterval.argtypes = [c_void_p, c_int]
    setTimingInterval(instance(), round(1000 / frameRate))


class WindowsShutdownHandler(QAbstractNativeEventFilter):
    WM_QUERYENDSESSION = 0x0011
    WM_ENDSESSION = 0x0016

    def __init__(
        self,
        application,
        hasActiveTorrents: Callable[[], bool],
        onShutdown: Callable[[], None],
    ):
        super().__init__()
        self._application = application
        self._hasActiveTorrents = hasActiveTorrents
        self._onShutdown = onShutdown
        self._pending = False
        self._handled = False
        self._reasonWindow: int | None = None
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.ShutdownBlockReasonCreate.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        self._user32.ShutdownBlockReasonCreate.restype = wintypes.BOOL
        self._user32.ShutdownBlockReasonDestroy.argtypes = [wintypes.HWND]
        self._user32.ShutdownBlockReasonDestroy.restype = wintypes.BOOL
        application.installNativeEventFilter(self)

    def nativeEventFilter(self, eventType, message) -> tuple[bool, int]:
        if bytes(eventType) != b"windows_generic_MSG":
            return False, 0

        msg = wintypes.MSG.from_address(int(message))
        if msg.message == self.WM_QUERYENDSESSION:
            if not self._hasActiveTorrents():
                return False, 0
            self._pending = True
            if self._reasonWindow is None and msg.hWnd:
                # Let hidden tray apps finish saving during WM_ENDSESSION.
                if self._user32.ShutdownBlockReasonCreate(msg.hWnd, "Saving download progress"):
                    self._reasonWindow = msg.hWnd
                else:
                    logger.warning("Could not register the Windows shutdown reason: {}", ctypes.get_last_error())
            return False, 0

        if msg.message != self.WM_ENDSESSION or not self._pending:
            return False, 0
        if not msg.wParam:
            self._pending = False
            self._destroyReason()
            return False, 0
        if self._handled:
            return True, 0

        self._handled = True
        try:
            self._onShutdown()
        except Exception as e:
            logger.opt(exception=e).error("Failed to save download state during Windows shutdown")
        finally:
            self._destroyReason()
            self._application.quit()
        return True, 0

    def close(self) -> None:
        self._destroyReason()
        self._application.removeNativeEventFilter(self)

    def _destroyReason(self) -> None:
        if self._reasonWindow is None:
            return
        if not self._user32.ShutdownBlockReasonDestroy(self._reasonWindow):
            logger.warning("Could not clear the Windows shutdown reason: {}", ctypes.get_last_error())
        self._reasonWindow = None
