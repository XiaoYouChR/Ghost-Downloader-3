from __future__ import annotations

from urllib.parse import urlparse

from app.client import buildClient
from app.models.pack import FeaturePack, TaskParser
from app.models.task import TaskOptions
from app.platform.filesystem import toSafeFilename
from .account import BilibiliAccount
from .cards import BilibiliDraftCard, BilibiliTaskCard
from .config import bilibiliConfig
from .parse import buildPages, parseBiliUrl
from .stream import buildSize, fetchPlayurl, toStreamUrl
from .task import BilibiliTask


class BilibiliParser(TaskParser):
    priority = 50

    def match(self, options: TaskOptions) -> bool:
        hostname = (urlparse(options.url).hostname or "").lower()
        return hostname == "bilibili.com" or hostname.endswith(".bilibili.com")

    def matchPassive(self, options: TaskOptions) -> bool:
        if not self.match(options):
            return False
        try:
            biliUrl = parseBiliUrl(options.url)
        except ValueError:
            return False
        return bool(biliUrl.videoId or biliUrl.seasonId)

    async def parse(self, options: TaskOptions) -> Task:
        url = options.url
        subworkerCount = options.subworkerCount
        outputFolder = options.outputFolder

        await self.pack.account.fetchWbiKeys()

        parsed = urlparse(url)
        referer = parsed._replace(netloc="www.bilibili.com").geturl() if (
            (parsed.hostname or "").lower() != "bilibili.com"
        ) else url

        apiHeaders = {}
        cookie = self.pack.account.cookie
        if cookie:
            apiHeaders["cookie"] = cookie

        downloadHeaders = {
            **dict(options.headers),
            "referer": referer,
        }
        if cookie:
            downloadHeaders["cookie"] = cookie

        client = buildClient(emulation=None, headers=apiHeaders)

        try:
            biliUrl = parseBiliUrl(url)
            if not biliUrl.videoId and not biliUrl.seasonId:
                raise ValueError("不是有效的 Bilibili 视频链接")

            viewData = await fetchView(client, biliUrl)
            parsedPages, title, coverUrl = buildPages(viewData, biliUrl)
            if not parsedPages:
                raise ValueError("未获取到视频分P信息")

            requestedQuality = bilibiliConfig.defaultQuality.value
            baseName = toSafeFilename(title, fallback="bilibili_video")
            for page in parsedPages:
                page.headers = dict(downloadHeaders)
                page.subworkerCount = subworkerCount
            template = next((p for p in parsedPages if p.selected), parsedPages[0])
            acceptQuality, acceptDescription, requestedQuality = await fetchPlayurl(
                template,
                qn=requestedQuality,
                signParams=self.pack.account.signParams,
                headers=template.headers,
            )
            for page in parsedPages:
                page.headers["cookie"] = template.headers.get("cookie", "")

            videoStream = next(
                (s for s in template._videoStreams if toStreamUrl(s) == template.videoUrl), None
            )
            audioStream = next(
                (s for s in template._audioStreams if toStreamUrl(s) == template.audioUrl), None
            )
            for page in parsedPages:
                if page is template:
                    continue
                page.videoSize = buildSize(videoStream, page._duration)
                page.audioSize = buildSize(audioStream, page._duration)

            coverSize = 0
            if coverUrl:
                try:
                    headResponse = await client.head(coverUrl)
                    cl = headResponse.headers.get("content-length")
                    if cl:
                        coverSize = int(cl.decode() if isinstance(cl, bytes) else cl)
                except Exception:
                    pass

            task = BilibiliTask(
                name=f"{baseName}.mp4",
                url=url,
                fileSize=0,
                outputFolder=outputFolder,
                coverUrl=coverUrl,
                coverSize=coverSize,
                files=parsedPages,
                requestedQn=requestedQuality,
                _baseName=baseName,
                _acceptQualities=acceptQuality,
                _qualityLabels=acceptDescription,
            )
            task.update()

            return task
        finally:
            client.close()


async def fetchView(client, biliUrl) -> dict:
    videoId = biliUrl.videoId
    if not videoId and biliUrl.seasonId:
        listUrl = (
            "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
            f"?mid={biliUrl.mid}&season_id={biliUrl.seasonId}&page_num=1&page_size=1"
        )
        response = await client.get(listUrl, headers={"referer": "https://www.bilibili.com"})
        response.raise_for_status()
        payload = await response.json()
        archives = ((payload.get("data") or {}).get("archives") or [])
        if not archives:
            raise ValueError("未获取到合集信息")
        videoId = str(archives[0].get("bvid") or "")
        if not videoId:
            raise ValueError("未获取到合集信息")

    viewApiUrl = (
        f"https://api.bilibili.com/x/web-interface/view?avid={videoId[2:]}"
        if videoId.startswith("av")
        else f"https://api.bilibili.com/x/web-interface/view?bvid={videoId}"
    )
    response = await client.get(viewApiUrl)
    response.raise_for_status()
    viewPayload = await response.json()
    if viewPayload.get("code") not in {None, 0}:
        raise ValueError(viewPayload.get("message") or "获取 Bilibili 视频信息失败")
    return viewPayload.get("data") or {}


class BilibiliPack(FeaturePack):
    packId = "bili"
    config = bilibiliConfig
    parsers = [BilibiliParser]
    taskCards = {BilibiliTask: BilibiliTaskCard}
    draftCards = {BilibiliTask: BilibiliDraftCard}

    def __init__(self, services):
        super().__init__(services)
        self.account = BilibiliAccount(services.coroutineRunner)
        self.config._account = self.account

    def optionCards(self, task, parent=None):
        from app.view.components.option_cards import OutputFolderCard
        return [OutputFolderCard(parent, initial=task.outputFolder)]

    async def activate(self):
        self.account.fetchAccountInfo()
