from __future__ import annotations

from urllib.parse import urlparse, parse_qs, quote

from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions, SpecialFileSize
from app.platform.filesystem import toSafeFilename
from loguru import logger

from .cards import YtDlpDraftCard, YtDlpTaskCard
from .config import ytDlpConfig, youTubeRuntime
from .task import YouTubeTask, buildStepGroup

YOUTUBE_HOSTS = ("youtube.com", "youtu.be")


class YouTubeParser(TaskParser):
    priority = 70

    def match(self, options: TaskOptions) -> bool:
        host = (urlparse(options.url).hostname or "").lower()
        return any(host == h or host.endswith(f".{h}") for h in YOUTUBE_HOSTS)

    async def parse(self, options: TaskOptions) -> Task:
        url = options.url.strip()
        isPlaylist = bool(parse_qs(urlparse(url).query).get("list"))

        cookieHeader = options.headers.get("cookie") or options.headers.get("Cookie")
        if cookieHeader:
            from .config import saveCookiesIfBetter
            saveCookiesIfBetter(cookieHeader)

        title = await self._fetchTitle(url)
        name = toSafeFilename(title) if title else "YouTube 视频"

        task = YouTubeTask(
            name=f"{name}.mp4",
            url=url,
            fileSize=SpecialFileSize.UNKNOWN,
            outputFolder=options.outputFolder,
            isPlaylist=isPlaylist,
            subworkerCount=options.subworkerCount,
        )
        for step in buildStepGroup(0):
            task.addStep(step)
        return task

    async def _fetchTitle(self, url: str) -> str:
        from app.client import buildClient
        oembedUrl = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
        client = buildClient(timeout=5)
        try:
            response = await client.get(oembedUrl)
            data = await response.json()
            return str(data.get("title") or "")
        except Exception:
            logger.opt(exception=True).debug("_fetchTitle failed for {}", url)
            return ""
        finally:
            client.close()


class YouTubePack(FeaturePack):
    packId = "ytdlp"
    parsers = [YouTubeParser]
    taskCards = {YouTubeTask: YtDlpTaskCard}
    draftCards = {YouTubeTask: YtDlpDraftCard}

    def __init__(self, services):
        self.config = ytDlpConfig
        super().__init__(services)

    def runtimes(self):
        return [youTubeRuntime]

    def optionCards(self, task, parent=None):
        from app.view.components.option_cards import OutputFolderCard
        return [
            OutputFolderCard(parent, initial=task.outputFolder),
        ]
