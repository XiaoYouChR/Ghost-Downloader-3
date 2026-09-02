from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from loguru import logger

from app.client import buildClient
from .config import bilibiliConfig

if TYPE_CHECKING:
    from .task import BiliPage


class NoopRunner:
    def submit(self, *a, **k):
        return ""

    def cancel(self, *a, **k):
        pass

    def post(self, *a, **k):
        pass


def toStreamUrl(s: dict) -> str:
    url = s.get("baseUrl") or s.get("base_url") or ""
    if url:
        return url
    for item in (s.get("backupUrl") or s.get("backup_url") or []):
        if item:
            return item
    return ""


def buildSize(stream: dict | None, duration: int) -> int:
    if not stream or duration <= 0:
        return 0
    return int(stream.get("bandwidth") or 0) * duration // 8


async def probeSize(url: str, headers: dict | None = None) -> int:
    if not url:
        return 0
    client = buildClient()
    try:
        response = await client.get(
            url,
            headers={**(headers or {}), "range": "bytes=0-0", "accept-encoding": "identity"},
        )
        try:
            raw = response.headers.get("content-range")
            if raw is None:
                return 0
            cr = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
            if "/" not in cr:
                return 0
            total = cr.rsplit("/", 1)[-1].strip()
            if not total or total == "*":
                return 0
            size = int(total)
            return size if size > 0 else 0
        finally:
            response.close()
    except Exception:
        logger.opt(exception=True).debug("probeSize failed for {}", url)
        return 0
    finally:
        client.close()


def buildFnval(qn: int) -> int:
    fnval = 16
    if bilibiliConfig.shouldIncludeHdr.value:
        fnval |= 64
    if bilibiliConfig.shouldIncludeDolby.value:
        fnval |= 256 | 512
    if qn == 128:
        fnval |= 1024
    if qn == 120:
        fnval |= 128
    return fnval


def parseDash(page: BiliPage, dash: dict, *, qn: int, acceptQuality: list[int], audioQn: int = 0) -> None:
    videoStreams = list(dash.get("video") or [])
    audioStreams = list(dash.get("audio") or [])
    if not videoStreams:
        raise ValueError("Bilibili 返回结果中不存在可用的媒体流")
    video = matchStream(videoStreams, qn, acceptQuality)
    audio = None
    if audioStreams:
        audioIds = [s.get("id") for s in audioStreams if s.get("id") is not None]
        audio = matchStream(audioStreams, audioQn or None, audioIds if audioQn else None)
    page.videoUrl = toStreamUrl(video)
    page.audioUrl = toStreamUrl(audio) if audio else ""
    page._videoStreams = videoStreams
    page._audioStreams = audioStreams
    page.videoSize = buildSize(video, page._duration)
    page.audioSize = buildSize(audio, page._duration) if audio else 0


def matchStream(
    streams: list[dict],
    quality: int | None = None,
    acceptQuality: list[int] | None = None,
) -> dict:
    if not streams:
        raise ValueError("Bilibili 返回结果中不存在可用的媒体流")

    if quality is not None and acceptQuality:
        targetQuality = quality
        if targetQuality not in acceptQuality:
            targetQuality = (
                max(acceptQuality) if bilibiliConfig.alternativeQuality.value == "max"
                else min(acceptQuality)
            )
        for s in streams:
            if s.get("id") == targetQuality and toStreamUrl(s):
                return s

    for s in streams:
        if toStreamUrl(s):
            return s
    raise ValueError("未找到可用的媒体流")


async def fetchPlayurl(
    page: BiliPage,
    *,
    qn: int,
    headers: dict,
    signParams=None,
    audioQn: int = 0,
) -> tuple[list[int], list[str], int]:
    if signParams is None:
        from .account import BilibiliAccount
        account = BilibiliAccount(NoopRunner())
        await account.fetchWbiKeys()
        signParams = account.signParams

    cookie = headers.get("cookie") or headers.get("Cookie") or ""
    client = buildClient(headers={"cookie": cookie} if cookie else None)
    try:
        if cookie and "buvid3=" not in cookie.lower():
            buvid = await fetchBuvid(client)
            if buvid:
                cookie = f"{cookie}; buvid3={buvid}"
                page.headers["cookie"] = cookie
                client.close()
                client = buildClient(headers={"cookie": cookie})

        playParams = {"cid": page.cid, "qn": qn, "fnval": buildFnval(qn), "fourk": 1}
        if page.bvid:
            playParams["bvid"] = page.bvid
        playParams = signParams(playParams)
        playApiUrl = f"https://api.bilibili.com/x/player/wbi/playurl?{urllib.parse.urlencode(playParams)}"

        response = await client.get(playApiUrl)
        status = response.status.as_int()
        if status == 412:
            raise ValueError("Bilibili 拦截了取流请求（412 风控）。请稍后再试，登录 Cookie 建议带上 buvid3")
        response.raise_for_status()
        playPayload = await response.json()
        if playPayload.get("code") not in {None, 0}:
            if qn != 80:
                return await fetchPlayurl(page, qn=80, headers=headers, signParams=signParams, audioQn=audioQn)
            raise ValueError(playPayload.get("message") or "获取 Bilibili 音视频流失败")

        pageData = playPayload.get("data") or {}
        dash = pageData.get("dash") or {}
        videoStreams = list(dash.get("video") or [])
        if not videoStreams and qn != 80:
            return await fetchPlayurl(page, qn=80, headers=headers, signParams=signParams, audioQn=audioQn)
        acceptQuality = list(pageData.get("accept_quality") or [])
        parseDash(page, dash, qn=qn, acceptQuality=acceptQuality, audioQn=audioQn)
        if not page.subtitles:
            page.subtitles = await fetchSubtitles(client, page)
        return acceptQuality, list(pageData.get("accept_description") or []), qn
    finally:
        client.close()


async def fetchBuvid(client) -> str:
    try:
        response = await client.get("https://api.bilibili.com/x/frontend/finger/spi")
        payload = await response.json()
        return str(((payload.get("data") or {}).get("b_3") or "")).strip()
    except Exception:
        logger.opt(exception=True).debug("Failed to fetch buvid3")
        return ""


async def fetchSubtitles(client, page: BiliPage) -> list[dict]:
    try:
        params: dict = {"cid": page.cid}
        if page.bvid:
            params["bvid"] = page.bvid
        url = f"https://api.bilibili.com/x/player/v2?{urllib.parse.urlencode(params)}"
        response = await client.get(url)
        response.raise_for_status()
        payload = await response.json()
        rawList = ((payload.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
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
        logger.opt(exception=True).debug("Failed to fetch subtitles for cid={}", page.cid)
        return []
