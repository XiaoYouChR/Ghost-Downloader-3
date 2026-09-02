from __future__ import annotations

import asyncio
import json
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Signal
from loguru import logger


from app.config.cfg import cfg, ConfigItem
from app.platform.filesystem import findExecutable

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


@dataclass(frozen=True)
class UriScheme:
    scheme: str
    displayName: str


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
    associateUriSchemes: ConfigItem | None = None
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
        if self.associateFileTypes is not None:
            return self.associateFileTypes.value
        return True

    def isUriSchemeAssociationEnabled(self) -> bool:
        if self.associateUriSchemes is not None:
            return self.associateUriSchemes.value
        return True

    def fileAssociationToggle(self) -> Signal | None:
        if self.associateFileTypes is not None:
            return self.associateFileTypes.valueChanged
        return None

    def uriSchemeAssociationToggle(self) -> Signal | None:
        if self.associateUriSchemes is not None:
            return self.associateUriSchemes.valueChanged
        return None

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)


@dataclass(frozen=True)
class VersionInfo:
    version: str
    detail: str = ""


class BinaryRuntime:
    name: str = ""
    binaryName: str = ""
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

    # ── Discovery ──

    def installFolder(self) -> Path:
        raise NotImplementedError

    def path(self) -> str:
        return findExecutable(self.installFolder(), self.binaryName or self.name)

    def isAppManaged(self) -> bool:
        p = self.path()
        return bool(p) and Path(p).is_relative_to(self.installFolder())

    async def probeVersion(self) -> VersionInfo:
        path = self.path()
        if not path:
            return VersionInfo("")
        process = await asyncio.create_subprocess_exec(
            path, "--version",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            return VersionInfo("")
        lines = stdout.decode("utf-8", errors="ignore").splitlines()
        return VersionInfo(lines[0].strip() if lines else "")

    # ── Version ──

    async def fetchLatestVersion(self) -> str:
        return ""

    # ── Lifecycle ──

    def delete(self) -> None:
        folder = self.installFolder()
        if folder.exists():
            shutil.rmtree(folder)

    async def createInstallTask(self, version: str = "") -> Task:
        raise NotImplementedError


class PackPage:
    icon: ...
    title: str = ""


@dataclass(frozen=True)
class PackServices:
    coroutineRunner: CoroutineRunner
    speedMeter: SpeedMeter


@dataclass(frozen=True)
class PackManifest:
    name: str
    className: str
    entryPath: Path
    folder: Path
    dependencies: tuple[str, ...]
    version: str
    gdMinVersion: str

    @classmethod
    def fromDir(cls, packDir: Path) -> PackManifest | None:
        manifestPath = packDir / "manifest.toml"
        if not manifestPath.exists():
            logger.warning("FeaturePack 缺少 manifest.toml: {}", packDir)
            return None

        try:
            raw = tomllib.loads(manifestPath.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("无法读取 manifest {}: {}", manifestPath, repr(e))
            return None

        packSection = raw.get("pack")
        if not isinstance(packSection, dict):
            logger.warning("manifest 缺少 [pack] 节: {}", manifestPath)
            return None

        entry = packSection.get("entry", "pack.py")
        if not isinstance(entry, str) or not entry.strip():
            logger.warning("manifest entry 无效: {}", manifestPath)
            return None

        entryPath = packDir / entry
        if not entryPath.exists() and entry.endswith(".py"):
            entryPath = packDir / (entry[:-3] + ".pyc")
        if not entryPath.exists():
            logger.warning("入口文件不存在: {}", packDir / entry)
            return None

        className = packSection.get("class")
        if not isinstance(className, str) or not className.strip():
            logger.warning("manifest 缺少 class 字段: {}", manifestPath)
            return None

        deps = packSection.get("dependencies", [])
        if not isinstance(deps, list) or any(
            not isinstance(d, str) or not d for d in deps
        ):
            logger.warning("manifest dependencies 无效: {}", manifestPath)
            return None

        version = packSection.get("version", "")
        if not isinstance(version, str):
            version = ""

        gdMinVersion = packSection.get("gdMinVersion", "")
        if not isinstance(gdMinVersion, str):
            gdMinVersion = ""

        return cls(
            name=packDir.name,
            className=className,
            entryPath=entryPath,
            folder=packDir,
            dependencies=tuple(deps),
            version=version,
            gdMinVersion=gdMinVersion,
        )


class FeaturePack:
    packId: str = ""
    manifest: PackManifest | None = None
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

    def uriSchemes(self) -> list[UriScheme]:
        return []

    def pages(self) -> list[type[PackPage]]:
        return []

    async def activate(self):
        pass

    async def deactivate(self):
        pass

    def tr(self, text: str) -> str:
        return QCoreApplication.translate(self.__class__.__name__, text)
