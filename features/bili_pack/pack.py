import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.bases.interfaces import FeaturePack
from app.bases.models import Task
from app.supports.config import cfg
from app.supports.utils import buildClient, getProxies, headerDict, toSafeFilename
from .config import bilibiliConfig
from .task import BilibiliVideoStage, BilibiliAudioStage, BilibiliMergeStage


def _normalizeBilibiliReferer(referer: str) -> str:
    parsedUrl = urlparse(referer)
    if (parsedUrl.hostname or "").lower() != "bilibili.com":
        return referer
    return parsedUrl._replace(netloc="www.bilibili.com").geturl()


def _buildBilibiliHeaders(referer: str) -> dict[str, str]:
    headers = {
        "accept-encoding": "deflate, br, gzip",
        "accept-language": "zh-CN,zh;q=0.9",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 Edg/144.0.0.0",
        "referer": _normalizeBilibiliReferer(referer),
    }

    userCookie = bilibiliConfig.userCookie.value
    if userCookie:
        headers["cookie"] = userCookie

    return headers


def _parseVideoIdAndPages(url: str) -> tuple[str, list[int] | None]:
    parsedUrl = urlparse(url)
    host = (parsedUrl.hostname or "").lower()
    if not (host == "bilibili.com" or host.endswith(".bilibili.com")):
        raise ValueError("Invalid Bilibili video URL")

    matchResult = re.match(r"/video/(BV[a-zA-Z0-9]+|av\d+)", parsedUrl.path)
    if not matchResult:
        raise ValueError("Invalid Bilibili video URL")

    pageParam = parse_qs(parsedUrl.query).get("p", [""])[0].strip()
    pageRange = None if not pageParam else _parsePageParam(pageParam)
    return matchResult.group(1), pageRange


def _parsePageParam(pageParam: str) -> list[int]:
    values: list[int] = []
    if "," in pageParam:
        for part in pageParam.split(","):
            values.extend(_parsePageParam(part.strip()))
        return values

    if "-" in pageParam:
        start, end = map(int, pageParam.split("-", 1))
        if start > end:
            start, end = end, start
        return list(range(start, end + 1))

    return [int(pageParam)]


def _buildViewApiUrl(videoId: str) -> str:
    if videoId.startswith("av"):
        return f"https://api.bilibili.com/x/web-interface/view?avid={videoId[2:]}"
    return f"https://api.bilibili.com/x/web-interface/view?bvid={videoId}"


def _buildPlayApiUrl(videoId: str, cid: int, fnval: int, qn: int) -> str:
    if videoId.startswith("av"):
        return f"https://api.bilibili.com/x/player/wbi/playurl?avid={videoId[2:]}&cid={cid}&qn={qn}&fnval={fnval}&fourk=1"
    return f"https://api.bilibili.com/x/player/wbi/playurl?bvid={videoId}&cid={cid}&qn={qn}&fnval={fnval}&fourk=1"


def _resolveRequestedFnval(videoQuality: int) -> int:
    fnval = 16
    if bilibiliConfig.parseHDR.value:
        fnval |= 64
    if bilibiliConfig.parseDolby.value:
        fnval |= 256
        fnval |= 512
    if videoQuality == 128:
        fnval |= 1024
    if videoQuality == 120:
        fnval |= 128
    return fnval


def _buildPageSuffix(pageNumber: int, pagePart: str, baseTitle: str, totalSelected: int) -> str:
    if totalSelected <= 1:
        return ""
    suffix = f" - P{pageNumber}"
    if pagePart and pagePart != baseTitle:
        suffix += f" {pagePart}"
    return suffix


def _pickVideoStream(pageData: dict, requestedQuality: int) -> dict:
    dash = pageData.get("dash") or {}
    videoOptions = dash.get("video") or []
    if not videoOptions:
        raise ValueError("Bilibili 返回结果中不存在 DASH 视频流")

    acceptQuality = list(pageData.get("accept_quality") or [])
    quality = requestedQuality
    if acceptQuality and quality not in acceptQuality:
        if bilibiliConfig.alternativeQuality.value == "max":
            quality = max(acceptQuality)
        else:
            quality = min(acceptQuality)

    for option in videoOptions:
        if option.get("id") != quality:
            continue
        if _getStreamUrl(option):
            return option

    for option in videoOptions:
        if _getStreamUrl(option):
            return option

    raise ValueError("未找到可用的视频流")


def _pickAudioStream(pageData: dict) -> dict:
    dash = pageData.get("dash") or {}
    audioOptions = dash.get("audio") or []
    if not audioOptions:
        raise ValueError("Bilibili 返回结果中不存在 DASH 音频流")

    for option in audioOptions:
        if _getStreamUrl(option):
            return option

    raise ValueError("未找到可用的音频流")


def _getStreamUrl(stream: dict) -> str:
    url = stream.get("baseUrl") or stream.get("base_url")
    if isinstance(url, str) and url:
        return url

    backup = stream.get("backupUrl") or stream.get("backup_url") or []
    if isinstance(backup, list):
        for item in backup:
            if isinstance(item, str) and item:
                return item

    return ""


async def _getFileSizeWithClient(url: str, headers: dict, client) -> int:
    requestHeaders = headers.copy()
    requestHeaders["range"] = "bytes=0-0"

    response = await client.get(url, headers=requestHeaders)
    try:
        response.raise_for_status()
        head = headerDict(response.headers)

        if response.status.as_int() == 206 and "content-range" in head:
            _left, _char, right = head["content-range"].rpartition("/")
            if right != "*":
                return int(right)

        raise ValueError("音视频流不支持范围请求，当前实现无法下载")
    finally:
        await response.close()


class BilibiliPack(FeaturePack):
    packId = "bili"
    priority = 50
    config = bilibiliConfig

    def matches(self, url: str) -> bool:
        hostname = (urlparse(url).hostname or "").lower()
        return hostname == "bilibili.com" or hostname.endswith(".bilibili.com")

    async def parse(self, payload: dict) -> Task:
        url: str = payload["url"]
        proxies: dict = payload.get("proxies", getProxies())
        blockNum: int = payload.get("preBlockNum", cfg.preBlockNum.value)
        path: Path = payload.get("path", Path(cfg.downloadFolder.value))

        headers = _buildBilibiliHeaders(url)
        async with buildClient(proxies, headers=headers, timeout=60) as client:
            videoId, selectedPages = _parseVideoIdAndPages(url)

            response = await client.get(_buildViewApiUrl(videoId))
            response.raise_for_status()
            videoPayload = await response.json()

            if videoPayload.get("code") not in {None, 0}:
                raise ValueError(videoPayload.get("message") or "获取 Bilibili 视频信息失败")

            viewData = videoPayload.get("data") or {}
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
            totalSize = 0

            baseTitle = toSafeFilename(videoTitle, fallback="bilibili_video")
            if len(selectedPages) == 1:
                page = pages[selectedPages[0] - 1]
                pagePart = str(page.get("part", "")).strip()
                suffix = _buildPageSuffix(selectedPages[0], pagePart, baseTitle, len(selectedPages))
                title = f"{baseTitle}{suffix}.mp4"
            else:
                title = f"{baseTitle}.mp4"

            resolvedPages = []
            for index, pageNumber in enumerate(selectedPages):
                page = pages[pageNumber - 1]
                pagePart = str(page.get("part", "")).strip()
                cid = int(page["cid"])

                playResponse = await client.get(
                    _buildPlayApiUrl(videoId, cid, _resolveRequestedFnval(requestedQuality), requestedQuality),
                )
                playResponse.raise_for_status()
                playPayload = await playResponse.json()

                if playPayload.get("code") not in {None, 0}:
                    raise ValueError(playPayload.get("message") or "获取 Bilibili 音视频流失败")

                pageData = playPayload.get("data") or {}
                videoStream = _pickVideoStream(pageData, requestedQuality)
                audioStream = _pickAudioStream(pageData)
                videoUrl = _getStreamUrl(videoStream)
                audioUrl = _getStreamUrl(audioStream)
                if not videoUrl or not audioUrl:
                    raise ValueError("未能解析出完整的音视频下载链接")

                videoSize = await _getFileSizeWithClient(videoUrl, headers, client)
                audioSize = await _getFileSizeWithClient(audioUrl, headers, client)
                totalSize += videoSize + audioSize

                resolvedPages.append({
                    "pageNumber": pageNumber,
                    "pagePart": pagePart,
                    "videoUrl": videoUrl,
                    "audioUrl": audioUrl,
                    "videoSize": videoSize,
                    "audioSize": audioSize,
                })

            task = Task(
                title=title,
                url=url,
                packId=self.packId,
                fileSize=totalSize,
                path=path,
            )

            for index, pageInfo in enumerate(resolvedPages):
                pageSuffix = _buildPageSuffix(
                    pageInfo["pageNumber"],
                    pageInfo["pagePart"],
                    baseTitle,
                    len(selectedPages),
                )
                stageBase = index * 3

                task.addStage(BilibiliVideoStage(
                    stageIndex=stageBase + 1,
                    url=pageInfo["videoUrl"],
                    fileSize=pageInfo["videoSize"],
                    headers=headers.copy(),
                    proxies=proxies,
                    blockNum=blockNum,
                    pageIndex=index,
                    pageSuffix=pageSuffix,
                ))
                task.addStage(BilibiliAudioStage(
                    stageIndex=stageBase + 2,
                    url=pageInfo["audioUrl"],
                    fileSize=pageInfo["audioSize"],
                    headers=headers.copy(),
                    proxies=proxies,
                    blockNum=blockNum,
                    pageIndex=index,
                    pageSuffix=pageSuffix,
                ))
                task.addStage(BilibiliMergeStage(
                    stageIndex=stageBase + 3,
                    pageIndex=index,
                    pageSuffix=pageSuffix,
                ))

            return task
