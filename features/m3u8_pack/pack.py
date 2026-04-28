# pyright: reportAny=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportImplicitOverride=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

from urllib.parse import urlparse

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import SettingSection
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput

from .config import m3u8Config
from .task import M3U8_INSTALL_URL
from .task import M3U8InstallTask
from .task import M3U8Task
from .task import buildM3U8Task
from .task import createInstallTask


def _isSupportedUrl(url: str) -> bool:
    parsedUrl = urlparse(url)
    if parsedUrl.scheme.lower() not in {"http", "https"}:
        return False

    loweredUrl = url.lower()
    return any(marker in loweredUrl for marker in (".m3u8", ".m3u", ".mpd"))


class M3U8Pack(FeaturePack):
    priority = 80

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

    def createTaskCard(self, task: Task, parent=None):
        _ = task
        _ = parent
        return None

    def createResultCard(self, task: Task, parent=None):
        _ = task
        _ = parent
        return None


__all__ = ["M3U8Pack"]
