from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from PySide6.QtCore import QObject

from app.config.paths import executableDir
from app.models.pack import BinaryRuntime
from app.models.task import TaskOptions
from app.platform import file_association
from app.services.pack_loader import loadPacks

if TYPE_CHECKING:
    from app.models.pack import FeaturePack, FileType, PackPage, PackServices, TaskParser
    from app.models.task import Task
    from PySide6.QtWidgets import QWidget
    from app.view.components.setting_card_group import CollapsibleSettingCardGroup


class FeatureService(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._packs: list[FeaturePack] = []
        self._parsers: list[TaskParser] = []
        self._packByPackId: dict[str, FeaturePack] = {}

    @property
    def packs(self) -> list[FeaturePack]:
        return self._packs

    def load(self, services: PackServices | None = None) -> None:
        for pack in loadPacks(executableDir / "features", services):
            self._register(pack)

    def activate(self, coroutineRunner: object) -> None:
        async def activateAll() -> None:
            for pack in self._packs:
                await pack.activate()

        coroutineRunner.submit(activateAll())

    def _register(self, pack: FeaturePack) -> None:
        self._packs.append(pack)
        self._packByPackId[pack.packId] = pack
        self._parsers.extend(pack.parsers())
        self._parsers.sort(key=lambda p: p.priority)
        if pack.config:
            toggle = pack.config.fileAssociationToggle()
            if toggle:
                toggle.connect(self._registerFileAssociations)

    async def parse(self, options: TaskOptions) -> Task:
        if not options.clientProfile:
            from app.client import matchIdentityPreset
            host = urlparse(options.url).hostname or ""
            preset = matchIdentityPreset(host)
            if preset is not None:
                kwargs = {}
                if preset["clientProfile"]:
                    kwargs["clientProfile"] = preset["clientProfile"]
                if preset["userAgent"]:
                    kwargs["userAgent"] = preset["userAgent"]
                if kwargs:
                    options = replace(options, **kwargs)

        for parser in self._parsers:
            if parser.match(options):
                task = await parser.parse(options)
                return task
        raise ValueError(f"No parser matched: {options.url}")

    def matchPassive(self, url: str) -> bool:
        options = TaskOptions(url=url)
        return any(parser.matchPassive(options) for parser in self._parsers)

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[QWidget]:
        pack = self._packByPackId.get(task.packId)
        return pack.optionCards(task, parent) if pack else []

    def editCards(self, task: Task, parent: QWidget | None = None) -> list[QWidget]:
        pack = self._packByPackId.get(task.packId)
        return pack.editCards(task, parent) if pack else []

    def taskCard(self, task: Task, parent: QWidget | None = None) -> QWidget | None:
        pack = self._packByPackId.get(task.packId)
        return pack.taskCard(task, parent) if pack else None

    def draftCard(self, task: Task, parent: QWidget | None = None) -> QWidget | None:
        pack = self._packByPackId.get(task.packId)
        return pack.draftCard(task, parent) if pack else None

    def pages(self) -> list[type[PackPage]]:
        result: list[type[PackPage]] = []
        for pack in self._packs:
            result.extend(pack.pages())
        return result

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        groups: list[CollapsibleSettingCardGroup] = []
        for pack in self._packs:
            if pack.config:
                groups.extend(pack.config.settingGroups(parent))
        return groups

    def runtimes(self) -> list[BinaryRuntime]:
        result: list[BinaryRuntime] = []
        for pack in self._packs:
            result.extend(pack.runtimes())
        return result

    def fileTypes(self) -> list[FileType]:
        types: list[FileType] = []
        for pack in self._packs:
            types.extend(pack.fileTypes())
        return types

    def isFileAssociationEnabled(self) -> bool:
        return any(
            pack.config.associateFileTypes.value
            for pack in self._packs
            if pack.config and hasattr(pack.config, "associateFileTypes")
        )

    def setFileAssociation(self, isEnabled: bool) -> None:
        from app.config.cfg import cfg
        for pack in self._packs:
            if pack.config and hasattr(pack.config, "associateFileTypes"):
                cfg.set(pack.config.associateFileTypes, isEnabled)

    def _registerFileAssociations(self) -> None:
        types: list[FileType] = []
        for pack in self._packs:
            if pack.config and not pack.config.isFileAssociationEnabled():
                continue
            types.extend(pack.fileTypes())
        file_association.register(types)

    def deactivate(self, coroutineRunner: object) -> None:
        from PySide6.QtCore import QEventLoop

        async def deactivateAll() -> None:
            for pack in self._packs:
                await pack.deactivate()

        loop = QEventLoop()
        coroutineRunner.submit(deactivateAll(), done=lambda _: loop.quit())
        loop.exec()
