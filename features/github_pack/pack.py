from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from .config import githubConfig, selectedProxySite

if TYPE_CHECKING:
    from features.http_pack.pack import HttpPack
else:
    from http_pack.pack import HttpPack


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


class GitHubPack(FeaturePack):
    packId = "github"
    priority = 90
    config = githubConfig

    def matches(self, url: str) -> bool:
        return self.config.enabled.value and bool(selectedProxySite()) and _isSupportedGitHubUrl(url)

    async def resolve(self, payload: dict) -> dict:
        originalUrl = str(payload["url"]).strip()
        proxiedPayload = payload.copy()
        proxiedPayload["url"] = f"{selectedProxySite().rstrip('/')}/{originalUrl.lstrip('/')}"

        httpPack = HttpPack()
        resolvedPayload = await httpPack.resolve(proxiedPayload)
        resolvedPayload["originalUrl"] = originalUrl
        return resolvedPayload

    def build(self, payload: dict) -> Task:
        originalUrl = payload.pop("originalUrl", payload["url"])
        httpPack = HttpPack()
        task = httpPack.build(payload)
        task.url = originalUrl
        task.packId = self.packId
        return task
