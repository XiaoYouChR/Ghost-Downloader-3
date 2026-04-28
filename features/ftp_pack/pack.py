# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportImplicitOverride=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput

from .task import FtpTask
from .task import _buildTaskConfigFromPayload
from .task import buildFtpTask
from .task import parse


class FtpPack(FeaturePack):
    priority: int = 95

    def accepts(self, source: str) -> bool:
        return urlparse(source).scheme.lower() in {"ftp", "ftps"}

    async def createTask(self, data: TaskInput) -> Task | None:
        source = data.config.source.strip()
        if not self.accepts(source):
            return None
        return await buildFtpTask(data)

    def owns(self, task: Task) -> bool:
        return isinstance(task, FtpTask) and task.packId == self.manifest.id

    def canHandle(self, url: str) -> bool:
        return self.accepts(url)

    def canHandleTask(self, task: object) -> bool:
        return isinstance(task, FtpTask) and getattr(task, "packId", "") == "ftp_pack"

    async def parse(self, payload: Mapping[str, object]) -> FtpTask:
        return await parse(payload)

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> FtpTask | None:
        config = _buildTaskConfigFromPayload(payload)
        if config is None:
            return None
        return await buildFtpTask(TaskInput(config=config, hints=(dict(payload),)))


__all__ = ["FtpPack", "parse"]
