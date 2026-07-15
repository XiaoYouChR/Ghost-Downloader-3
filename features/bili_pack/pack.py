from __future__ import annotations

import re
import urllib.parse
from urllib.parse import parse_qs, urlparse

from loguru import logger

from app.client import buildClient, toEmulation
from app.config.cfg import cfg
from app.models.pack import FeaturePack, TaskParser
from app.models.task import TaskOptions
from app.platform.filesystem import toSafeFilename
from .account import bilibiliAccount
from .config import bilibiliConfig
from .task import BiliPage, BilibiliTask


class BilibiliParser(TaskParser):
    priority = 50

    def match(self, options: TaskOptions) -> bool:
        hostname = (urlparse(options.url).hostname or "").lower()
        return hostname == "bilibili.com" or hostname.endswith(".bilibili.com")

    def matchPassive(self, options: TaskOptions) -> bool:
        parsed = urlparse(options.url)
        hostname = (parsed.hostname or "").lower()
        if hostname != "bilibili.com" and not hostname.endswith(".bilibili.com"):
            return False
        return bool(re.match(r"/video/(BV[a-zA-Z0-9]+|av\d+)", parsed.path))

    async def parse(self, options: TaskOptions) -> Task:
        url = options.url
        subworkerCount = options.subworkerCount
        outputFolder = options.outputFolder

        await bilibiliAccount.fetchWbiKeys()

        parsed = urlparse(url)
        referer = parsed._replace(netloc="www.bilibili.com").geturl() if (
            (parsed.hostname or "").lower() != "bilibili.com"
        ) else url

        apiHeaders = {}
        cookie = bilibiliAccount.cookie
        if cookie:
            apiHeaders["cookie"] = cookie

        downloadHeaders = {
            **dict(options.headers),
            "referer": referer,
        }
        if cookie:
            downloadHeaders["cookie"] = cookie

        emulation = toEmulation(
            options.clientProfile or cfg.clientProfile.value,
            options.sourceUserAgent,
        )
        client = buildClient(emulation=None, headers=apiHeaders)

        try:
            videoIdMatch = re.match(r"/video/(BV[a-zA-Z0-9]+|av\d+)", parsed.path)
            if not videoIdMatch:
                raise ValueError("不是有效的 Bilibili 视频链接")
            videoId = videoIdMatch.group(1)

            pageParam = parse_qs(parsed.query).get("p", [""])[0].strip()
            selectedPages: list[int] | None = None
            if pageParam:
                selectedPages = []
                for part in pageParam.split(","):
                    part = part.strip()
                    if "-" in part:
                        start, end = map(int, part.split("-", 1))
                        if start > end:
                            start, end = end, start
                        selectedPages.extend(range(start, end + 1))
                    else:
                        selectedPages.append(int(part))

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

            viewData = viewPayload.get("data") or {}
            pages = list(viewData.get("pages") or [])
            if not pages:
                raise ValueError("未获取到视频分P信息")

            if selectedPages is None:
                selectedPages = list(range(1, len(pages) + 1))
            selectedPages = [p for p in dict.fromkeys(selectedPages) if 1 <= p <= len(pages)]
            if not selectedPages:
                raise ValueError("未找到有效的分P编号")

            videoTitle = str(viewData.get("title", "")).strip() or "bilibili_video"
            requestedQuality = bilibiliConfig.defaultQuality.value
            baseName = toSafeFilename(videoTitle, fallback="bilibili_video")
            taskName = f"{baseName}.mp4"

            fnval = 16
            if bilibiliConfig.shouldIncludeHdr.value:
                fnval |= 64
            if bilibiliConfig.shouldIncludeDolby.value:
                fnval |= 256 | 512
            if requestedQuality == 128:
                fnval |= 1024
            if requestedQuality == 120:
                fnval |= 128

            totalSize = 0
            parsedPages = []

            for pageNumber in range(1, len(pages) + 1):
                page = pages[pageNumber - 1]
                pagePart = str(page.get("part", "")).strip()
                cid = int(page["cid"])

                playParams = {"cid": cid, "qn": requestedQuality, "fnval": fnval, "fourk": 1}
                if videoId.startswith("av"):
                    playParams["avid"] = videoId[2:]
                else:
                    playParams["bvid"] = videoId
                playParams = bilibiliAccount.signParams(playParams)
                playApiUrl = f"https://api.bilibili.com/x/player/wbi/playurl?{urllib.parse.urlencode(playParams)}"

                response = await client.get(playApiUrl)
                response.raise_for_status()
                playPayload = await response.json()
                if playPayload.get("code") not in {None, 0}:
                    raise ValueError(playPayload.get("message") or "获取 Bilibili 音视频流失败")

                pageData = playPayload.get("data") or {}
                videoUrl = self._selectStream(
                    pageData.get("dash", {}).get("video") or [],
                    requestedQuality,
                    list(pageData.get("accept_quality") or []),
                )
                audioUrl = self._selectStream(
                    pageData.get("dash", {}).get("audio") or [],
                )
                if not videoUrl or not audioUrl:
                    raise ValueError("未能解析出完整的音视频下载链接")

                videoSize = await self._fetchSize(client, videoUrl, downloadHeaders)
                audioSize = await self._fetchSize(client, audioUrl, downloadHeaders)
                totalSize += videoSize + audioSize

                subtitles = await self._fetchSubtitles(client, videoId, cid)

                parsedPages.append(BiliPage(
                    index=pageNumber - 1,
                    relativePath=pagePart or f"P{pageNumber}",
                    pagePart=pagePart,
                    videoUrl=videoUrl,
                    audioUrl=audioUrl,
                    videoSize=videoSize,
                    audioSize=audioSize,
                    subtitles=subtitles,
                ))

            coverUrl = str(viewData.get("pic") or "").strip()
            if coverUrl.startswith("http://"):
                coverUrl = "https://" + coverUrl[7:]

            coverSize = 0
            if coverUrl:
                try:
                    headResponse = await client.head(coverUrl)
                    cl = headResponse.headers.get("content-length")
                    if cl:
                        coverSize = int(cl.decode() if isinstance(cl, bytes) else cl)
                except Exception:
                    pass

            for page in parsedPages:
                page.headers = dict(downloadHeaders)
                page.subworkerCount = subworkerCount
                page.selected = page.pageNumber in selectedPages

            task = BilibiliTask(
                name=taskName,
                url=url,
                fileSize=totalSize,
                outputFolder=outputFolder,
                coverUrl=coverUrl,
                coverSize=coverSize,
                files=parsedPages,
                _baseName=baseName,
            )
            task._rebuildSteps()

            return task
        finally:
            client.close()

    async def _fetchSubtitles(self, client, videoId: str, cid: int) -> list[dict]:
        try:
            params: dict = {"cid": cid}
            if videoId.startswith("av"):
                params["aid"] = videoId[2:]
            else:
                params["bvid"] = videoId

            url = f"https://api.bilibili.com/x/player/v2?{urllib.parse.urlencode(params)}"
            response = await client.get(url)
            response.raise_for_status()
            payload = await response.json()

            subtitleData = (payload.get("data") or {}).get("subtitle") or {}
            rawList = subtitleData.get("subtitles") or []
            return [
                {
                    "lan": s["lan"],
                    "lan_doc": s.get("lan_doc", s["lan"]),
                    "subtitle_url": s.get("subtitle_url", ""),
                    "isAi": s.get("type", 0) == 1,
                }
                for s in rawList if s.get("lan") and s.get("subtitle_url")
            ]
        except Exception:
            logger.opt(exception=True).debug("Failed to fetch subtitles for cid={}", cid)
            return []

    def _selectStream(
        self,
        streams: list[dict],
        quality: int | None = None,
        acceptQuality: list[int] | None = None,
    ) -> str:
        if not streams:
            raise ValueError("Bilibili 返回结果中不存在可用的媒体流")

        def streamUrl(s: dict) -> str:
            url = s.get("baseUrl") or s.get("base_url")
            if isinstance(url, str) and url:
                return url
            backup = s.get("backupUrl") or s.get("backup_url") or []
            if isinstance(backup, list):
                for item in backup:
                    if isinstance(item, str) and item:
                        return item
            return ""

        if quality is not None and acceptQuality:
            targetQuality = quality
            if targetQuality not in acceptQuality:
                targetQuality = max(acceptQuality) if bilibiliConfig.alternativeQuality.value == "max" else min(acceptQuality)
            for s in streams:
                if s.get("id") == targetQuality and streamUrl(s):
                    return streamUrl(s)

        for s in streams:
            url = streamUrl(s)
            if url:
                return url

        raise ValueError("未找到可用的媒体流")

    async def _fetchSize(self, client, url: str, headers: dict) -> int:
        response = await client.get(url, headers={**headers, "range": "bytes=0-0"})
        try:
            response.raise_for_status()
            head = {k.decode().lower(): v.decode() for k, v in response.headers}
            if response.status.as_int() == 206 and "content-range" in head:
                _, _, total = head["content-range"].rpartition("/")
                if total != "*":
                    return int(total)
            raise ValueError("音视频流不支持范围请求，当前实现无法下载")
        finally:
            response.close()


class BilibiliPack(FeaturePack):
    packId = "bili"
    config = bilibiliConfig

    def parsers(self):
        return [BilibiliParser()]

    def draftCard(self, task, parent=None):
        from .cards import BilibiliDraftCard
        return BilibiliDraftCard(task, parent)

    def taskCard(self, task, parent=None):
        from .cards import BilibiliTaskCard
        return BilibiliTaskCard(task, parent)

    def optionCards(self, task, parent=None):
        from app.view.components.option_cards import OutputFolderCard
        return [OutputFolderCard(parent, initial=task.outputFolder)]

    def start(self):
        bilibiliAccount.fetchAccountInfo()
