from __future__ import annotations

import sys

from PySide6.QtCore import QOperatingSystemVersion


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


if sys.platform == "win32":
    import ctypes
    from contextlib import suppress
    from ctypes import WinDLL, wintypes
    from typing import TYPE_CHECKING

    from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication
    from loguru import logger

    from app.signal import Signal

    if TYPE_CHECKING:
        from PySide6.QtGui import QIcon

    _user32 = WinDLL("user32", use_last_error=True)
    _user32.ShutdownBlockReasonCreate.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    _user32.ShutdownBlockReasonCreate.restype = wintypes.BOOL
    _user32.ShutdownBlockReasonDestroy.argtypes = [wintypes.HWND]
    _user32.ShutdownBlockReasonDestroy.restype = wintypes.BOOL

    class ShutdownListener(QAbstractNativeEventFilter):
        triggered = Signal()

        def __init__(self, reason: str, icon: QIcon) -> None:
            super().__init__()
            from PySide6.QtGui import QWindow

            self._reason = reason[:255]
            self._window = QWindow()
            self._window.setTitle("Ghost Downloader")
            self._window.setIcon(icon)
            self._window.create()
            self._hwnd = int(self._window.winId())
            QCoreApplication.instance().installNativeEventFilter(self)

        def nativeEventFilter(self, eventType, message):
            if bytes(eventType) != b"windows_generic_MSG":
                return False, 0
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0011:  # WM_QUERYENDSESSION
                try:
                    if not _user32.ShutdownBlockReasonCreate(self._hwnd, self._reason):
                        logger.warning("阻止系统关机失败: {}", ctypes.get_last_error())
                except OSError as e:
                    logger.warning("阻止系统关机失败: {}", e)
            elif msg.message == 0x0016:  # WM_ENDSESSION
                if msg.wParam:
                    self.triggered.emit()
                else:
                    with suppress(OSError):
                        _user32.ShutdownBlockReasonDestroy(self._hwnd)
            # 必须放行给 Qt，否则取消关机后 QWindowsSessionManager 不会解锁输入
            return False, 0

        def close(self) -> None:
            with suppress(OSError):
                _user32.ShutdownBlockReasonDestroy(self._hwnd)
            QCoreApplication.instance().removeNativeEventFilter(self)
            self._window.deleteLater()
