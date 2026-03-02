from sys import platform
import typing

if platform == "win32":
    import msvcrt
    from ctypes import wintypes, Structure, Union, c_void_p, POINTER, windll, WinError, cast, c_char_p, byref

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

else:
    from os import pwrite
