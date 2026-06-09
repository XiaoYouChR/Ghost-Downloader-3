from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orjson import dumps, loads
from PySide6.QtCore import QObject, Signal


@dataclass(frozen=True)
class Setting:
    """一项配置的 schema：键、默认值、可选的校验函数。"""

    key: str
    default: Any
    validate: Callable[[Any], bool] | None = None


class Config(QObject):
    """engine 持有的权威配置。值变了发 changed(key)，引擎据此热应用。"""

    changed = Signal(str)

    def __init__(self, settings: list[Setting], path: Path) -> None:
        super().__init__()
        self._settings = {setting.key: setting for setting in settings}
        self._path = path
        self._values: dict[str, Any] = {}

    def value(self, key: str) -> Any:
        if key in self._values:
            return self._values[key]
        return self._settings[key].default

    def set(self, key: str, value: Any) -> None:
        setting = self._settings[key]
        if setting.validate is not None and not setting.validate(value):
            return
        if value == self.value(key):
            return
        self._values[key] = value
        self.save()
        self.changed.emit(key)

    def load(self) -> None:
        if self._path.exists():
            self._values = loads(self._path.read_bytes())

    def save(self) -> None:
        self._path.write_bytes(dumps(self._values))
