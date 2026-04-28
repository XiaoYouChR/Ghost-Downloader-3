# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlparse

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import SettingSection
from app.feature_pack.api import Task
from app.feature_pack.api import TaskInput

from .config import githubConfig
from .config import getSelectedProxySite
from .task import GitHubDownloadTask
from .task import HttpPack
from .task import buildProxyUrl


_SUPPORTED_GITHUB_HOSTS = {
    "api.github.com",
    "codeload.github.com",
    "gist.github.com",
    "gist.githubusercontent.com",
    "github-releases.githubusercontent.com",
    "media.githubusercontent.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "raw.github.com",
}


def _isSupportedGitHubUrl(source: str) -> bool:
    parsedUrl = urlparse(source)
    scheme = parsedUrl.scheme.lower()
    host = (parsedUrl.hostname or "").lower().removeprefix("www.")
    path = parsedUrl.path.lower()

    if scheme not in {"http", "https"} or not host:
        return False

    if host in _SUPPORTED_GITHUB_HOSTS:
        return True

    if host != "github.com":
        return False

    return (
        "/archive/" in path
        or "/raw/" in path
        or "/releases/download/" in path
        or "/releases/latest/download/" in path
    )


class GitHubPack(FeaturePack):
    priority = 90

    def __init__(self) -> None:
        self._httpPack = HttpPack()

    def accepts(self, source: str) -> bool:
        return (
            githubConfig.enabled.value
            and bool(getSelectedProxySite())
            and _isSupportedGitHubUrl(source)
        )

    async def createTask(self, data: TaskInput) -> Task | None:
        originalSource = str(data.config.source).strip()
        if not self.accepts(originalSource):
            return None

        proxiedInput = TaskInput(
            config=replace(data.config, source=buildProxyUrl(originalSource)),
            size=data.size,
            hints=data.hints,
        )
        httpTask = await self._httpPack.createTask(proxiedInput)
        if httpTask is None:
            return None

        return GitHubDownloadTask.fromHttpTask(
            originalSource=originalSource,
            httpTask=httpTask,
        )

    def owns(self, task: Task) -> bool:
        return isinstance(task, GitHubDownloadTask) and task.packId == self.manifest.id

    def settingSection(self) -> SettingSection:
        return githubConfig.settingSection()

    def createTaskCard(self, task: Task, parent=None):
        return self._httpPack.createTaskCard(task, parent)

    def createResultCard(self, task: Task, parent=None):
        return self._httpPack.createResultCard(task, parent)


__all__ = [
    "GitHubPack",
    "_isSupportedGitHubUrl",
]
