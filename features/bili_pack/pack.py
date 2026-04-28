# pyright: reportAny=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportAttributeAccessIssue=false, reportImplicitOverride=false, reportCallIssue=false, reportUnusedCallResult=false, reportArgumentType=false, reportUnannotatedClassAttribute=false

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs
from urllib.parse import urlparse

import niquests

from app.feature_pack.api import FeaturePack
from app.feature_pack.api import Task
from app.feature_pack.api import TaskConfig
from app.feature_pack.api import TaskInput
from app.supports.config import cfg
from app.supports.utils import getProxies
from app.supports.utils import sanitizeFilename

from .config import bilibiliConfig
from .task import BilibiliEpisodeFile
from .task import BilibiliTask
from .task import createBilibiliTask


def _copyHeaders(headers: Mapping[str, object] | None) -> dict[str, str]:
    if not isinstance(headers, Mapping):
        return {}
    return {str(key): str(value) for key, value in headers.items()}


def _copyProxies(proxies: Mapping[str, object] | None) -> dict[str, str] | None:
    if proxies is None:
        return None
    return {str(key): str(value) for key, value in proxies.items()}


def _normalizeChunks(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return max(1, int(cfg.preBlockNum.value))
    return max(1, int(value))


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
        headers["cookie"] = str(userCookie)

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


def _pickVideoStream(pageData: Mapping[str, object], requestedQuality: int) -> Mapping[str, object]:
    dash = pageData.get("dash") if isinstance(pageData.get("dash"), Mapping) else {}
    rawVideoOptions = dash.get("video") if isinstance(dash, Mapping) else None
    videoOptions = [
        cast(Mapping[str, object], option)
        for option in rawVideoOptions
        if isinstance(option, Mapping)
    ] if isinstance(rawVideoOptions, list) else []
    if not videoOptions:
        raise ValueError("Bilibili 返回结果中不存在 DASH 视频流")

    rawAcceptQuality = pageData.get("accept_quality")
    acceptQuality = [
        quality
        for quality in rawAcceptQuality
        if isinstance(quality, int) and not isinstance(quality, bool)
    ] if isinstance(rawAcceptQuality, list) else []
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


def _pickAudioStream(pageData: Mapping[str, object]) -> Mapping[str, object]:
    dash = pageData.get("dash") if isinstance(pageData.get("dash"), Mapping) else {}
    rawAudioOptions = dash.get("audio") if isinstance(dash, Mapping) else None
    audioOptions = [
        cast(Mapping[str, object], option)
        for option in rawAudioOptions
        if isinstance(option, Mapping)
    ] if isinstance(rawAudioOptions, list) else []
    if not audioOptions:
        raise ValueError("Bilibili 返回结果中不存在 DASH 音频流")

    for option in audioOptions:
        if _getStreamUrl(option):
            return option

    raise ValueError("未找到可用的音频流")


def _getStreamUrl(stream: Mapping[str, object]) -> str:
    url = stream.get("baseUrl") or stream.get("base_url")
    if isinstance(url, str) and url:
        return url

    backup = stream.get("backupUrl") or stream.get("backup_url") or []
    if isinstance(backup, list):
        for item in backup:
            if isinstance(item, str) and item:
                return item

    return ""


async def _getFileSizeWithClient(
    url: str,
    headers: Mapping[str, str],
    proxies: Mapping[str, str] | None,
    client: niquests.AsyncSession,
) -> int:
    requestHeaders = dict(headers)
    requestHeaders["range"] = "bytes=0-0"

    response = await client.get(
        url,
        headers=requestHeaders,
        proxies=proxies,
        verify=cfg.SSLVerify.value,
        allow_redirects=True,
        stream=True,
    )
    try:
        response.raise_for_status()
        responseHeaders = {str(key).lower(): str(value) for key, value in response.headers.items()}

        if response.status_code == 206 and "content-range" in responseHeaders:
            _left, _char, right = responseHeaders["content-range"].rpartition("/")
            if right != "*":
                return int(right)

        raise ValueError("音视频流不支持范围请求，当前实现无法下载")
    finally:
        await response.close()


def _buildTaskConfigFromPayload(payload: Mapping[str, object]) -> TaskConfig | None:
    rawSource = payload.get("url")
    if not isinstance(rawSource, str):
        return None

    source = rawSource.strip()
    if not source:
        return None

    rawFolder = payload.get("path")
    rawName = payload.get("filename")
    rawHeaders = payload.get("headers")
    rawProxies = payload.get("proxies")
    rawChunks = payload.get("preBlockNum")
    return TaskConfig(
        source=source,
        folder=Path(rawFolder) if isinstance(rawFolder, (str, Path)) else Path(cfg.downloadFolder.value),
        name=rawName if isinstance(rawName, str) else "",
        headers=_copyHeaders(rawHeaders if isinstance(rawHeaders, Mapping) else None),
        proxies=(
            _copyProxies(rawProxies)
            if isinstance(rawProxies, Mapping)
            else getProxies()
        ),
        chunks=_normalizeChunks(rawChunks),
    )


def _selectedPageNumbers(
    requestedPages: list[int] | None,
    *,
    pageCount: int,
) -> set[int]:
    if requestedPages is None:
        return set(range(1, pageCount + 1))

    selectedPages = {
        pageNumber
        for pageNumber in requestedPages
        if 1 <= pageNumber <= pageCount
    }
    if not selectedPages:
        raise ValueError("未找到有效的分P编号")
    return selectedPages


def _pageOutputName(videoTitle: str, pageNumber: int, part: str, totalPages: int) -> str:
    baseTitle = sanitizeFilename(videoTitle, fallback="bilibili_video")
    if totalPages <= 1:
        return f"{baseTitle}.mp4"

    sanitizedPart = sanitizeFilename(part, fallback="").strip() if part.strip() else ""
    if sanitizedPart and sanitizedPart != baseTitle:
        return f"{baseTitle} - P{pageNumber} {sanitizedPart}.mp4"
    return f"{baseTitle} - P{pageNumber}.mp4"


async def buildBilibiliTask(data: TaskInput) -> BilibiliTask:
    source = str(data.config.source).strip()
    videoId, requestedPages = _parseVideoIdAndPages(source)
    proxies = _copyProxies(data.config.proxies) if data.config.proxies is not None else getProxies()
    headers = _buildBilibiliHeaders(source)
    headers.update(_copyHeaders(data.config.headers))

    client = niquests.AsyncSession(headers=headers, timeout=60, happy_eyeballs=True)
    client.trust_env = False

    try:
        response = await client.get(
            _buildViewApiUrl(videoId),
            proxies=proxies,
            allow_redirects=True,
        )
        try:
            response.raise_for_status()
            videoPayload = response.json()
        finally:
            response.close()

        if not isinstance(videoPayload, Mapping):
            raise ValueError("获取 Bilibili 视频信息失败")
        if videoPayload.get("code") not in {None, 0}:
            raise ValueError(str(videoPayload.get("message") or "获取 Bilibili 视频信息失败"))

        viewData = videoPayload.get("data") if isinstance(videoPayload.get("data"), Mapping) else {}
        rawPages = viewData.get("pages") if isinstance(viewData, Mapping) else None
        pages = [
            cast(Mapping[str, object], page)
            for page in rawPages
            if isinstance(page, Mapping)
        ] if isinstance(rawPages, list) else []
        if not pages:
            raise ValueError("未获取到视频分P信息")

        selectedPages = _selectedPageNumbers(requestedPages, pageCount=len(pages))
        videoTitle = sanitizeFilename(
            str(viewData.get("title", "")).strip() if isinstance(viewData, Mapping) else "",
            fallback="bilibili_video",
        )
        requestedQuality = int(bilibiliConfig.defaultQuality.value)
        episodes: list[BilibiliEpisodeFile] = []

        for pageIndex, page in enumerate(pages, start=1):
            part = str(page.get("part", "")).strip()
            rawCid = page.get("cid")
            if isinstance(rawCid, bool) or not isinstance(rawCid, int):
                raise ValueError(f"P{pageIndex} 缺少有效 cid")

            playResponse = await client.get(
                _buildPlayApiUrl(
                    videoId,
                    rawCid,
                    _resolveRequestedFnval(requestedQuality),
                    requestedQuality,
                ),
                proxies=proxies,
                allow_redirects=True,
            )
            try:
                playResponse.raise_for_status()
                playPayload = playResponse.json()
            finally:
                playResponse.close()

            if not isinstance(playPayload, Mapping):
                raise ValueError("获取 Bilibili 音视频流失败")
            if playPayload.get("code") not in {None, 0}:
                raise ValueError(str(playPayload.get("message") or "获取 Bilibili 音视频流失败"))

            pageData = playPayload.get("data") if isinstance(playPayload.get("data"), Mapping) else {}
            videoStream = _pickVideoStream(cast(Mapping[str, object], pageData), requestedQuality)
            audioStream = _pickAudioStream(cast(Mapping[str, object], pageData))
            videoUrl = _getStreamUrl(videoStream)
            audioUrl = _getStreamUrl(audioStream)
            if not videoUrl or not audioUrl:
                raise ValueError("未能解析出完整的音视频下载链接")

            videoSize = await _getFileSizeWithClient(videoUrl, headers, proxies, client)
            audioSize = await _getFileSizeWithClient(audioUrl, headers, proxies, client)
            episodeName = _pageOutputName(videoTitle, pageIndex, part, len(pages))
            episodes.append(
                BilibiliEpisodeFile(
                    id=f"page-{pageIndex}",
                    pageNumber=pageIndex,
                    path=episodeName,
                    size=videoSize + audioSize,
                    selected=pageIndex in selectedPages,
                    note=f"P{pageIndex}" if not part else f"P{pageIndex} · {part}",
                    part=part,
                    cid=rawCid,
                    videoUrl=videoUrl,
                    audioUrl=audioUrl,
                    videoSize=videoSize,
                    audioSize=audioSize,
                )
            )

        baseConfig = replace(
            data.config,
            source=source,
            folder=Path(data.config.folder),
            name=data.config.name or videoTitle,
            headers=headers,
            proxies=proxies,
            chunks=_normalizeChunks(data.config.chunks),
        )
        return createBilibiliTask(
            config=baseConfig,
            episodes=episodes,
            fallbackName=videoTitle,
        )
    finally:
        await client.close()


async def parse(payload: Mapping[str, object]) -> BilibiliTask:
    config = _buildTaskConfigFromPayload(payload)
    if config is None:
        raise ValueError("Bilibili 任务缺少有效的 url")
    return await buildBilibiliTask(TaskInput(config=config, hints=(dict(payload),)))


class BilibiliPack(FeaturePack):
    priority = 50
    taskType = BilibiliTask
    config = bilibiliConfig

    def accepts(self, source: str) -> bool:
        try:
            _parseVideoIdAndPages(source)
        except Exception:
            return False
        return True

    async def createTask(self, data: TaskInput) -> Task | None:
        if not self.accepts(data.config.source):
            return None
        return await buildBilibiliTask(data)

    def owns(self, task: Task) -> bool:
        return isinstance(task, BilibiliTask) and task.packId == self.manifest.id

    def canHandle(self, url: str) -> bool:
        return self.accepts(url)

    def canHandleTask(self, task: object) -> bool:
        return isinstance(task, BilibiliTask) and getattr(task, "packId", "") == "bili_pack"

    async def parse(self, payload: Mapping[str, object]) -> BilibiliTask:
        return await parse(payload)

    async def createTaskFromPayload(self, payload: Mapping[str, object]) -> BilibiliTask | None:
        config = _buildTaskConfigFromPayload(payload)
        if config is None:
            return None
        return await buildBilibiliTask(TaskInput(config=config, hints=(dict(payload),)))

    def createTaskCard(self, task: Task, parent: object | None = None):
        _ = task
        _ = parent
        return None

    def createResultCard(self, task: Task, parent: object | None = None):
        _ = task
        _ = parent
        return None


__all__ = [
    "BilibiliPack",
    "_buildTaskConfigFromPayload",
    "buildBilibiliTask",
    "parse",
]
