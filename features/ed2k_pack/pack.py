from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime, PackServices
from app.platform.filesystem import toSafeFilename
from .config import ed2kConfig, ed2kRuntime
from .task import ED2kTask, ED2kTaskStep, parseEd2kLink


class ED2kParser(TaskParser):
    priority = 45

    def match(self, options: TaskOptions) -> bool:
        return options.url.strip().lower().startswith("ed2k://")

    async def parse(self, options: TaskOptions) -> Task:
        link = options.url.strip()
        name, fileSize, _ = parseEd2kLink(link)
        name = toSafeFilename(name, fallback="ed2k_download")

        task = ED2kTask(
            name=name,
            url=link,
            fileSize=fileSize,
            outputFolder=options.outputFolder,
        )
        task.addStep(ED2kTaskStep(stepIndex=1))
        return task


class ED2kPack(FeaturePack):
    packId = "ed2k"
    config = ed2kConfig

    def __init__(self, services: PackServices) -> None:
        super().__init__(services)
        from . import task as _task_mod
        _task_mod._coroutineRunner = services.coroutineRunner

    def runtimes(self) -> list[BinaryRuntime]:
        return [ed2kRuntime]

    def parsers(self) -> list[TaskParser]:
        return [ED2kParser()]

    async def deactivate(self) -> None:
        from .session import ed2kSession
        if ed2kSession._client is None:
            return
        await ed2kSession.close()
