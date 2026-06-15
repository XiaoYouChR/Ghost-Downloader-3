import asyncio
from base64 import b64encode
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import libtorrent as lt
import niquests
from loguru import logger

from app.bases.models import TaskStage
from app.supports.config import cfg, defaultHeaders
from app.supports.utils import getProxies, splitCookies, toSafeFilename
from .config import bittorrentConfig
from .session import btSessionService
from .task import BTFile, BTTask
from .trackers import mergeTrackers
from .web_tracker.service import webTrackerService


def loadLocalTorrent(source: str) -> Path | None:
    text = str(source).strip()
    if not text:
        return None

    parsed = urlparse(text)
    if parsed.scheme.lower() == "file":
        location = f"//{parsed.netloc}{parsed.path}" if parsed.netloc else parsed.path
        path = Path(url2pathname(unquote(location))).expanduser()
        return path if path.suffix.lower() == ".torrent" else None

    if "://" in text or parsed.scheme.lower() == "magnet":
        return None

    path = Path(text).expanduser()
    return path if path.suffix.lower() == ".torrent" else None


async def _loadFromFile(source: str) -> tuple[bytes, lt.torrent_info]:
    torrentPath = loadLocalTorrent(source)
    if torrentPath is None:
        raise ValueError("不是有效的本地 .torrent 文件路径")
    torrentBytes = await asyncio.to_thread(torrentPath.resolve().read_bytes)
    return torrentBytes, lt.torrent_info(torrentBytes)


async def _loadFromUrl(payload: dict) -> tuple[bytes, lt.torrent_info]:
    url = str(payload["url"]).strip()
    headers = payload.get("headers") or defaultHeaders()
    proxies = payload.get("proxies", getProxies())
    requestHeaders, requestCookies = splitCookies(
        headers if isinstance(headers, dict) else defaultHeaders()
    )

    async with niquests.AsyncSession(timeout=30, happy_eyeballs=True) as client:
        client.trust_env = False
        response = await client.get(
            url,
            headers=requestHeaders,
            cookies=requestCookies,
            proxies=proxies,
            verify=cfg.SSLVerify.value,
            allow_redirects=True,
        )
        response.raise_for_status()
        torrentBytes = cast(bytes, response.content)

    return torrentBytes, lt.torrent_info(torrentBytes)


async def _loadFromMagnet(
    payload: dict,
    webTrackers: list[str],
) -> tuple[bytes, lt.torrent_info, list[str]]:
    url = str(payload["url"]).strip()
    return await btSessionService.fetchMetadata(url, webTrackers)


def _buildTask(
    ti: lt.torrent_info,
    *,
    payload: dict,
    sourceType: str,
    sourceUrl: str,
    torrentBytes: bytes,
    trackers: list[str],
) -> BTTask:
    files = ti.files()
    entries: list[BTFile] = [
        BTFile(
            index=index,
            path=files.file_path(index),
            size=files.file_size(index),
        )
        for index in range(ti.num_files())
        if not (files.file_flags(index) & lt.file_storage.flag_pad_file)
    ]

    if not entries:
        raise ValueError("该种子中没有可下载的普通文件")

    rootName = toSafeFilename(PurePosixPath(entries[0].path).parts[0], fallback="torrent")
    title = toSafeFilename(Path(entries[0].path).name, fallback="torrent") if len(entries) == 1 else rootName

    return BTTask(
        title=title,
        url=sourceUrl,
        fileSize=sum(entry.size for entry in entries),
        path=Path(payload.get("path", cfg.downloadFolder.value)),
        stages=[TaskStage(stageIndex=1)],
        sourceType=sourceType,
        torrentData=b64encode(torrentBytes).decode(),
        trackers=trackers,
        files=entries,
    )


async def resolve(payload: dict) -> BTTask:
    url = str(payload["url"]).strip()

    if bittorrentConfig.enableWebTrackers.value:
        if bittorrentConfig.autoRefreshWebTrackers.value:
            try:
                await webTrackerService.refresh()
            except Exception as e:
                logger.opt(exception=e).warning("刷新 Web Tracker 失败,使用缓存 {}", repr(e))
        webTrackers = webTrackerService.mergedTrackers()
    else:
        webTrackers = []

    # Fixes https://github.com/XiaoYouChR/Ghost-Downloader-3/issues/448
    localTorrentPath = loadLocalTorrent(url)
    if localTorrentPath is not None:
        torrentBytes, ti = await _loadFromFile(url)
        trackers = mergeTrackers(ti, webTrackers)
        sourceType, sourceUrl = "torrent", str(localTorrentPath.resolve())
    elif urlparse(url).scheme.lower() == "magnet":
        torrentBytes, ti, trackers = await _loadFromMagnet(payload, webTrackers)
        sourceType, sourceUrl = "magnet", url
    else:
        torrentBytes, ti = await _loadFromUrl(payload)
        trackers = mergeTrackers(ti, webTrackers)
        sourceType, sourceUrl = "torrent", url

    return await asyncio.to_thread(
        _buildTask,
        ti,
        payload=payload,
        sourceType=sourceType,
        sourceUrl=sourceUrl,
        torrentBytes=torrentBytes,
        trackers=trackers,
    )
