from __future__ import annotations

from app.models.pack import FeaturePack, TaskParser, UriScheme
from app.models.task import Task, TaskError, TaskOptions
from app.platform.filesystem import toSafeFilename
from .config import ed2kConfig, ed2kRuntime
from .cards import ED2kTaskCard
from .task import ED2kTask, ED2kTaskStep, parseEd2kLink


class ED2kParser(TaskParser):
    priority = 45

    def match(self, options: TaskOptions) -> bool:
        return options.url.strip().lower().startswith("ed2k://")

    async def parse(self, options: TaskOptions) -> Task:
        link = options.url.strip()
        name, fileSize, fileHash = parseEd2kLink(link)
        from .session import ed2kSession

        if ed2kSession.hasActiveTransfer(fileHash, fileSize):
            raise TaskError("该 eD2k 链接已在下载中")
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
    parsers = [ED2kParser]
    taskCards = {ED2kTask: ED2kTaskCard}

    def uriSchemes(self) -> list[UriScheme]:
        return [UriScheme("ed2k", "eD2k")]

    def runtimes(self):
        return [ed2kRuntime]

    async def activate(self):
        from .session import ed2kSession
        ed2kSession.submit = self.submit

    async def deactivate(self):
        from .session import ed2kSession
        if ed2kSession._client is None:
            return
        await ed2kSession.close()
