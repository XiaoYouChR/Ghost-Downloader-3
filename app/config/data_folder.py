from __future__ import annotations

import os
from pathlib import Path


class PathSerializer:
    """Data Folder 内的路径随 Data Folder 搬迁。"""

    PLACEHOLDER = "{data}"

    def __init__(self, dataFolder: Path):
        self._dataFolder = Path(os.path.abspath(dataFolder))

    def serialize(self, value):
        if isinstance(value, list):
            return [self.serialize(item) for item in value]
        if not value:
            return value
        path = Path(os.path.abspath(value))
        if not path.is_relative_to(self._dataFolder):
            return value
        relative = path.relative_to(self._dataFolder).as_posix()
        return self.PLACEHOLDER if relative == "." else f"{self.PLACEHOLDER}/{relative}"

    def deserialize(self, value):
        if isinstance(value, list):
            return [self.deserialize(item) for item in value]
        if not isinstance(value, str) or not value:
            return value
        if value == self.PLACEHOLDER or value.startswith(self.PLACEHOLDER + "/"):
            return (self._dataFolder / value.removeprefix(self.PLACEHOLDER).lstrip("/")).as_posix()

        # 旧版存的是绝对路径
        path = Path(value)
        parts = path.parts
        if self._dataFolder.name not in parts or path.exists():
            return value
        index = len(parts) - 1 - parts[::-1].index(self._dataFolder.name)
        moved = self._dataFolder.joinpath(*parts[index + 1:])
        return moved.as_posix() if moved.exists() else value
