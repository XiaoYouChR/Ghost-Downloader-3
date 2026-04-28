from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import SettingSection
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput

from .config import ffmpegConfig
from .install_task import FFmpegInstallTask


FFMPEG_MERGE_URL = "gd3+ffmpeg://merge"
FFMPEG_INSTALL_URL = "gd3+ffmpeg://install"


def _mergeTaskType() -> type[object]:
    from .task import FFmpegMergeTask

    return FFmpegMergeTask


async def _createBrowserMergeTask(inputData: Mapping[str, object]) -> object:
    from .task import createBrowserMergeTask

    return await createBrowserMergeTask(dict(inputData))


class FFmpegPack(FeaturePack):
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
            mergeData = self._taskInputToMergeData(data)
            return cast(Task | None, await _createBrowserMergeTask(mergeData))
        return None

    def owns(self, task: Task) -> bool:
        if isinstance(task, FFmpegInstallTask):
            return task.packId == self.manifest.id
        mergeTaskType = _mergeTaskType()
        return isinstance(task, mergeTaskType) and getattr(task, "packId", "") == self.manifest.id

    def settingSection(self) -> SettingSection:
        return ffmpegConfig.settingSection()

    def createTaskCard(self, task: Task, parent=None):
        return None

    def createResultCard(self, task: Task, parent=None):
        return None

    def _taskInputToMergeData(self, data: TaskInput) -> dict[str, object]:
        mergeData: dict[str, object] = {
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
                mergeData.update(dict(hint))
        return mergeData
