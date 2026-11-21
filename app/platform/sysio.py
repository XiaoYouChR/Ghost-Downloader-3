from __future__ import annotations

import errno
import os
from pathlib import Path
from sys import platform
from tempfile import NamedTemporaryFile


def writeAtomic(path: Path, data: bytes) -> None:
    """Replace a file using a flushed temporary file on the same filesystem."""
    temporaryPath = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as output:
            temporaryPath = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporaryPath.replace(path)
        temporaryPath = None
    finally:
        if temporaryPath is not None:
            temporaryPath.unlink(missing_ok=True)

    if os.name == "posix":
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            try:
                os.fsync(fd)
            except OSError as error:
                if error.errno not in {errno.EINVAL, errno.ENOTSUP}:
                    raise
        finally:
            os.close(fd)

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
