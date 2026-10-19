from __future__ import annotations


from sys import platform

if platform == "win32":
    import msvcrt
    from ctypes import wintypes, Structure, c_void_p, POINTER, WinDLL, WinError, get_last_error, c_char_p, byref, \
        c_longlong

    # 独立实例，不改全局 windll 上的 argtypes
    kernel32 = WinDLL("kernel32", use_last_error=True)

    class OVERLAPPED(Structure):
        _fields_ = [
            ("Internal", c_void_p),
            ("InternalHigh", c_void_p),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    WriteFile = kernel32.WriteFile
    WriteFile.argtypes = [
        wintypes.HANDLE,
        c_char_p,
        wintypes.DWORD,
        wintypes.LPDWORD,
        POINTER(OVERLAPPED),
    ]
    WriteFile.restype = wintypes.BOOL

    def pwrite(fd: int, data: bytes | memoryview, offset: int) -> int:
        # 实测比 PyObject_GetBuffer 零拷贝快
        buffer = bytes(data)
        overlapped = OVERLAPPED(Offset=offset & 0xFFFFFFFF, OffsetHigh=offset >> 32)
        # 同步写文件要么全部写完要么失败，所以不取实际写入字节数
        if not WriteFile(msvcrt.get_osfhandle(fd), buffer, len(buffer), None, byref(overlapped)):
            raise WinError(get_last_error())
        return len(buffer)

    FSCTL_SET_SPARSE = 0x000900C4
    FILE_BEGIN = 0

    DeviceIoControl = kernel32.DeviceIoControl
    DeviceIoControl.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        POINTER(wintypes.DWORD),
        wintypes.LPVOID,
    ]
    DeviceIoControl.restype = wintypes.BOOL

    SetFilePointerEx = kernel32.SetFilePointerEx
    SetFilePointerEx.argtypes = [
        wintypes.HANDLE,
        c_longlong,
        POINTER(c_longlong),
        wintypes.DWORD,
    ]
    SetFilePointerEx.restype = wintypes.BOOL

    SetEndOfFile = kernel32.SetEndOfFile
    SetEndOfFile.argtypes = [wintypes.HANDLE]
    SetEndOfFile.restype = wintypes.BOOL

    # 不用 os.ftruncate：它在 Windows 上扩展文件时会逐块写零，预分配大文件很慢
    def ftruncate(fd: int, size: int) -> None:
        handle = msvcrt.get_osfhandle(fd)
        if not DeviceIoControl(handle, FSCTL_SET_SPARSE, None, 0, None, 0, byref(wintypes.DWORD()), None):
            from loguru import logger
            logger.debug("文件系统不支持稀疏文件，使用常规预分配")
        if not SetFilePointerEx(handle, size, None, FILE_BEGIN) or not SetEndOfFile(handle):
            raise WinError(get_last_error())

else:
    # noinspection PyUnresolvedReferences
    from os import pwrite, ftruncate
