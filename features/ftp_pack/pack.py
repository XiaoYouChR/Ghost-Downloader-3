# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportImplicitOverride=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from urllib.parse import urlparse

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput

from .task import FtpTask
from .task import buildFtpTask


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


__all__ = ["FtpPack"]
