from __future__ import annotations

import asyncio
from time import perf_counter
from urllib.parse import urlparse

from loguru import logger

from app.client import buildClient
from app.models.task import TaskError
from .config import GITHUB_PROXY_SITES, githubConfig

PROBE_TARGET = "https://github.com/cli/cli/releases/download/v2.62.0/gh_2.62.0_linux_amd64.tar.gz"
PROBE_UNAVAILABLE = -1
PROBE_TIMEOUT = -2


def toProxyHeaders(headers: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in headers.items() if k.lower() not in {"authorization", "cookie"}}


def matchResponse(originalUrl: str, status: int, headers: dict[str, str]) -> bool:
    parsedUrl = urlparse(originalUrl)
    if parsedUrl.hostname == "codeload.github.com" or "/archive/" in parsedUrl.path:
        return status in {200, 206} and not headers.get("content-type", "").lower().startswith("text/")

    total = headers.get("content-range", "").rpartition("/")[2]
    return status == 206 and total.isdigit() and int(total) > 0


async def fetchHead(url: str, headers: dict[str, str]) -> tuple[int, dict[str, str]]:
    client = buildClient(timeout=5)
    try:
        response = await client.get(url, headers={**headers, "range": "bytes=0-0", "accept-encoding": "identity"})
        try:
            return response.status.as_int(), {k.decode().lower(): v.decode() for k, v in response.headers}
        finally:
            response.close()
    finally:
        client.close()


async def probeUrls(urls: list[str], originalUrl: str, headers: dict[str, str]) -> tuple[str, list[str]]:
    async def probe(url: str) -> None:
        status, responseHeaders = await fetchHead(url, headers if url == originalUrl else toProxyHeaders(headers))
        if not matchResponse(originalUrl, status, responseHeaders):
            raise TaskError("代理站响应不合格（{status}）", status=status)

    urlByTask = {asyncio.create_task(probe(url)): url for url in urls}
    pending = set(urlByTask)
    unmatchedUrls = set()
    lastError = None
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                url = urlByTask[task]
                if task.exception() is None:
                    return url, [u for u in urls if u != url and u not in unmatchedUrls]
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
            status, headers = await fetchHead(f"{site}/{PROBE_TARGET}", {})
        except Exception:
            return site, PROBE_TIMEOUT
        if not matchResponse(PROBE_TARGET, status, headers):
            return site, PROBE_UNAVAILABLE
        return site, int((perf_counter() - start) * 1000)

    sites = list(GITHUB_PROXY_SITES)
    if githubConfig.customSite.value:
        sites.append(githubConfig.customSite.value)
    return dict(await asyncio.gather(*(probeOne(s) for s in sites)))
