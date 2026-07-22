from __future__ import annotations

import asyncio
from urllib.parse import urlparse, parse_qs, quote

from typing import TYPE_CHECKING

from app.models.pack import FeaturePack, TaskParser
from app.models.task import Task, TaskOptions, SpecialFileSize

if TYPE_CHECKING:
    from app.models.pack import BinaryRuntime, PackServices
    from PySide6.QtWidgets import QWidget
from app.platform.filesystem import toSafeFilename
from loguru import logger

from .config import ytDlpConfig, youTubeRuntime
from .task import YouTubeTask, buildStepGroup, probeFormats, probePlaylist

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
            from .config import saveCookies
            saveCookies(cookieHeader)

        title = await self._fetchTitle(url)
        name = toSafeFilename(title) if title else "YouTube 视频"

        task = YouTubeTask(
            name=f"{name}.mp4",
            url=url,
            fileSize=SpecialFileSize.UNKNOWN,
            outputFolder=options.outputFolder,
            isPlaylist=isPlaylist,
        )
        for step in buildStepGroup(0):
            task.addStep(step)
        return task

    async def fetchFormats(self, url: str) -> dict:
        from .config import youTubeRuntime
        runtimePath = youTubeRuntime.path()
        if not runtimePath:
            logger.warning("fetchFormats skipped: runtime not found (installFolder={})", youTubeRuntime.ytDlpFolder())
            return {}
        try:
            return await asyncio.to_thread(probeFormats, url)
        except Exception as e:
            logger.opt(exception=e).warning("fetchFormats failed for {}", url)
            return {}

    async def fetchPlaylist(self, url: str) -> list[dict]:
        from .config import youTubeRuntime
        if not youTubeRuntime.path():
            return []
        try:
            return await asyncio.to_thread(probePlaylist, url)
        except Exception as e:
            logger.opt(exception=e).warning("fetchPlaylist failed for {}", url)
            return []

    async def _fetchTitle(self, url: str) -> str:
        from app.client import buildClient
        oembedUrl = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
        try:
            client = buildClient(timeout=5)
            response = await client.get(oembedUrl)
            data = await response.json()
            return str(data.get("title") or "")
        except Exception:
            return ""


class YouTubePack(FeaturePack):
    packId = "ytdlp"

    def __init__(self, services: PackServices) -> None:
        self.config = ytDlpConfig
        super().__init__(services)

    def runtimes(self) -> list[BinaryRuntime]:
        return [youTubeRuntime]

    def parsers(self) -> list[TaskParser]:
        return [YouTubeParser()]

    def taskCard(self, task: Task, parent: QWidget | None = None) -> QWidget:
        from .cards import YtDlpTaskCard
        return YtDlpTaskCard(task, self._services.taskService, self._services.featureService, self._services.categoryService, parent)

    def draftCard(self, task: Task, parent: QWidget | None = None) -> QWidget:
        from .cards import YtDlpDraftCard
        return YtDlpDraftCard(task, self._services.categoryService, parent)

    def optionCards(self, task: Task, parent: QWidget | None = None) -> list[QWidget]:
        from app.view.components.option_cards import OutputFolderCard
        return [
            OutputFolderCard(parent, initial=task.outputFolder),
        ]
