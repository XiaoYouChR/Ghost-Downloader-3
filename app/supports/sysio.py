import typing
from sys import platform

if platform == "win32":
    import msvcrt
    from ctypes import wintypes, Structure, Union, c_void_p, POINTER, windll, WinError, cast, c_char_p, byref, \
        c_longlong, get_last_error

    INVALID_HANDLE_VALUE = -1

    class _dummy_s(Structure):
        _fields_ = [("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD)]

    class _dummy_u(Union):
        _fields_ = [("DUMMYSTRUCTNAME", _dummy_s), ("Pointer", c_void_p)]

    class OVERLAPPED(Structure):
        _fields_ = [
            ("Internal", POINTER(wintypes.ULONG)),
            ("InternalHigh", POINTER(wintypes.ULONG)),
            ("DUMMYUNIONNAME", _dummy_u),
            ("hEvent", wintypes.HANDLE),
        ]
        _anonymous_ = ("DUMMYUNIONNAME",)

    WriteFile = windll.kernel32.WriteFile
    WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        wintypes.LPDWORD,
        POINTER(OVERLAPPED),
    ]
    WriteFile.restype = wintypes.BOOL

    def check1(result, func, arg):
        if result == 0:
            raise WinError()
        return result

    WriteFile.errcheck = check1

    # _get_osfhandle = ctypes.windll.msvcrt._get_osfhandle
    # _get_osfhandle.argtypes = [ctypes.c_int]
    # _get_osfhandle.restype = ctypes.c_int

    # def check2(result, func, arg):
    #     if result == INVALID_HANDLE_VALUE:
    #         raise ctypes.WinError()
    #     return result

    # _get_osfhandle.errcheck = check2

    def pwrite(fd: typing.Union[int, wintypes.HANDLE], data: bytes, offset: int) -> int:
        # handle = wintypes.HANDLE(_get_osfhandle(fd))
        if isinstance(fd, int):
            handle = wintypes.HANDLE(
                msvcrt.get_osfhandle(fd)
            )  # fuck, fuck, fuck, what's the difference between these two?
        else:
            handle = fd
        written = wintypes.DWORD(0)
        overlapped = OVERLAPPED()
        overlapped.DUMMYSTRUCTNAME.OffsetHigh = wintypes.DWORD(offset >> 32)
        overlapped.DUMMYSTRUCTNAME.Offset = wintypes.DWORD(offset)
        WriteFile(
            handle,
            cast(c_char_p(data), wintypes.LPCVOID),
            len(data),
            byref(written),
            byref(overlapped),
        )
        return written.value

    FSCTL_SET_SPARSE = 0x000900C4
    FILE_BEGIN = 0

    DeviceIoControl = windll.kernel32.DeviceIoControl
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

    SetFilePointerEx = windll.kernel32.SetFilePointerEx
    SetFilePointerEx.argtypes = [
        wintypes.HANDLE,
        c_longlong,
        POINTER(c_longlong),
        wintypes.DWORD,
    ]
    SetFilePointerEx.restype = wintypes.BOOL

    SetEndOfFile = windll.kernel32.SetEndOfFile
    SetEndOfFile.argtypes = [wintypes.HANDLE]
    SetEndOfFile.restype = wintypes.BOOL


    def _raise_winerror(msg: str):
        err = get_last_error()
        raise OSError(err, f"{msg}, WinError={err}")

    def ftruncate(fd: typing.Union[int, wintypes.HANDLE], size: int) -> None:
        if isinstance(fd, int):
            handle = wintypes.HANDLE(
                msvcrt.get_osfhandle(fd)
            )
        else:
            handle = fd

        returned = wintypes.DWORD(0)
        ok = DeviceIoControl(
            handle,
            FSCTL_SET_SPARSE,
            None,
            0,
            None,
            0,
            byref(returned),
            None,
        )
        if not ok:
            _raise_winerror("FSCTL_SET_SPARSE failed")

        newPos = c_longlong()
        ok = SetFilePointerEx(handle, size, byref(newPos), FILE_BEGIN)
        if not ok:
            _raise_winerror("SetFilePointerEx failed")

        ok = SetEndOfFile(handle)
        if not ok:
            _raise_winerror("SetEndOfFile failed")

else:
    # noinspection PyUnresolvedReferences
    from os import pwrite, ftruncate
