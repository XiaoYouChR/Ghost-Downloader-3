from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from app.config.paths import APP_DATA_DIR
from app.i18n import N
from app.models.pack import BinaryRuntime, FeaturePack, PackServices, TaskParser, UriScheme
from app.models.task import Task, TaskError, TaskOptions
from app.platform.filesystem import toSafeFilename
from .config import ed2kConfig, kelpieRuntime
from .kelpie import PROXY_SCHEMES, Error, Kelpie, Link, Network
from .lists import nodeList, serverList
from .session import buildSettings, ed2kSession, toTaskError
from .task import ED2kTask, ED2kTaskStep

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.view.cards.task_cards import TaskCard
    from app.view.dialogs.task_drawer import DetailCard


def createKelpie(onNetwork: Callable[[Network | None], None]) -> Kelpie:
    return Kelpie(lambda: Path(kelpieRuntime.path()), APP_DATA_DIR / "ed2k_data", buildSettings, onNetwork)


class ED2kParser(TaskParser):
    priority = 45

    def match(self, options: TaskOptions) -> bool:
        return options.url.strip().lower().startswith("ed2k://")

    async def parse(self, options: TaskOptions) -> Task:
        url = options.url.strip()
        try:
            link = Link.parse(url)
        except Error as error:
            raise toTaskError(error) from error

        task = ED2kTask(
            name=toSafeFilename(link.name, fallback="ed2k_download"),
            url=url,
            fileSize=link.size,
            outputFolder=options.outputFolder,
        )
        if ed2kSession.isActive(task):
            raise TaskError("该 eD2k 链接已在下载中")
        task.addStep(ED2kTaskStep(stepIndex=1))
        return task


class ED2kPack(FeaturePack):
    packId = "ed2k"
    capturedLinks = N("ED2kPack", "eD2k 链接")
    config = ed2kConfig
    parsers = [ED2kParser]
    proxySchemes = PROXY_SCHEMES

    def __init__(self, services: PackServices) -> None:
        super().__init__(services)
        ed2kSession.open(services.coroutineRunner, createKelpie)

    def taskCardClass(self, task: Task) -> type[TaskCard] | None:
        from .cards import ED2kTaskCard
        return ED2kTaskCard

    def detailCards(self, task: ED2kTask, parent: QWidget | None = None) -> list[DetailCard]:
        from .detail_cards import ED2kCard, ED2kSourceCard
        return [ED2kCard(task, parent), ED2kSourceCard(task, parent)]

    def uriSchemes(self) -> list[UriScheme]:
        return [UriScheme("ed2k", "eD2k")]

    def runtimes(self) -> list[BinaryRuntime]:
        return [kelpieRuntime]

    async def activate(self) -> None:
        if ed2kConfig.shouldRefreshLists.value:
            for bootstrapList in (serverList, nodeList):
                if bootstrapList.isStale():
                    asyncio.ensure_future(bootstrapList.refresh())

    async def deactivate(self) -> None:
        await ed2kSession.close()
