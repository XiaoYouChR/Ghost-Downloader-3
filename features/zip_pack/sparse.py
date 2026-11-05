from __future__ import annotations

import io
import os
from pathlib import Path


class SparseView(io.RawIOBase):
    def __init__(self, size: int, segments: list[tuple[int, bytes | Path]]):
        super().__init__()
        self._size = size
        self._segments = []
        for start, source in sorted(segments, key=lambda segment: segment[0]):
            length = len(source) if isinstance(source, bytes) else os.path.getsize(source)
            self._segments.append((start, start + length, source))
        self._files: dict[Path, io.BufferedReader] = {}
        self._position = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        base = {os.SEEK_SET: 0, os.SEEK_CUR: self._position, os.SEEK_END: self._size}[whence]
        self._position = base + offset
        return self._position

    def readinto(self, buffer) -> int:
        if self._position >= self._size:
            return 0
        for start, end, source in self._segments:
            if start <= self._position < end:
                length = min(len(buffer), end - self._position)
                offset = self._position - start
                if isinstance(source, bytes):
                    data = source[offset:offset + length]
                else:
                    if source not in self._files:
                        self._files[source] = open(source, "rb")
                    file = self._files[source]
                    file.seek(offset)
                    data = file.read(length)
                buffer[:len(data)] = data
                self._position += len(data)
                return len(data)
        raise OSError(f"压缩包的这段数据还没有下载：{self._position}")

    def close(self) -> None:
        for file in self._files.values():
            file.close()
        self._files.clear()
        super().close()
