from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from PySide6.QtCore import QObject

from app.config.paths import executableDir
from app.platform import file_association
from app.services.pack_loader import loadPacks

if TYPE_CHECKING:
    from app.models.pack import FeaturePack, TaskParser, FileType, PackPage
    from app.models.task import Task, TaskOptions
    from PySide6.QtWidgets import QWidget
    from app.view.components.setting_card_group import CollapsibleSettingCardGroup


class FeatureService(QObject):
    def __init__(self, taskService, categoryService, coroutineRunner, runtimeStatusService, parent=None):
        super().__init__(parent)
        self._taskService = taskService
        self._categoryService = categoryService
        self._coroutineRunner = coroutineRunner
        self._runtimeStatusService = runtimeStatusService
        self._packs: list[FeaturePack] = []
        self._parsers: list[TaskParser] = []
        self._packByPackId: dict[str, FeaturePack] = {}
        self._pagePackMap: dict[type, FeaturePack] = {}

    @property
    def packs(self) -> list[FeaturePack]:
        return self._packs

    def load(self, services=None) -> None:
        for pack in loadPacks(executableDir / "features", services):
            self._register(pack)

    def activate(self, coroutineRunner) -> None:
        async def activateAll():
            for pack in self._packs:
                await pack.activate()

        coroutineRunner.submit(activateAll())

    def _register(self, pack: FeaturePack) -> None:
        self._packs.append(pack)
        self._packByPackId[pack.packId] = pack

        pack.parse = self.parse
        pack.addTask = self._taskService.add
        pack.submit = self._coroutineRunner.submit

        for PageClass in pack.pages():
            self._pagePackMap[PageClass] = pack

        for ParserClass in pack.parsers:
            parser = ParserClass()
            parser.pack = pack
            parser.delegate = self.parse
            self._parsers.append(parser)
        self._parsers.sort(key=lambda p: p.priority)

        for runtime in pack.runtimes():
            runtime.parse = self.parse

        if pack.config:
            pack.config.createRuntimeCard = self._createRuntimeCard
            pack.config.submit = self._coroutineRunner.submit
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
        from app.models.task import TaskOptions
        options = TaskOptions(url=url)
        return any(parser.matchPassive(options) for parser in self._parsers)

    # ── Card construction (the seam) ──

    def taskCard(self, task: Task, parent=None):
        from app.view.cards.task_cards import TaskCard
        pack = self._packByPackId.get(task.packId)
        if not pack:
            return None
        CardClass = pack.taskCardClass(task) or TaskCard
        return CardClass(task, self._taskService, self, self._categoryService, parent)

    def draftCard(self, task: Task, parent=None):
        from app.view.cards.draft_cards import DraftCard
        pack = self._packByPackId.get(task.packId)
        if not pack:
            return None
        CardClass = pack.draftCardClass(task) or DraftCard
        return CardClass(task, self._categoryService, self._coroutineRunner, parent)

    def createEditDialog(self, task: Task, parent=None):
        from app.view.dialogs.edit_task import LiveEditDialog
        editCards = self.editCards(task, parent)
        return LiveEditDialog(task, editCards, self._coroutineRunner, self, self._taskService, parent)

    def optionCards(self, task: Task, parent=None) -> list[QWidget]:
        pack = self._packByPackId.get(task.packId)
        return pack.optionCards(task, parent) if pack else []

    def editCards(self, task: Task, parent=None) -> list[QWidget]:
        pack = self._packByPackId.get(task.packId)
        return pack.editCards(task, parent) if pack else []

    # ── RuntimeCard factory ──

    def _createRuntimeCard(self, runtime, parent):
        from app.view.components.setting_cards import RuntimeCard
        return RuntimeCard(self._runtimeStatusService, self._coroutineRunner,
                           self._taskService, runtime, parent)

    # ── Aggregation ──

    def createPage(self, pageClass, parent=None):
        pack = self._pagePackMap.get(pageClass)
        if pack:
            return pageClass(pack, parent)
        return pageClass(parent)

    def pages(self) -> list[type[PackPage]]:
        result = []
        for pack in self._packs:
            result.extend(pack.pages())
        return result

    def settingGroups(self, parent: QWidget) -> list[CollapsibleSettingCardGroup]:
        groups = []
        for pack in self._packs:
            if pack.config:
                groups.extend(pack.config.settingGroups(parent))
        return groups

    def runtimes(self):
        from app.models.pack import BinaryRuntime
        result: list[BinaryRuntime] = []
        for pack in self._packs:
            result.extend(pack.runtimes())
        return result

    def fileTypes(self) -> list[FileType]:
        types = []
        for pack in self._packs:
            types.extend(pack.fileTypes())
        return types

    def isFileAssociationEnabled(self) -> bool:
        return any(
            pack.config.associateFileTypes.value
            for pack in self._packs
            if pack.config and pack.config.associateFileTypes is not None
        )

    def setFileAssociation(self, isEnabled: bool) -> None:
        from app.config.cfg import cfg
        for pack in self._packs:
            if pack.config and pack.config.associateFileTypes is not None:
                cfg.set(pack.config.associateFileTypes, isEnabled)

    def _registerFileAssociations(self) -> None:
        types = []
        for pack in self._packs:
            if pack.config and not pack.config.isFileAssociationEnabled():
                continue
            types.extend(pack.fileTypes())
        file_association.register(types)

    def deactivate(self, coroutineRunner) -> None:
        from PySide6.QtCore import QEventLoop

        async def deactivateAll():
            for pack in self._packs:
                await pack.deactivate()

        loop = QEventLoop()
        coroutineRunner.submit(deactivateAll(), done=lambda _: loop.quit())
        loop.exec()
