from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput

from .config import ffmpegConfig
from .install_task import FFmpegInstallTask


FFMPEG_MERGE_URL = "gd3+ffmpeg://merge"
FFMPEG_INSTALL_URL = "gd3+ffmpeg://install"


def _mergeTaskType() -> type[object]:
    from .task import FFmpegMergeTask

    return FFmpegMergeTask


async def _createBrowserMergeTask(payload: Mapping[str, object]) -> object:
    from .task import createBrowserMergeTask

    return await createBrowserMergeTask(dict(payload))


def _normalizeStringMapping(value: Mapping[object, object] | None) -> dict[str, str] | None:
    if value is None:
        return None
    normalized: dict[str, str] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, str):
            normalized[key] = item
    return normalized


class FFmpegPack(FeaturePack):
    taskType = (FFmpegInstallTask,)
    config = ffmpegConfig

    def accepts(self, source: str) -> bool:
        normalizedSource = str(source).strip()
        return normalizedSource in {FFMPEG_INSTALL_URL, FFMPEG_MERGE_URL}

    async def createTask(self, data: TaskInput) -> Task | None:
        source = str(data.config.source).strip()
        if source == FFMPEG_INSTALL_URL:
            from .install_task import createWindowsInstallTask

            return await createWindowsInstallTask(
                installFolder=data.config.folder,
                proxies=data.config.proxies,
                chunks=data.config.chunks,
            )
        if source == FFMPEG_MERGE_URL:
            payload = self._taskInputToMergePayload(data)
            return cast(Task | None, await _createBrowserMergeTask(payload))
        return None

    def owns(self, task: Task) -> bool:
        if isinstance(task, FFmpegInstallTask):
            return task.packId == self.manifest.id
        mergeTaskType = _mergeTaskType()
        return isinstance(task, mergeTaskType) and getattr(task, "packId", "") == self.manifest.id

    def canHandle(self, url: str) -> bool:
        return self.accepts(url)

    def canHandleTask(self, task: object) -> bool:
        if isinstance(task, FFmpegInstallTask):
            return getattr(task, "packId", "") == "ffmpeg_pack"
        mergeTaskType = _mergeTaskType()
        return isinstance(task, mergeTaskType) and getattr(task, "packId", "") == "ffmpeg_pack"

    async def parse(self, payload: Mapping[str, object]) -> Task:
        url = str(payload.get("url") or "").strip()
        if url == FFMPEG_INSTALL_URL:
            from .install_task import createWindowsInstallTask

            rawFolder = payload.get("path")
            rawProxies = payload.get("proxies")
            rawChunks = payload.get("preBlockNum")
            return await createWindowsInstallTask(
                installFolder=rawFolder if isinstance(rawFolder, (str, Path)) else None,
                proxies=_normalizeStringMapping(rawProxies) if isinstance(rawProxies, Mapping) else None,
                chunks=rawChunks if isinstance(rawChunks, int) else None,
            )
        return cast(Task, await _createBrowserMergeTask(payload))

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> Task | None:
        return await self.parse(payload)

    def createTaskCard(self, task: Task, parent=None):
        return None

    def createResultCard(self, task: Task, parent=None):
        return None

    def _taskInputToMergePayload(self, data: TaskInput) -> dict[str, object]:
        payload: dict[str, object] = {
            "url": str(data.config.source).strip(),
            "path": data.config.folder,
            "filename": data.config.name,
            "headers": dict(data.config.headers),
            "proxies": None if data.config.proxies is None else dict(data.config.proxies),
            "preBlockNum": data.config.chunks,
            "size": data.size,
        }
        for hint in data.hints:
            if isinstance(hint, Mapping):
                payload.update(dict(hint))
        return payload
