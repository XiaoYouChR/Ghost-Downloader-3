from __future__ import annotations

import asyncio

import pytest
from aiohttp import web

from app.models.task import ResourceTaskOptions, TaskOptions
from github_pack.probe import matchFile, probeUrls
from http_pack.pack import RemoteFile

ASSET_URL = "https://github.com/o/r/releases/download/v1/a.tar.gz"
RAW_URL = "https://raw.githubusercontent.com/o/r/main/README.md"
ARCHIVE_URL = "https://github.com/o/r/archive/refs/heads/main.zip"
CODELOAD_URL = "https://codeload.github.com/o/r/zip/refs/heads/main"


def buildFile(*, fileSize: int = 100, canUseRangeRequests: bool = True, contentType: str = "") -> RemoteFile:
    return RemoteFile(name="a", fileSize=fileSize, canUseRangeRequests=canUseRangeRequests, contentType=contentType)


@pytest.mark.parametrize("originalUrl, file, expected", [
    (ASSET_URL, buildFile(), True),
    (RAW_URL, buildFile(contentType="text/plain"), True),
    (ASSET_URL, buildFile(canUseRangeRequests=False), False),
    (ASSET_URL, buildFile(fileSize=0), False),
    (ARCHIVE_URL, buildFile(canUseRangeRequests=False, fileSize=0, contentType="application/zip"), True),
    (CODELOAD_URL, buildFile(canUseRangeRequests=False, fileSize=0, contentType="application/zip"), True),
    (ARCHIVE_URL, buildFile(contentType="application/zip"), True),
    (ARCHIVE_URL, buildFile(canUseRangeRequests=False, contentType="text/html"), False),
    (ARCHIVE_URL, buildFile(canUseRangeRequests=False, contentType="text/plain"), False),
])
def testMatchFile(originalUrl, file, expected):
    assert matchFile(originalUrl, file) is expected


def buildSiteHandler(*, delay: float = 0, status: int = 206, contentType: str = "application/octet-stream",
                     requests: list | None = None):
    async def handler(request: web.Request) -> web.Response:
        if requests is not None:
            requests.append(dict(request.headers))
        await asyncio.sleep(delay)
        headers = {"Content-Type": contentType}
        if status == 206:
            headers["Content-Range"] = "bytes 1-1/100"
        return web.Response(status=status, body=b"x", headers=headers)
    return handler


async def testFirstMatchedWins(server):
    slow = await server(buildSiteHandler(delay=2))
    fake = await server(buildSiteHandler(status=200, contentType="text/plain"))
    good = await server(buildSiteHandler(delay=0.2))

    winner, file, fallbackUrls = await probeUrls(TaskOptions(url=ASSET_URL), [slow, fake, good])

    assert winner == good
    assert file.fileSize == 100
    assert fallbackUrls == [slow]


async def testAllUnmatchedRaises(server):
    fake = await server(buildSiteHandler(status=200, contentType="text/html"))
    denied = await server(buildSiteHandler(status=403))

    with pytest.raises(Exception):
        await probeUrls(TaskOptions(url=ASSET_URL), [fake, denied])


async def testKnownResourceStillProbes(server):
    fake = await server(buildSiteHandler(status=200, contentType="text/html"))
    good = await server(buildSiteHandler(delay=0.2))
    options = ResourceTaskOptions(url=ASSET_URL, name="a.tar.gz", size=100, canUseRangeRequests=True)

    winner, _, _ = await probeUrls(options, [fake, good])

    assert winner == good


async def testProxySiteGetsNoCredentials(server):
    directRequests, proxyRequests = [], []
    direct = await server(buildSiteHandler(delay=0.2, requests=directRequests))
    proxy = await server(buildSiteHandler(delay=0.2, requests=proxyRequests))
    headers = {"Authorization": "token t", "Cookie": "c=1", "X-Other": "1"}

    await probeUrls(TaskOptions(url=direct, headers=headers), [proxy, direct])

    assert directRequests[0]["Authorization"] == "token t"
    assert "Authorization" not in proxyRequests[0]
    assert "Cookie" not in proxyRequests[0]
    assert proxyRequests[0]["X-Other"] == "1"
