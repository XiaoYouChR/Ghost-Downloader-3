from __future__ import annotations

from asyncio import CancelledError
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, fields as dc_fields, replace
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from loguru import logger

from app.i18n import N
from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions
from http_pack.pack import buildEditCards, buildOptionCards
from http_pack.task import HttpTask, HttpTaskStep
from .config import githubConfig, selectedProxySite, GITHUB_PROXY_SITES
from .probe import probeUrls, toProxyHeaders

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from app.view.cards.task_cards import TaskCard
    from app.view.components.option_cards import OptionCard

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


@dataclass(kw_only=True)
class GitHubHttpTaskStep(HttpTaskStep):
    fallbackUrls: list[str] = field(default_factory=list)

    @classmethod
    def build(cls, step: HttpTaskStep, fallbackUrls: list[str]) -> GitHubHttpTaskStep:
        kwargs = {f.name: getattr(step, f.name) for f in dc_fields(HttpTaskStep) if f.init}
        return cls(**kwargs, fallbackUrls=fallbackUrls)

    def rangeStep(self, start: int, end: int, path: Path) -> GitHubHttpTaskStep:
        step = self.build(super().rangeStep(start, end, path), list(self.fallbackUrls))
        step._bindTask(self.task)
        return step

    async def run(
        self,
        reportSpeed: Callable[[int], None],
        waitForSpeedLimit: Callable[[], Awaitable[None]],
    ) -> None:
        while True:
            try:
                await super().run(reportSpeed, waitForSpeedLimit)
                return
            except CancelledError:
                raise
            except Exception:
                if not self.fallbackUrls:
                    raise
                nextUrl, *self.fallbackUrls = self.fallbackUrls
                logger.warning("GitHub 下载 fallback: {} -> {}", self.url, nextUrl)
                self.url = nextUrl
                self.headers = toProxyHeaders(self.headers)
                self.subworkers = []
                self.receivedBytes = 0
                self.progress = 0
                self.speed = 0
                self.error = None
                self.canUseRangeRequests = True
                self.isAccelerated = False
                self._deleteRecord()


class GitHubParser(TaskParser):
    priority = 75

    def match(self, options: TaskOptions) -> bool:
        return githubConfig.enabled.value and isGitHubFileUrl(options.url) and not options.isProbed

    async def parse(self, options: TaskOptions) -> Task:
        originalUrl = options.url
        selected = selectedProxySite()
        urls = [f"{site}/{originalUrl}" for site in GITHUB_PROXY_SITES if site != selected] + [originalUrl]

        file = None
        if selected:
            try:
                winner, file, _ = await probeUrls(options, [f"{selected}/{originalUrl}"])
                fallbackUrls = urls
            except Exception as e:
                logger.warning("所选代理站不可用 {}: {}", selected, e)
        if file is None:
            winner, file, fallbackUrls = await probeUrls(options, urls)

        logger.info("GitHub 选用 {}", winner)
        headers = options.headers if winner == originalUrl else toProxyHeaders(options.headers)
        task = await self.delegate(replace(options, url=winner, headers=headers, file=file))
        if task.packId != "m3u8":
            task.url = originalUrl
        if task.steps and type(task.steps[0]) is HttpTaskStep and fallbackUrls:
            step = GitHubHttpTaskStep.build(task.steps[0], fallbackUrls)
            step._bindTask(task)
            task.steps[0] = step
        if type(task) is HttpTask:
            task.packId = "github"
        return task


class GitHubPack(FeaturePack):
    packId = "github"
    capturedLinks = N("GitHubPack", "GitHub 发布文件与仓库文件")
    config = githubConfig
    parsers = [GitHubParser]

    def taskCardClass(self, task: Task) -> type[TaskCard] | None:
        from http_pack.cards import HttpTaskCard
        return HttpTaskCard

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        return buildOptionCards(task, parent)

    def editCards(self, task: Task, parent: QWidget | None = None) -> list[OptionCard]:
        return buildEditCards(task, parent)
