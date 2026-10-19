import errno
import os
import sys

import pytest

from app.platform.sysio import ftruncate, pwrite

O_BINARY = getattr(os, "O_BINARY", 0)


def test_flush_readonly_memoryview_at_offset(tmp_path):
    path = tmp_path / "out.bin"
    fd = os.open(path, os.O_RDWR | os.O_CREAT | O_BINARY)
    data = memoryview(b"ghost-downloader").toreadonly()
    try:
        ftruncate(fd, 123 + len(data))
        assert pwrite(fd, data, 123) == len(data)
    finally:
        os.close(fd)

    assert path.read_bytes() == bytes(123) + b"ghost-downloader"


def test_flush_to_readonly_file_fails_like_os(tmp_path):
    path = tmp_path / "out.bin"
    path.write_bytes(b"")
    fd = os.open(path, os.O_RDONLY | O_BINARY)
    try:
        with pytest.raises(OSError) as info:
            pwrite(fd, b"x", 0)
    finally:
        os.close(fd)

    if sys.platform == "win32":
        assert info.value.winerror == 5
        assert info.value.errno == errno.EACCES
    else:
        assert info.value.errno == errno.EBADF
