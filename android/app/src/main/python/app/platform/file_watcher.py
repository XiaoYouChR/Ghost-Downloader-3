from __future__ import annotations

import ctypes
import os
import struct
from collections.abc import Callable

from app.signal import Signal

_libc = ctypes.CDLL("libc.so", use_errno=True)
_libc.inotify_init1.argtypes = (ctypes.c_int,)
_libc.inotify_add_watch.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32)
_libc.inotify_rm_watch.argtypes = (ctypes.c_int, ctypes.c_int)

IN_MODIFY = 0x2
IN_ATTRIB = 0x4
IN_DELETE_SELF = 0x400
IN_MOVE_SELF = 0x800
IN_IGNORED = 0x8000

_WATCH_MASK = IN_MODIFY | IN_ATTRIB | IN_DELETE_SELF | IN_MOVE_SELF
_REMOVAL_MASK = IN_DELETE_SELF | IN_MOVE_SELF | IN_IGNORED
_EVENT = struct.Struct("iIII")


class InotifyFileWatcher:
    fileChanged = Signal()

    def __init__(self, loop, post: Callable):
        self._post = post
        self._fd = _libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
        if self._fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1")
        self._wdToPath: dict[int, str] = {}
        self._pathToWd: dict[str, int] = {}
        loop.add_reader(self._fd, self._onReadable)

    def addPath(self, path: str):
        if path in self._pathToWd:
            return
        wd = _libc.inotify_add_watch(self._fd, path.encode(), _WATCH_MASK)
        if wd >= 0:
            self._wdToPath[wd] = path
            self._pathToWd[path] = wd

    def removePath(self, path: str):
        wd = self._pathToWd.pop(path, None)
        if wd is not None:
            self._wdToPath.pop(wd, None)
            _libc.inotify_rm_watch(self._fd, wd)

    def _onReadable(self):
        try:
            data = os.read(self._fd, 4096)
        except BlockingIOError:
            return
        pos = 0
        while pos < len(data):
            wd, mask, _cookie, nameLen = _EVENT.unpack_from(data, pos)
            pos += _EVENT.size + nameLen
            path = self._wdToPath.get(wd)
            if path is None:
                continue
            if mask & _REMOVAL_MASK:
                self._wdToPath.pop(wd, None)
                self._pathToWd.pop(path, None)
            self._post(self.fileChanged.emit, path)
