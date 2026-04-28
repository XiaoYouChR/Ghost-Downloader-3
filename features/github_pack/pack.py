# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnannotatedClassAttribute=false, reportImplicitOverride=false

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast
from urllib.parse import urlparse

from app.feature_pack.api import FeaturePack
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


def _payloadSize(payload: Mapping[str, object]) -> int:
    size = payload.get("size")
    if isinstance(size, bool) or not isinstance(size, int):
        return 0
    return size


def _taskInputFromPayload(payload: Mapping[str, object]) -> TaskInput:
    source = str(payload.get("url") or "").strip()
    if not source:
        raise ValueError("GitHub 任务缺少有效的 url")

    from .task import buildHttpTaskConfigFromPayload

    config = buildHttpTaskConfigFromPayload(payload)
    if config is None:
        raise ValueError("GitHub 任务缺少有效的 url")

    return TaskInput(
        config=config,
        size=_payloadSize(payload),
        hints=(dict(payload),),
    )


async def parse(payload: Mapping[str, object]) -> GitHubDownloadTask:
    pack = GitHubPack()
    task = await pack.createTask(_taskInputFromPayload(payload))
    if task is None:
        raise ValueError("GitHub Pack 未创建任务")
    return cast(GitHubDownloadTask, task)


class GitHubPack(FeaturePack):
    priority = 90
    config = githubConfig

    def __init__(self) -> None:
        self._httpPack = HttpPack()

    def accepts(self, source: str) -> bool:
        return (
            self.config.enabled.value
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

    def canHandle(self, url: str) -> bool:
        return self.accepts(url)

    def canHandleTask(self, task: object) -> bool:
        return isinstance(task, GitHubDownloadTask) and getattr(task, "packId", "") == "github_pack"

    async def parse(self, payload: Mapping[str, object]) -> GitHubDownloadTask:
        return await parse(payload)

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> GitHubDownloadTask | None:
        return await parse(payload)

    def createTaskCard(self, task: Task, parent=None):
        return self._httpPack.createTaskCard(task, parent)

    def createResultCard(self, task: Task, parent=None):
        return self._httpPack.createResultCard(task, parent)


__all__ = [
    "GitHubPack",
    "_isSupportedGitHubUrl",
    "parse",
]
