from __future__ import annotations

from typing import TYPE_CHECKING

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self._packs: list[FeaturePack] = []
        self._parsers: list[TaskParser] = []
        self._packByPackId: dict[str, FeaturePack] = {}

    @property
    def packs(self) -> list[FeaturePack]:
        return self._packs

    def load(self) -> None:
        for pack in loadPacks(executableDir / "features"):
            self._register(pack)

    def start(self) -> None:
        for pack in self._packs:
            pack.start()

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
        for parser in self._parsers:
            if parser.match(options):
                task = await parser.parse(options)
                if not task.category:
                    from app.services.category_service import categoryService
                    task.category = categoryService.categoryOf(task)
                return task
        raise ValueError(f"No parser matched: {options.url}")

    def matchFetched(self, options: TaskOptions) -> bool:
        return any(parser.match(options) for parser in self._parsers)

    def matchPassive(self, url: str) -> bool:
        from app.models.task import TaskOptions
        options = TaskOptions(url=url)
        return any(parser.matchPassive(options) for parser in self._parsers)

    def optionCards(self, task: Task, parent=None) -> list[QWidget]:
        pack = self._packByPackId.get(task.packId)
        return pack.optionCards(task, parent) if pack else []

    def editCards(self, task: Task, parent=None) -> list[QWidget]:
        pack = self._packByPackId.get(task.packId)
        return pack.editCards(task, parent) if pack else []

    def taskCard(self, task: Task, parent=None):
        pack = self._packByPackId.get(task.packId)
        return pack.taskCard(task, parent) if pack else None

    def draftCard(self, task: Task, parent=None):
        pack = self._packByPackId.get(task.packId)
        return pack.draftCard(task, parent) if pack else None

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

    def fileTypes(self) -> list[FileType]:
        types = []
        for pack in self._packs:
            types.extend(pack.fileTypes())
        return types

    def _registerFileAssociations(self) -> None:
        types = []
        for pack in self._packs:
            if pack.config and not pack.config.isFileAssociationEnabled():
                continue
            types.extend(pack.fileTypes())
        file_association.register(types)

    def stop(self) -> None:
        for pack in self._packs:
            pack.stop()


featureService = FeatureService()
