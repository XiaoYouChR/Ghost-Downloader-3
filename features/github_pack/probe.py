from __future__ import annotations

import asyncio
from dataclasses import replace
from time import perf_counter
from urllib.parse import urlparse

from loguru import logger

from app.models.task import TaskError, TaskOptions
from http_pack.pack import RemoteFile, probe
from .config import GITHUB_PROXY_SITES, githubConfig

PROBE_TARGET = "https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.tar.gz"
PROBE_UNAVAILABLE = -1
PROBE_TIMEOUT = -2


def toProxyHeaders(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in {"authorization", "cookie"}}


def matchFile(originalUrl: str, file: RemoteFile) -> bool:
    parsedUrl = urlparse(originalUrl)
    if parsedUrl.hostname == "codeload.github.com" or "/archive/" in parsedUrl.path:
        return not file.contentType.startswith("text/")
    return file.canUseRangeRequests and file.fileSize > 0


async def probeUrls(options: TaskOptions, urls: list[str]) -> tuple[str, RemoteFile, list[str]]:
    originalUrl = options.url

    async def probeOne(url: str) -> RemoteFile:
        headers = options.headers if url == originalUrl else toProxyHeaders(options.headers)
        file = await asyncio.wait_for(probe(replace(options, url=url, headers=headers)), 5)
        if not matchFile(originalUrl, file):
            raise TaskError("代理站响应不合格")
        return file

    urlByTask = {asyncio.create_task(probeOne(url)): url for url in urls}
    pending = set(urlByTask)
    unmatchedUrls = set()
    lastError = None
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                url = urlByTask[task]
                if task.exception() is None:
                    return url, task.result(), [u for u in urls if u != url and u not in unmatchedUrls]
                unmatchedUrls.add(url)
                lastError = task.exception()
                logger.debug("GitHub 候选不可用 {}: {}", url, lastError)
        raise lastError
    finally:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def probeProxyLatencies() -> dict[str, int]:
    async def probeOne(site: str) -> tuple[str, int]:
        start = perf_counter()
        try:
            file = await asyncio.wait_for(probe(TaskOptions(url=f"{site}/{PROBE_TARGET}", headers={})), 5)
        except TimeoutError:
            return site, PROBE_TIMEOUT
        except Exception:
            return site, PROBE_UNAVAILABLE
        if not matchFile(PROBE_TARGET, file):
            return site, PROBE_UNAVAILABLE
        return site, int((perf_counter() - start) * 1000)

    sites = list(GITHUB_PROXY_SITES)
    if githubConfig.customSite.value:
        sites.append(githubConfig.customSite.value)
    return dict(await asyncio.gather(*(probeOne(s) for s in sites)))
