from __future__ import annotations

import asyncio
from dataclasses import replace
from threading import Event
from typing import TYPE_CHECKING

from loguru import logger

from app.config.cfg import cfg
from app.config.paths import FEATURES_DIR
from app.models.task import TaskError, TaskOptions, toHost, toScheme
from app.platform import file_association
from app.loader import loadPacks

if TYPE_CHECKING:
    from app.models.pack import (
        BinaryRuntime, FeaturePack, FileType, PackPage, PackServices, TaskParser, UriScheme,
    )
    from app.models.task import Task
    from app.services.category_service import CategoryService
    from app.services.coroutine_runner import CoroutineRunner
    from app.services.runtime_status import RuntimeStatusService
    from app.services.task_service import TaskService
    from PySide6.QtWidgets import QWidget
    from app.view.cards.draft_cards import DraftCard
    from app.view.cards.task_cards import TaskCard
    from app.view.components.option_cards import OptionCard
    from app.view.components.setting_card_group import CollapsibleSettingCardGroup
    from app.view.components.setting_cards import RuntimeCard
    from app.view.dialogs.edit_task import LiveEditDialog
    from app.view.dialogs.task_drawer import DetailCard

PARSE_LIMIT_PER_HOST = 5


class FeatureService:
    def __init__(
        self,
        taskService: TaskService,
        categoryService: CategoryService,
        coroutineRunner: CoroutineRunner,
        runtimeStatusService: RuntimeStatusService,
    ):
        self._taskService = taskService
        self._categoryService = categoryService
        self._coroutineRunner = coroutineRunner
        self._runtimeStatusService = runtimeStatusService
        self._packs: list[FeaturePack] = []
        self._parsers: list[TaskParser] = []
        self._packByPackId: dict[str, FeaturePack] = {}
        self._pagePackMap: dict[type[PackPage], FeaturePack] = {}
        self._parseSlotsByHost: dict[str, asyncio.Semaphore] = {}

    @property
    def packs(self) -> list[FeaturePack]:
        return self._packs

    def load(self, services: PackServices | None = None) -> None:
        for pack in loadPacks(FEATURES_DIR, services):
            self.register(pack)

    def activate(self) -> None:
        async def activateAll() -> None:
            for pack in self._packs:
                await pack.activate()

        self._coroutineRunner.submit(activateAll())

    def packById(self, packId: str) -> FeaturePack | None:
        return self._packByPackId.get(packId)

    def register(self, pack: FeaturePack) -> None:
        self._packs.append(pack)
        self._packByPackId[pack.packId] = pack

        pack.parse = self._parse
        pack.addTask = self._taskService.add
        pack.submit = self._coroutineRunner.submit

        for PageClass in pack.pages():
            self._pagePackMap[PageClass] = pack

        for ParserClass in pack.parsers:
            self._parsers.append(ParserClass(pack))
        self._parsers.sort(key=lambda p: p.priority)

        if pack.config:
            pack.config.createRuntimeCard = self._createRuntimeCard
            pack.config.submit = self._coroutineRunner.submit
            fileToggle = pack.config.fileAssociationToggle()
            if fileToggle:
                fileToggle.connect(self._registerAssociations)
            schemeToggle = pack.config.uriSchemeAssociationToggle()
            if schemeToggle:
                schemeToggle.connect(self._registerAssociations)

    async def parse(self, options: TaskOptions) -> Task:
        host = toHost(options.url)
        if not host:
            return await self._parse(options)

        async with self._parseSlotsByHost.setdefault(host, asyncio.Semaphore(PARSE_LIMIT_PER_HOST)):
            return await self._parse(options)

    async def _parse(self, options: TaskOptions) -> Task:
        options = toPresetOptions(options)
        matched = [parser for parser in self._parsers if matchParser(parser, options)]
        if not matched:
            raise TaskError("不支持该链接")
        if not options.isProbed:
            return await matched[0].parse(options)
        for parser in matched[:-1]:
            try:
                return await parser.parse(options)
            except Exception as e:
                logger.opt(exception=e).warning("无法按内容解析，按普通文件下载 {}", options.url)
        return await matched[-1].parse(options)

    def match(self, url: str) -> bool:
        options = TaskOptions(url=url)
        return any(matchParser(parser, options) for parser in self._parsers)

    def matchPassive(self, url: str) -> bool:
        if not toScheme(url):
            return False
        options = TaskOptions(url=url)
        parser = next((parser for parser in self._parsers if matchParser(parser, options)), None)
        return (parser is not None
                and parser.pack.packId not in cfg.clipboardIgnoredPacks.value
                and parser.matchPassive(options))

    # ── Card construction (the seam) ──

    def taskCard(self, task: Task, parent: QWidget | None = None) -> TaskCard | None:
        from app.view.cards.task_cards import TaskCard
        pack = self._packByPackId.get(task.packId)
        if not pack:
            return None
        CardClass = pack.taskCardClass(task) or TaskCard
        return CardClass(task, self._taskService, self, self._categoryService, parent)

    def draftCard(self, task: Task, parent: QWidget | None = None) -> DraftCard | None:
        from app.view.cards.draft_cards import DraftCard
        pack = self._packByPackId.get(task.packId)
        if not pack:
            return None
        CardClass = pack.draftCardClass(task) or DraftCard
        return CardClass(task, self._categoryService, self._coroutineRunner, self._taskService.probeConflict, parent)

    def createEditDialog(self, task: Task, parent: QWidget | None = None) -> LiveEditDialog:
        from app.view.dialogs.edit_task import LiveEditDialog
        editCards = self.editCards(task, parent)
        return LiveEditDialog(task, editCards, self._coroutineRunner, self, self._taskService, parent)

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        pack = self._packByPackId.get(task.packId)
        return pack.optionCards(task, parent) if pack else []

    def editCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        pack = self._packByPackId.get(task.packId)
        return pack.editCards(task, parent) if pack else []

    def detailCards(self, task: Task, parent: QWidget | None = None) -> list[DetailCard]:
        pack = self._packByPackId.get(task.packId)
        return pack.detailCards(task, parent) if pack else []

    # ── RuntimeCard factory ──

    def _createRuntimeCard(self, runtime: BinaryRuntime, parent: QWidget | None) -> RuntimeCard:
        from app.view.components.setting_cards import RuntimeCard
        return RuntimeCard(self._runtimeStatusService, runtime, parent)

    # ── Aggregation ──

    def createPage(self, pageClass: type[PackPage], parent: QWidget | None = None) -> PackPage:
        pack = self._pagePackMap.get(pageClass)
        if pack:
            return pageClass(pack, parent)
        return pageClass(parent)

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
        types = []
        for pack in self._packs:
            types.extend(pack.fileTypes())
        return types

    def uriSchemes(self) -> list[UriScheme]:
        schemes = []
        for pack in self._packs:
            schemes.extend(pack.uriSchemes())
        return schemes

    def isFileAssociationEnabled(self) -> bool:
        return any(
            pack.config.associateFileTypes.value
            for pack in self._packs
            if pack.config and pack.config.associateFileTypes is not None
        )

    def isUriSchemeAssociationEnabled(self) -> bool:
        return any(
            pack.config.associateUriSchemes.value
            for pack in self._packs
            if pack.config and pack.config.associateUriSchemes is not None
        )

    def setFileAssociation(self, isEnabled: bool) -> None:
        for pack in self._packs:
            if pack.config and pack.config.associateFileTypes is not None:
                cfg.set(pack.config.associateFileTypes, isEnabled)

    def _registerAssociations(self) -> None:
        types = []
        enabledSchemes = []
        disabledSchemes = []
        for pack in self._packs:
            if not pack.config or pack.config.isFileAssociationEnabled():
                types.extend(pack.fileTypes())
            if not pack.config or pack.config.isUriSchemeAssociationEnabled():
                enabledSchemes.extend(pack.uriSchemes())
            elif pack.uriSchemes():
                disabledSchemes.extend(pack.uriSchemes())
        file_association.register(types)
        for s in disabledSchemes:
            file_association.unregisterUrlScheme(s.scheme)
        for s in enabledSchemes:
            file_association.registerUrlScheme(s.scheme)

    def deactivate(self) -> None:
        event = Event()

        async def deactivateAll():
            try:
                for pack in self._packs:
                    await pack.deactivate()
            finally:
                event.set()

        self._coroutineRunner.submit(deactivateAll())
        event.wait()


def matchParser(parser: TaskParser, options: TaskOptions) -> bool:
    try:
        return parser.match(options)
    except ValueError:
        return False


def toPresetOptions(options: TaskOptions) -> TaskOptions:
    if options.clientProfile:
        return options
    from app.client import matchIdentityPreset
    preset = matchIdentityPreset(toHost(options.url))
    if preset is None:
        return options
    kwargs = {}
    if preset["clientProfile"]:
        kwargs["clientProfile"] = preset["clientProfile"]
    if preset["userAgent"]:
        kwargs["userAgent"] = preset["userAgent"]
    return replace(options, **kwargs) if kwargs else options
