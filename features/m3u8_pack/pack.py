# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportImplicitOverride=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import SettingSection
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput

from .config import m3u8Config
from .task import M3U8_INSTALL_URL
from .task import M3U8InstallTask
from .task import M3U8Task
from .task import _buildTaskConfigFromPayload
from .task import buildM3U8Task
from .task import createInstallTask
from .task import parse


def _isSupportedUrl(url: str) -> bool:
    parsedUrl = urlparse(url)
    if parsedUrl.scheme.lower() not in {"http", "https"}:
        return False

    loweredUrl = url.lower()
    return any(marker in loweredUrl for marker in (".m3u8", ".m3u", ".mpd"))


class M3U8Pack(FeaturePack):
    priority = 80
    taskType = (M3U8Task, M3U8InstallTask)
    config = m3u8Config

    def accepts(self, source: str) -> bool:
        normalizedSource = str(source).strip()
        return normalizedSource == M3U8_INSTALL_URL or _isSupportedUrl(normalizedSource)

    async def createTask(self, data: TaskInput) -> Task | None:
        source = data.config.source.strip()
        if source == M3U8_INSTALL_URL:
            return await createInstallTask(
                installFolder=data.config.folder,
                proxies=data.config.proxies,
                chunks=data.config.chunks,
            )
        if not _isSupportedUrl(source):
            return None
        return await buildM3U8Task(data)

    def owns(self, task: Task) -> bool:
        return isinstance(task, (M3U8Task, M3U8InstallTask)) and task.packId == self.manifest.id

    def settingSection(self) -> SettingSection:
        return m3u8Config.settingSection()

    def canHandle(self, url: str) -> bool:
        return self.accepts(url)

    def canHandleTask(self, task: object) -> bool:
        return isinstance(task, (M3U8Task, M3U8InstallTask)) and getattr(task, "packId", "") == "m3u8_pack"

    async def parse(self, payload: Mapping[str, object]) -> Task:
        if str(payload.get("url") or "").strip() == M3U8_INSTALL_URL:
            rawFolder = payload.get("path")
            rawProxies = payload.get("proxies")
            rawChunks = payload.get("preBlockNum")
            return await createInstallTask(
                installFolder=rawFolder if isinstance(rawFolder, (str, Path)) else None,
                proxies=rawProxies if isinstance(rawProxies, Mapping) else None,
                chunks=rawChunks if isinstance(rawChunks, int) else None,
            )
        return await parse(payload)

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> Task | None:
        config = _buildTaskConfigFromPayload(payload)
        if config is None:
            return None
        if config.source == M3U8_INSTALL_URL:
            return await createInstallTask(
                installFolder=config.folder,
                proxies=config.proxies,
                chunks=config.chunks,
            )
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
