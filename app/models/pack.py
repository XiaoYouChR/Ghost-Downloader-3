from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Signal

from app.config.cfg import cfg, ConfigItem

if TYPE_CHECKING:
    from app.models.task import Task, TaskOptions
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.feature_service import FeatureService
    from app.services.speed_meter import SpeedMeter
    from app.services.task_service import TaskService
    from app.services.runtime_status import RuntimeStatusService
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

    def match(self, options: TaskOptions) -> bool:
        raise NotImplementedError

    def matchPassive(self, options: TaskOptions) -> bool:
        return self.match(options)

    async def parse(self, options: TaskOptions) -> Task:
        raise NotImplementedError


class PackConfig:
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
    taskService: TaskService
    featureService: FeatureService
    categoryService: CategoryService
    runtimeStatusService: RuntimeStatusService


class FeaturePack:
    packId: str = ""
    config: PackConfig | None = None
    proxySchemes: set[str] | None = None

    def __init__(self, services: PackServices):
        self._services = services
        if self.config is not None:
            self.config._services = services
        for runtime in self.runtimes():
            runtime._services = services

    def parsers(self) -> list[TaskParser]:
        return []

    def taskCard(self, task: Task, parent=None):
        from app.view.cards.task_cards import TaskCard
        return TaskCard(task, self._services.taskService, self._services.featureService,
                        self._services.categoryService, parent)

    def draftCard(self, task: Task, parent=None):
        from app.view.cards.draft_cards import DraftCard
        return DraftCard(task, self._services.categoryService, parent)

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
