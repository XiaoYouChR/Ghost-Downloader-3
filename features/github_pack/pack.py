from urllib.parse import urlparse

from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions
from .config import githubConfig, selectedProxySite

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

    def match(self, options: TaskOptions) -> bool:
        return (
            githubConfig.enabled.value
            and bool(selectedProxySite())
            and isGitHubFileUrl(options.url)
        )

    async def parse(self, options: TaskOptions) -> Task:
        from dataclasses import replace
        from app.services.feature_service import featureService

        proxiedUrl = f"{selectedProxySite().rstrip('/')}/{options.url.lstrip('/')}"
        task = await featureService.parse(replace(options, url=proxiedUrl))
        task.url = options.url
        task.packId = "github"
        return task


class GitHubPack(FeaturePack):
    packId = "github"
    config = githubConfig

    def parsers(self):
        return [GitHubParser()]

    def taskCard(self, task, parent=None):
        from http_pack.cards import HttpTaskCard
        return HttpTaskCard(task, parent)
