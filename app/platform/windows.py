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
