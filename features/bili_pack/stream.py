from __future__ import annotations

import urllib.parse
from collections.abc import Callable
from typing import TYPE_CHECKING

from loguru import logger

from app.client import buildClient
from app.models.task import TaskError
from .config import bilibiliConfig

if TYPE_CHECKING:
    import wreq
    from .task import BiliPage

ALL_DASH_STREAMS = 4048
PLAYURL_API = "https://api.bilibili.com/x/player/wbi/playurl"
PLAYER_API = "https://api.bilibili.com/x/player/wbi/v2"
BUVID_API = "https://api.bilibili.com/x/frontend/finger/spi"
DEFAULT_REFERER = "https://www.bilibili.com"


def extractHeader(headers: dict[str, str] | None, name: str, default: str = "") -> str:
    if not headers:
        return default
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target and v:
            return v
    return default


def toSubtitleUrl(url: str) -> str:
    url = str(url or "").strip()
    if url.startswith("//"):
        return "https:" + url
    return url


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


async def probeSize(url: str, headers: dict[str, str] | None = None) -> int:
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
            cr = bytes(raw).decode()
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


def parseDash(page: BiliPage, dash: dict, *, qn: int, acceptQuality: list[int], audioQn: int) -> None:
    videoStreams = list(dash.get("video") or [])
    flac = (dash.get("flac") or {}).get("audio")
    audioStreams = sorted([
        *(dash.get("audio") or []),
        *((dash.get("dolby") or {}).get("audio") or []),
        *([flac] if flac else []),
    ], key=lambda s: s["bandwidth"], reverse=True)
    if not videoStreams:
        raise ValueError("Bilibili 返回结果中不存在可用的媒体流")
    video = matchStream(videoStreams, qn, acceptQuality)
    audio = matchAudio(audioStreams, audioQn) if audioStreams else None
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


def matchAudio(streams: list[dict], quality: int) -> dict:
    playable = [s for s in streams if toStreamUrl(s)]
    if not playable:
        raise ValueError("未找到可用的媒体流")
    preferred = next((s for s in playable if s.get("id") == quality), None)
    if preferred:
        return preferred
    pick = max if bilibiliConfig.alternativeQuality.value == "max" else min
    return pick(playable, key=lambda s: s["bandwidth"])


async def resolveSignParams(signParams: Callable[[dict], dict] | None = None) -> Callable[[dict], dict]:
    if signParams is not None:
        return signParams
    from .account import fetchWbiMixinKey, signWbiParams
    mixinKey = await fetchWbiMixinKey()
    return lambda params: signWbiParams(params, mixinKey)


async def openPlayerClient(headers: dict[str, str] | None) -> tuple[wreq.Client, str]:
    cookie = extractHeader(headers, "cookie")
    referer = extractHeader(headers, "referer", DEFAULT_REFERER)
    reqHeaders = {"referer": referer}
    if cookie:
        reqHeaders["cookie"] = cookie
    client = buildClient(headers=reqHeaders)
    if cookie and "buvid3=" not in cookie.lower():
        buvid = await fetchBuvid(client)
        if buvid:
            cookie = f"{cookie}; buvid3={buvid}"
            reqHeaders["cookie"] = cookie
            client.close()
            client = buildClient(headers=reqHeaders)
    return client, cookie


async def fetchPlayurl(
    page: BiliPage,
    *,
    qn: int,
    headers: dict[str, str],
    signParams: Callable[[dict], dict] | None = None,
    audioQn: int,
) -> tuple[list[int], list[str], int]:
    signParams = await resolveSignParams(signParams)
    client, cookie = await openPlayerClient(headers)
    try:
        if cookie:
            page.headers["cookie"] = cookie

        playParams = {"cid": page.cid, "qn": qn, "fnval": ALL_DASH_STREAMS, "fourk": 1}
        if page.bvid:
            playParams["bvid"] = page.bvid
        playParams = signParams(playParams)
        playApiUrl = f"{PLAYURL_API}?{urllib.parse.urlencode(playParams)}"

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
            try:
                page.subtitles = await querySubtitles(
                    client, cid=page.cid, aid=page.aid, bvid=page.bvid, signParams=signParams,
                )
            except Exception:
                logger.opt(exception=True).debug("Failed to fetch subtitles for cid={}", page.cid)
                page.subtitles = []
        return acceptQuality, list(pageData.get("accept_description") or []), qn
    finally:
        client.close()


async def fetchBuvid(client: wreq.Client) -> str:
    try:
        response = await client.get(BUVID_API)
        payload = await response.json()
        return str(((payload.get("data") or {}).get("b_3") or "")).strip()
    except Exception:
        logger.opt(exception=True).debug("Failed to fetch buvid3")
        return ""


async def querySubtitles(
    client: wreq.Client,
    *,
    cid: int,
    aid: int = 0,
    bvid: str = "",
    signParams: Callable[[dict], dict],
) -> list[dict]:
    params: dict = {"cid": cid}
    if aid > 0:
        params["aid"] = aid
    elif bvid:
        params["bvid"] = bvid
    params = signParams(params)
    url = f"{PLAYER_API}?{urllib.parse.urlencode(params)}"
    response = await client.get(url)
    try:
        if response.status.as_int() == 412:
            raise TaskError("Bilibili 拦截了字幕请求（412 风控），请稍后再试")
        response.raise_for_status()
        payload = await response.json()
    finally:
        response.close()

    if payload.get("code") not in {None, 0}:
        raise ValueError(payload.get("message") or "获取 Bilibili 字幕列表失败")

    data = payload.get("data") or {}
    respCid = data.get("cid")
    if respCid and int(respCid) != cid:
        raise ValueError(f"字幕响应 cid 不匹配: 期望 {cid}，实际 {respCid}")
    respAid = data.get("aid")
    if aid > 0 and respAid and int(respAid) != aid:
        raise ValueError(f"字幕响应 aid 不匹配: 期望 {aid}，实际 {respAid}")
    respBvid = str(data.get("bvid") or "")
    if bvid and respBvid and respBvid != bvid:
        raise ValueError(f"字幕响应 bvid 不匹配: 期望 {bvid}，实际 {respBvid}")

    rawList = (data.get("subtitle") or {}).get("subtitles") or []
    return [
        {
            "lan": s["lan"],
            "lan_doc": s.get("lan_doc", s["lan"]),
            "subtitle_url": toSubtitleUrl(s.get("subtitle_url", "")),
            "isAi": s.get("type", 0) == 1,
        }
        for s in rawList if s.get("lan") and s.get("subtitle_url")
    ]


async def fetchSubtitles(
    cid: int,
    *,
    aid: int = 0,
    bvid: str = "",
    headers: dict[str, str] | None = None,
) -> list[dict]:
    signParams = await resolveSignParams()
    client, _ = await openPlayerClient(headers)
    try:
        return await querySubtitles(client, cid=cid, aid=aid, bvid=bvid, signParams=signParams)
    finally:
        client.close()


def toSrtTime(seconds: float) -> str:
    totalMs = int(round(seconds * 1000))
    h, rem = divmod(totalMs // 1000, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{totalMs % 1000:03d}"


def toSrt(body: list[dict]) -> str:
    lines: list[str] = []
    seq = 0
    for entry in body:
        content = str(entry.get("content", "")).strip()
        if not content:
            continue
        seq += 1
        lines.append(str(seq))
        lines.append(f"{toSrtTime(float(entry.get('from', 0)))} --> {toSrtTime(float(entry.get('to', 0)))}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


async def fetchSubtitleSrt(url: str, *, headers: dict[str, str] | None = None) -> str:
    url = toSubtitleUrl(url)
    if not url:
        return ""
    referer = extractHeader(headers, "referer", DEFAULT_REFERER)
    client = buildClient(headers={"referer": referer})
    try:
        response = await client.get(url)
        try:
            response.raise_for_status()
            payload = await response.json()
        finally:
            response.close()
    finally:
        client.close()
    return toSrt(payload.get("body") or [])
