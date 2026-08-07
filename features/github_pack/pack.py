from asyncio import CancelledError
from dataclasses import dataclass, field, fields as dc_fields, replace
from urllib.parse import urlparse

from loguru import logger

from app.client import buildClient
from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskError, TaskOptions, ResourceTaskOptions
from http_pack.cards import HttpTaskCard
from http_pack.task import HttpTask, HttpTaskStep
from .config import githubConfig, selectedProxySite, GITHUB_PROXY_SITES

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
    def build(cls, step: HttpTaskStep, fallbackUrls: list[str]):
        kwargs = {f.name: getattr(step, f.name) for f in dc_fields(HttpTaskStep) if f.init}
        return cls(**kwargs, fallbackUrls=fallbackUrls)

    async def run(self, reportSpeed, waitForSpeedLimit):
        while True:
            try:
                await super().run(reportSpeed, waitForSpeedLimit)
                return
            except CancelledError:
                raise
            except TaskError:
                raise
            except Exception:
                if not self.fallbackUrls:
                    raise
                nextUrl = self.fallbackUrls.pop(0)
                logger.warning("GitHub 下载 fallback: {} → {}", self.url, nextUrl)
                self.url = nextUrl
                self.subworkers = []
                self.receivedBytes = 0
                self.progress = 0
                self.speed = 0
                self.error = None
                self._deleteRecord()


class GitHubParser(TaskParser):
    priority = 90
    _isFallingBack = False

    def match(self, options: TaskOptions) -> bool:
        return (
            not self._isFallingBack
            and githubConfig.enabled.value
            and bool(selectedProxySite())
            and isGitHubFileUrl(options.url)
        )

    async def parse(self, options: TaskOptions) -> Task:
        fallbackUrls = self._buildFallbackUrls(options.url)
        isResourceWithName = isinstance(options, ResourceTaskOptions) and options.name

        lastError = None
        for i, url in enumerate(fallbackUrls):
            isDirectUrl = (url == options.url)
            try:
                if isResourceWithName and not isDirectUrl:
                    await self._probeProxy(url, options.headers)

                self._isFallingBack = isDirectUrl
                task = await self.delegate(replace(options, url=url))

                remaining = fallbackUrls[i + 1:]
                if remaining:
                    step = task.steps[0]
                    if isinstance(step, HttpTaskStep):
                        githubStep = GitHubHttpTaskStep.build(step, remaining)
                        task.steps[0] = githubStep
                        githubStep._bindTask(task)

                task.url = options.url
                task.packId = "github"
                return task
            except Exception as e:
                lastError = e
                logger.warning("GitHub proxy 不可用 {}: {}", url, e)
            finally:
                self._isFallingBack = False

        raise lastError

    def _buildFallbackUrls(self, originalUrl: str) -> list[str]:
        selected = selectedProxySite()
        urls = [f"{selected.rstrip('/')}/{originalUrl}"]
        for site in GITHUB_PROXY_SITES:
            if site != selected:
                urls.append(f"{site.rstrip('/')}/{originalUrl}")
        urls.append(originalUrl)
        return urls

    async def _probeProxy(self, url: str, headers: dict) -> None:
        client = buildClient(timeout=10)
        try:
            response = await client.get(
                url, headers={**headers, "range": "bytes=0-0", "accept-encoding": "identity"},
            )
            response.close()
        finally:
            client.close()


class GitHubPack(FeaturePack):
    packId = "github"
    config = githubConfig
    parsers = [GitHubParser]
    taskCards = {HttpTask: HttpTaskCard}

    def optionCards(self, task, parent=None):
        from http_pack.pack import HttpPack
        return HttpPack.optionCards(self, task, parent)

    def editCards(self, task, parent=None):
        from http_pack.pack import HttpPack
        return HttpPack.editCards(self, task, parent)
