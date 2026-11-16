from __future__ import annotations

from functools import cache, partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.task import TaskStatus


def setWindowsProgress(hwnd: int, status: TaskStatus | None, progress: float | None) -> None:
    from app.models.task import TaskStatus

    taskbarList = createTaskbarList()
    if taskbarList is None:
        return
    setState, setValue = taskbarList
    TBPF_NOPROGRESS, TBPF_INDETERMINATE, TBPF_NORMAL, TBPF_ERROR, TBPF_PAUSED = 0, 1, 2, 4, 8
    colors = {TaskStatus.PAUSED: TBPF_PAUSED, TaskStatus.FAILED: TBPF_ERROR}
    if status is None or status == TaskStatus.COMPLETED:
        setState(hwnd, TBPF_NOPROGRESS)
    elif progress is None and status not in colors:
        setState(hwnd, TBPF_INDETERMINATE)
    else:
        setState(hwnd, colors.get(status, TBPF_NORMAL))
        setValue(hwnd, round((100 if progress is None else progress) * 10), 1000)


def addTaskbarButton(hwnd: int) -> None:
    import ctypes

    GWL_STYLE, GWL_EXSTYLE = -16, -20
    WS_MINIMIZEBOX, WS_SYSMENU, WS_EX_APPWINDOW = 0x00020000, 0x00080000, 0x00040000
    user32 = ctypes.windll.user32
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) | WS_EX_APPWINDOW)
    user32.SetWindowLongPtrW(hwnd, GWL_STYLE, user32.GetWindowLongPtrW(hwnd, GWL_STYLE) | WS_MINIMIZEBOX | WS_SYSMENU)


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
