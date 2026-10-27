from __future__ import annotations

from sys import platform

if platform == "win32":
    import msvcrt
    from collections.abc import Buffer

    import pywintypes
    import win32file
    import winioctlcon
    from loguru import logger

    def pwrite(fd: int, data: Buffer, offset: int) -> int:
        overlapped = pywintypes.OVERLAPPED()
        overlapped.Offset = offset & 0xFFFFFFFF
        overlapped.OffsetHigh = offset >> 32
        try:
            _, written = win32file.WriteFile(msvcrt.get_osfhandle(fd), data, overlapped)
        except pywintypes.error as e:
            raise OSError(None, e.strerror, None, e.winerror) from None
        return written

    def ftruncate(fd: int, size: int) -> None:
        handle = msvcrt.get_osfhandle(fd)
        try:
            win32file.DeviceIoControl(handle, winioctlcon.FSCTL_SET_SPARSE, None, None)
        except pywintypes.error as e:
            logger.debug("文件系统不支持稀疏文件，使用常规预分配：{}", e.strerror)
        try:
            win32file.SetFileInformationByHandle(handle, win32file.FileEndOfFileInfo, size)
        except pywintypes.error as e:
            raise OSError(None, e.strerror, None, e.winerror) from None

else:
    # noinspection PyUnresolvedReferences
    from os import pwrite, ftruncate
