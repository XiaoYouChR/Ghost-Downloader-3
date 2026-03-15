from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.view.components.cards import UniversalResultCard, UniversalTaskCard
from .config import githubConfig

if TYPE_CHECKING:
    from features.http_pack.task import HttpTask
    from features.http_pack.pack import parse as parseHttp
else:
    from http_pack.task import HttpTask
    from http_pack.pack import parse as parseHttp


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


def _isSupportedGitHubUrl(url: str) -> bool:
    parsedUrl = urlparse(url)
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


def _buildProxyUrl(url: str) -> str:
    return f"{githubConfig.proxySite.value.rstrip('/')}/{url.lstrip('/')}"


async def parse(payload: dict) -> HttpTask:
    originalUrl = str(payload["url"]).strip()
    proxiedPayload = payload.copy()
    proxiedPayload["url"] = _buildProxyUrl(originalUrl)

    task = await parseHttp(proxiedPayload)
    task.url = originalUrl
    return task


class GitHubPack(FeaturePack):
    priority = 90
    config = githubConfig

    def canHandle(self, url: str) -> bool:
        return self.config.enabled.value and _isSupportedGitHubUrl(url)

    def canHandleTask(self, task: Task) -> bool:
        return _isSupportedGitHubUrl(task.url)

    async def parse(self, payload: dict) -> Task:
        return await parse(payload)

    def createTaskCard(self, task: Task, parent=None):
        if isinstance(task, HttpTask):
            return UniversalTaskCard(task, parent)
        return None

    def createResultCard(self, task: Task, parent=None):
        if isinstance(task, HttpTask):
            return UniversalResultCard(task, parent)
        return None
