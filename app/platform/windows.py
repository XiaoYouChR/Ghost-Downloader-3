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
