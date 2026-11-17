from __future__ import annotations

import ctypes
from ctypes import (
    POINTER, byref, c_byte, c_int, c_short, c_uint64, c_ulong, c_ushort, c_void_p, c_wchar_p,
)
from functools import cache, partial

from loguru import logger

from app.models.task import TaskStatus


def setWindowsProgress(hwnd: int, status: TaskStatus | None, progress: float | None) -> None:
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


def setWindowAppId(hwnd: int, appId: str | None) -> None:
    from ctypes import HRESULT, WINFUNCTYPE, wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", wintypes.BYTE * 8)]

    class PROPERTYKEY(ctypes.Structure):
        _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]

    class PROPVARIANT_VALUE(ctypes.Union):
        _fields_ = [("boolVal", c_short), ("pwszVal", c_wchar_p)]

    class PROPVARIANT(ctypes.Structure):
        _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort), ("value", PROPVARIANT_VALUE)]

    VT_EMPTY, VT_BOOL, VT_LPWSTR = 0, 11, 31
    shell32 = ctypes.windll.shell32
    shell32.SHGetPropertyStoreForWindow.argtypes = [
        wintypes.HWND, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHGetPropertyStoreForWindow.restype = HRESULT
    store = ctypes.c_void_p()
    iid = GUID(0x886D8EEB, 0x8CF2, 0x4446, (0x8D, 0x02, 0xCD, 0xBA, 0x1D, 0xBD, 0xCF, 0x99))
    if shell32.SHGetPropertyStoreForWindow(hwnd, ctypes.byref(iid), ctypes.byref(store)):
        logger.warning("无法取得窗口属性: {}", ctypes.GetLastError())
        return
    vtable = ctypes.POINTER(ctypes.c_void_p).from_address(store.value)
    setValue = WINFUNCTYPE(HRESULT, c_void_p, ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))(vtable[6])
    release = WINFUNCTYPE(c_ulong, c_void_p)(vtable[2])
    fmtid = GUID(0x9F4C2855, 0x9F79, 0x4B39, (0xA8, 0xD0, 0xE1, 0xD4, 0x2D, 0xE1, 0xD5, 0xF3))

    def put(pid: int, variant: PROPVARIANT) -> None:
        key = PROPERTYKEY(fmtid, pid)
        if setValue(store, ctypes.byref(key), ctypes.byref(variant)):
            logger.warning("无法设置窗口 AppUserModelID")

    if appId is None:
        put(9, PROPVARIANT(VT_EMPTY))
        put(5, PROPVARIANT(VT_EMPTY))
    else:
        # 先禁止固定，再写 ID。任务栏只在 ID 变化时重新分组
        put(9, PROPVARIANT(VT_BOOL, value=PROPVARIANT_VALUE(boolVal=-1)))
        put(5, PROPVARIANT(VT_LPWSTR, value=PROPVARIANT_VALUE(pwszVal=appId)))
    release(store)


def addTaskbarButton(hwnd: int) -> None:
    GWL_STYLE, GWL_EXSTYLE = -16, -20
    WS_MINIMIZEBOX, WS_SYSMENU, WS_EX_APPWINDOW = 0x00020000, 0x00080000, 0x00040000
    user32 = ctypes.windll.user32
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) | WS_EX_APPWINDOW)
    user32.SetWindowLongPtrW(hwnd, GWL_STYLE, user32.GetWindowLongPtrW(hwnd, GWL_STYLE) | WS_MINIMIZEBOX | WS_SYSMENU)


def minimizeWithoutActivating(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    # Qt 对 WA_ShowWithoutActivating 的窗口会把 SW_SHOWMINIMIZED 改成 SW_SHOWNOACTIVATE
    from ctypes import wintypes

    addTaskbarButton(hwnd)

    class WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT), ("showCmd", wintypes.UINT),
                    ("ptMinPosition", wintypes.POINT), ("ptMaxPosition", wintypes.POINT),
                    ("rcNormalPosition", wintypes.RECT)]

    SW_SHOWMINNOACTIVE = 7
    user32 = ctypes.windll.user32
    placement = WINDOWPLACEMENT()
    placement.length = ctypes.sizeof(WINDOWPLACEMENT)
    user32.GetWindowPlacement(hwnd, ctypes.byref(placement))
    placement.showCmd = SW_SHOWMINNOACTIVE
    placement.rcNormalPosition = wintypes.RECT(x, y, x + width, y + height)
    user32.SetWindowPlacement(hwnd, ctypes.byref(placement))


@cache
def createTaskbarList():
    # Qt6 和 pywin32 都没有封装 ITaskbarList3，只能按 shobjidl_core.h 的虚表序号直调
    from ctypes import HRESULT, WINFUNCTYPE, oledll

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
