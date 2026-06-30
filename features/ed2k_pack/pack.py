from __future__ import annotations

from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions
from app.platform.filesystem import toSafeFilename
from .config import ed2kConfig
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

    def parsers(self):
        return [ED2kParser()]

    def stop(self):
        from .session import ed2kSession
        if ed2kSession._client is None:
            return
        from app.services.coroutine_runner import coroutineRunner
        coroutineRunner.submit(ed2kSession.close())
