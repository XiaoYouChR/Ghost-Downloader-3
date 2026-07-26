from __future__ import annotations

import sys

from loguru import logger

_held = False


def hold() -> None:
    global _held
    if _held:
        return
    try:
        _inhibit()
        _held = True
    except Exception as e:
        logger.opt(exception=e).warning("Failed to inhibit system sleep")


def release() -> None:
    global _held
    if not _held:
        return
    try:
        _uninhibit()
    except Exception as e:
        logger.opt(exception=e).warning("Failed to release sleep inhibit")
    _held = False


# -- platform backends --

if sys.platform == "win32":
    import ctypes

    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001

    def _inhibit() -> None:
        ctypes.windll.kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED
        )

    def _uninhibit() -> None:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)

elif sys.platform == "darwin":
    import ctypes
    import ctypes.util

    _iokit = ctypes.cdll.LoadLibrary(ctypes.util.find_library("IOKit"))
    _cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))

    _cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    _cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    _cf.CFRelease.argtypes = [ctypes.c_void_p]

    _iokit.IOPMAssertionCreateWithName.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _iokit.IOPMAssertionCreateWithName.restype = ctypes.c_int32
    _iokit.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
    _iokit.IOPMAssertionRelease.restype = ctypes.c_int32

    _kCFStringEncodingUTF8 = 0x08000100
    _kIOPMAssertionLevelOn = 255

    def _cfstr(s: str) -> ctypes.c_void_p:
        return _cf.CFStringCreateWithCString(None, s.encode(), _kCFStringEncodingUTF8)

    _NO_IDLE_SLEEP = _cfstr("PreventUserIdleSystemSleep")
    _assertionId = ctypes.c_uint32(0)

    def _inhibit() -> None:
        global _assertionId
        reason = _cfstr("Active download")
        ret = _iokit.IOPMAssertionCreateWithName(
            _NO_IDLE_SLEEP, _kIOPMAssertionLevelOn, reason, ctypes.byref(_assertionId),
        )
        _cf.CFRelease(reason)
        if ret != 0:
            raise RuntimeError(f"IOPMAssertionCreateWithName failed: {ret:#x}")

    def _uninhibit() -> None:
        global _assertionId
        if _assertionId.value:
            _iokit.IOPMAssertionRelease(_assertionId.value)
            _assertionId.value = 0

else:
    # Linux: systemd-logind D-Bus inhibitor lock
    _inhibitFd = None

    def _inhibit() -> None:
        global _inhibitFd
        from PySide6.QtDBus import QDBusConnection, QDBusInterface

        bus = QDBusConnection.systemBus()
        iface = QDBusInterface(
            "org.freedesktop.login1", "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager", bus,
        )
        reply = iface.call("Inhibit", "sleep", "Ghost Downloader", "Active download", "block")
        if reply.type() == reply.ReplyMessage:
            _inhibitFd = reply.arguments()[0]
        else:
            raise RuntimeError(reply.errorMessage())

    def _uninhibit() -> None:
        global _inhibitFd
        _inhibitFd = None
