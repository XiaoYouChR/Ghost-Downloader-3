from __future__ import annotations

from functools import cache, partial


def setWindowsProgress(hwnd: int, isRunning: bool, progress: float | None) -> None:
    taskbarList = createTaskbarList()
    if taskbarList is None:
        return
    setState, setValue = taskbarList
    if not isRunning:
        setState(hwnd, 0)  # TBPF_NOPROGRESS
    elif progress is None:
        setState(hwnd, 1)  # TBPF_INDETERMINATE
    else:
        setState(hwnd, 2)  # TBPF_NORMAL
        setValue(hwnd, round(progress * 10), 1000)


@cache
def createTaskbarList():
    from ctypes import HRESULT, POINTER, WINFUNCTYPE, byref, c_byte, c_int, c_uint64, c_void_p, oledll

    from loguru import logger

    # Qt6 和 pywin32 都没有封装 ITaskbarList3，只能按 shobjidl_core.h 的虚表序号直调
    ole32 = oledll.ole32
    clsid = (c_byte * 16)()
    iid = (c_byte * 16)()
    pointer = c_void_p()
    try:
        ole32.CLSIDFromString("{56FDF344-FD6D-11d0-958A-006097C9A090}", byref(clsid))
        ole32.IIDFromString("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}", byref(iid))
        ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid), byref(pointer))  # CLSCTX_INPROC_SERVER
    except OSError as e:
        logger.warning("无法创建 ITaskbarList3: {}", e)
        return None
    vtable = POINTER(c_void_p).from_address(pointer.value)
    WINFUNCTYPE(HRESULT, c_void_p)(vtable[3])(pointer)  # HrInit
    setValue = WINFUNCTYPE(HRESULT, c_void_p, c_void_p, c_uint64, c_uint64)(vtable[9])
    setState = WINFUNCTYPE(HRESULT, c_void_p, c_void_p, c_int)(vtable[10])
    return partial(setState, pointer), partial(setValue, pointer)


def setLauncherProgress(progress: float | None) -> None:
    from PySide6.QtDBus import QDBusConnection, QDBusMessage

    from app.config.constants import DESKTOP_ID, DESKTOP_OBJECT_PATH

    # Unity LauncherEntry 没有不确定进度，算不出时只能隐藏
    message = QDBusMessage.createSignal(DESKTOP_OBJECT_PATH, "com.canonical.Unity.LauncherEntry", "Update")
    message.setArguments([
        f"application://{DESKTOP_ID}.desktop",
        {"progress": (progress or 0.0) / 100, "progress-visible": progress is not None},
    ])
    QDBusConnection.sessionBus().send(message)
