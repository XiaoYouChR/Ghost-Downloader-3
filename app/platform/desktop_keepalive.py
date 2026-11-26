from __future__ import annotations

import sys
from collections.abc import Callable

from loguru import logger


def buildSleepInhibitor() -> Callable[[bool], None]:
    release: Callable[[], None] | None = None

    def set(isActive: bool) -> None:
        nonlocal release
        if not isActive:
            if release is None:
                return
            fn, release = release, None
            try:
                fn()
            except Exception as e:
                logger.opt(exception=e).warning("Failed to release sleep inhibit")
            return
        if release is not None:
            return
        try:
            release = acquire()
        except Exception as e:
            logger.opt(exception=e).warning("Failed to inhibit system sleep")

    return set


if sys.platform == "win32":
    import ctypes

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    setThreadExecutionState = ctypes.WinDLL("kernel32").SetThreadExecutionState
    setThreadExecutionState.argtypes = [ctypes.c_uint32]
    setThreadExecutionState.restype = ctypes.c_uint32

    def acquire() -> Callable[[], None] | None:
        try:
            if not setThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED):
                logger.warning("SetThreadExecutionState returned 0")
                return None
        except OSError as e:
            logger.opt(exception=e).warning("Failed to inhibit system sleep")
            return None

        def release() -> None:
            try:
                setThreadExecutionState(ES_CONTINUOUS)
            except OSError as e:
                logger.opt(exception=e).warning("Failed to release sleep inhibit")

        return release

elif sys.platform == "darwin":
    import ctypes

    iokit = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")
    cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFRelease.argtypes = [ctypes.c_void_p]

    iokit.IOPMAssertionCreateWithName.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    iokit.IOPMAssertionCreateWithName.restype = ctypes.c_uint32
    iokit.IOPMAssertionRelease.argtypes = [ctypes.c_uint32]
    iokit.IOPMAssertionRelease.restype = ctypes.c_uint32

    CF_STRING_ENCODING_UTF8 = 0x08000100
    IOPM_ASSERTION_LEVEL_ON = 255

    def toCfString(text: str) -> ctypes.c_void_p:
        return cf.CFStringCreateWithCString(None, text.encode(), CF_STRING_ENCODING_UTF8)

    NO_IDLE_SLEEP = toCfString("PreventUserIdleSystemSleep")

    def acquire() -> Callable[[], None]:
        assertionId = ctypes.c_uint32(0)
        reason = toCfString("Active download")
        ret = iokit.IOPMAssertionCreateWithName(
            NO_IDLE_SLEEP, IOPM_ASSERTION_LEVEL_ON, reason, ctypes.byref(assertionId),
        )
        cf.CFRelease(reason)
        if ret != 0:
            raise RuntimeError(f"IOPMAssertionCreateWithName failed: {ret:#x}")
        aid = assertionId.value
        return lambda: iokit.IOPMAssertionRelease(aid)

else:
    INHIBIT_SUSPEND = 4

    # logind 的 sleep 锁会拦住合盖和手动睡眠。logind 的 idle 锁会被 GNOME 和 KDE 忽略。
    # 因此先走桌面会话，无桌面会话时再退回 logind idle。
    # PySide6 的 QDBusInterface.call 会把 int 封送成有符号 i，必须经 QMetaObject.invokeMethod 按签名发 uint32。
    def acquire() -> Callable[[], None] | None:
        from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, Qt
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusUnixFileDescriptor

        from app.config.constants import DESKTOP_ID

        sessionBus = QDBusConnection.sessionBus()
        busIface = sessionBus.interface()
        if busIface is not None:
            for service, path, interface, args, uninhibit in (
                ("org.gnome.SessionManager", "/org/gnome/SessionManager", "org.gnome.SessionManager",
                 (Q_ARG("QString", DESKTOP_ID), Q_ARG("uint", 0), Q_ARG("QString", "Active download"),
                  Q_ARG("uint", INHIBIT_SUSPEND)), "Uninhibit"),
                ("org.freedesktop.PowerManagement", "/org/freedesktop/PowerManagement/Inhibit",
                 "org.freedesktop.PowerManagement.Inhibit",
                 (Q_ARG("QString", "Ghost Downloader"), Q_ARG("QString", "Active download")), "UnInhibit"),
            ):
                if not busIface.isServiceRegistered(service).value():
                    continue
                iface = QDBusInterface(service, path, interface, sessionBus)
                if not iface.isValid():
                    continue
                try:
                    cookie = QMetaObject.invokeMethod(
                        iface, "Inhibit", Qt.ConnectionType.DirectConnection, Q_RETURN_ARG("uint"), *args,
                    )
                except RuntimeError as e:
                    logger.debug("Sleep inhibit via {} failed: {}", service, e)
                    continue
                if not iface.lastError().isValid() and cookie is not None:
                    def release(i=iface, m=uninhibit, c=cookie, s=service) -> None:
                        ok = QMetaObject.invokeMethod(i, m, Qt.ConnectionType.DirectConnection, Q_ARG("uint", c))
                        if not ok or i.lastError().isValid():
                            logger.warning("Failed to release sleep inhibit via {}: {}", s, i.lastError().message())
                    return release
                logger.debug("Sleep inhibit via {} failed: {}", service, iface.lastError().message())

        iface = QDBusInterface(
            "org.freedesktop.login1", "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager", QDBusConnection.systemBus(),
        )
        reply = iface.call("Inhibit", "idle", "Ghost Downloader", "Active download", "block")
        if reply.type() == reply.MessageType.ReplyMessage:
            fd = reply.arguments()[0]
            if isinstance(fd, QDBusUnixFileDescriptor) and fd.isValid():
                holder = [fd]
                return holder.clear
        raise RuntimeError(reply.errorMessage() or "Invalid logind inhibitor file descriptor")
