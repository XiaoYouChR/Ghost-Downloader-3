# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportImplicitOverride=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput

from .config import m3u8Config
from .task import M3U8Task
from .task import _buildTaskConfigFromPayload
from .task import buildM3U8Task
from .task import parse


def _isSupportedUrl(url: str) -> bool:
    parsedUrl = urlparse(url)
    if parsedUrl.scheme.lower() not in {"http", "https"}:
        return False

    loweredUrl = url.lower()
    return any(marker in loweredUrl for marker in (".m3u8", ".m3u", ".mpd"))


class M3U8Pack(FeaturePack):
    priority = 80
    taskType = (M3U8Task,)
    config = m3u8Config

    def accepts(self, source: str) -> bool:
        return _isSupportedUrl(source)

    async def createTask(self, data: TaskInput) -> Task | None:
        source = data.config.source.strip()
        if not self.accepts(source):
            return None
        return await buildM3U8Task(data)

    def owns(self, task: Task) -> bool:
        return isinstance(task, M3U8Task) and task.packId == self.manifest.id

    def canHandle(self, url: str) -> bool:
        return self.accepts(url)

    def canHandleTask(self, task: object) -> bool:
        return isinstance(task, M3U8Task) and getattr(task, "packId", "") == "m3u8_pack"

    async def parse(self, payload: Mapping[str, object]) -> M3U8Task:
        return await parse(payload)

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> M3U8Task | None:
        config = _buildTaskConfigFromPayload(payload)
        if config is None:
            return None
        return await buildM3U8Task(TaskInput(config=config, hints=(dict(payload),)))

    def createTaskCard(self, task: Task, parent=None):
        _ = task
        _ = parent
        return None

    def createResultCard(self, task: Task, parent=None):
        _ = task
        _ = parent
        return None


__all__ = ["M3U8Pack", "parse"]
