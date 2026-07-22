from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Signal

from app.config.cfg import cfg, ConfigItem

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from app.models.task import Task, TaskOptions
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.speed_meter import SpeedMeter
    from PySide6.QtWidgets import QWidget
    from qfluentwidgets import FluentIcon
    from app.view.components.setting_card_group import CollapsibleSettingCardGroup


@dataclass(frozen=True)
class FileType:
    extensions: tuple[str, ...]
    displayName: str
    mimeType: str
    icon: str


class TaskParser:
    priority: int = 100
    pack: FeaturePack | None = None
    delegate: Callable[[TaskOptions], Awaitable[Task]] | None = None

    def match(self, options: TaskOptions) -> bool:
        raise NotImplementedError

    def matchPassive(self, options: TaskOptions) -> bool:
        return self.match(options)

    async def parse(self, options: TaskOptions) -> Task:
        raise NotImplementedError


class PackConfig:
    createRuntimeCard: Callable[..., QWidget] | None = None
    submit: Callable[..., str] | None = None
    associateFileTypes: ConfigItem | None = None
    _items: dict[str, ConfigItem] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for attrName, attrValue in cls.__dict__.items():
            if isinstance(attrValue, ConfigItem):
                setattr(cfg.__class__, f"pack_{cls.__name__}_{attrName}", attrValue)
                PackConfig._items[attrValue.key] = attrValue

    @classmethod
    def load(cls) -> None:
        if not cls._items:
            return
        import json
        try:
            with open(cfg.file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        for k, v in data.items():
            if not isinstance(v, dict):
                if k in cls._items:
                    cls._items[k].deserializeFrom(v)
            else:
                for name, value in v.items():
                    if (key := k + "." + name) in cls._items:
                        cls._items[key].deserializeFrom(value)

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        return []

    def isFileAssociationEnabled(self) -> bool:
        return True

    def fileAssociationToggle(self) -> Signal | None:
        return None

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)


class BinaryRuntime:
    parse: Callable[[TaskOptions], Awaitable[Task]] | None = None
    name: str = ""
    canInstall: bool = False
    # 自描述展示信息（title 用 QT_TRANSLATE_NOOP 声明原文，展示端 translate）
    title: str = ""
    description: str = ""
    icon: FluentIcon | None = None
    isRecommended: bool = False

    @property
    def runtimeId(self) -> str:
        cls = type(self)
        return f"{cls.__module__}.{cls.__qualname__}"

    def path(self) -> str:
        raise NotImplementedError

    async def probeVersion(self) -> str:
        path = self.path()
        if not path:
            return ""
        process = await asyncio.create_subprocess_exec(
            path, "--version",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return ""
        lines = stdout.decode("utf-8", errors="ignore").splitlines()
        return lines[0].strip() if lines else ""

    async def installTask(self) -> Task:
        raise NotImplementedError


class PackPage:
    icon: ...
    title: str = ""


@dataclass(frozen=True)
class PackServices:
    coroutineRunner: CoroutineRunner
    speedMeter: SpeedMeter


class FeaturePack:
    packId: str = ""
    config: PackConfig | None = None
    proxySchemes: set[str] | None = None

    parsers: list[type[TaskParser]] = []
    taskCards: dict = {}
    draftCards: dict = {}
    parse: Callable[[TaskOptions], Awaitable[Task]] | None = None
    addTask: Callable[[Task], None] | None = None
    submit: Callable[..., str] | None = None

    def __init__(self, services: PackServices):
        self._services = services

    def taskCardClass(self, task: Task):
        return self.taskCards.get(type(task))

    def draftCardClass(self, task: Task):
        return self.draftCards.get(type(task))

    def optionCards(self, task: Task, parent=None) -> list[QWidget]:
        return []

    def editCards(self, task: Task, parent=None) -> list[QWidget]:
        return self.optionCards(task, parent)

    def runtimes(self) -> list[BinaryRuntime]:
        return []

    def fileTypes(self) -> list[FileType]:
        return []

    def pages(self) -> list[type[PackPage]]:
        return []

    async def activate(self):
        pass

    async def deactivate(self):
        pass

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)
