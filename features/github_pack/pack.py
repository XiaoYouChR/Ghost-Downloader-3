from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions
from .config import githubConfig, selectedProxySite

if TYPE_CHECKING:
    from app.models.pack import PackServices
    from PySide6.QtWidgets import QWidget

GITHUB_HOSTS = {
    "api.github.com",
    "codeload.github.com",
    "gist.github.com",
    "gist.githubusercontent.com",
    "github-releases.githubusercontent.com",
    "media.githubusercontent.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "raw.github.com",
    "release-assets.githubusercontent.com",
}


def isGitHubFileUrl(url: str) -> bool:
    parsedUrl = urlparse(url)
    scheme = parsedUrl.scheme.lower()
    host = (parsedUrl.hostname or "").lower().removeprefix("www.")
    path = parsedUrl.path.lower()

    if scheme not in {"http", "https"} or not host:
        return False

    if host in GITHUB_HOSTS:
        return True

    if host != "github.com":
        return False

    return (
        "/archive/" in path
        or "/raw/" in path
        or "/releases/download/" in path
        or "/releases/latest/download/" in path
    )


class GitHubParser(TaskParser):
    priority = 90

    def __init__(self, pack):
        self._pack = pack

    def match(self, options: TaskOptions) -> bool:
        return (
            githubConfig.enabled.value
            and bool(selectedProxySite())
            and isGitHubFileUrl(options.url)
        )

    async def parse(self, options: TaskOptions) -> Task:
        from dataclasses import replace

        proxiedUrl = f"{selectedProxySite().rstrip('/')}/{options.url.lstrip('/')}"
        task = await self._pack._services.featureService.parse(replace(options, url=proxiedUrl))
        task.url = options.url
        task.packId = "github"
        return task


class GitHubPack(FeaturePack):
    packId = "github"
    config = githubConfig

    def parsers(self) -> list[TaskParser]:
        return [GitHubParser(self)]

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[QWidget]:
        from http_pack.pack import HttpPack
        return HttpPack.optionCards(self, task, parent)

    def editCards(self, task: Task, parent: QWidget | None = None) -> list[QWidget]:
        from http_pack.pack import HttpPack
        return HttpPack.editCards(self, task, parent)

    def taskCard(self, task: Task, parent: QWidget | None = None) -> QWidget:
        from http_pack.cards import HttpTaskCard
        return HttpTaskCard(task, self._services.taskService, self._services.featureService, self._services.categoryService, parent)
