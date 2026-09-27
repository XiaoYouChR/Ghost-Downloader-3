"""GitHub 加速的选站：响应判定规则与竞速。

使用本地 aiohttp 服务器模拟 Proxy Site，不连外网。
"""
from __future__ import annotations

import asyncio

import pytest
from aiohttp import web

from github_pack.probe import matchResponse, probeUrls

ASSET_URL = "https://github.com/o/r/releases/download/v1/a.tar.gz"
RAW_URL = "https://raw.githubusercontent.com/o/r/main/README.md"
ARCHIVE_URL = "https://github.com/o/r/archive/refs/heads/main.zip"
CODELOAD_URL = "https://codeload.github.com/o/r/zip/refs/heads/main"


@pytest.mark.parametrize("originalUrl, status, headers, expected", [
    (ASSET_URL, 206, {"content-range": "bytes 0-0/100", "content-type": "application/octet-stream"}, True),
    (RAW_URL, 206, {"content-range": "bytes 0-0/100", "content-type": "text/plain"}, True),
    (ASSET_URL, 200, {"content-type": "application/octet-stream", "content-length": "100"}, False),
    (ASSET_URL, 200, {"content-type": "text/plain"}, False),
    (ASSET_URL, 206, {"content-type": "application/octet-stream"}, False),
    (ASSET_URL, 206, {"content-range": "bytes 0-0/*"}, False),
    (ASSET_URL, 206, {"content-range": "bytes 0-0/0"}, False),
    (ASSET_URL, 403, {"content-type": "text/html"}, False),
    (ARCHIVE_URL, 200, {"content-type": "application/zip"}, True),
    (CODELOAD_URL, 200, {"content-type": "application/zip"}, True),
    (ARCHIVE_URL, 206, {"content-range": "bytes 0-0/100", "content-type": "application/zip"}, True),
    (ARCHIVE_URL, 200, {"content-type": "text/html; charset=utf-8"}, False),
    (ARCHIVE_URL, 200, {"content-type": "text/plain"}, False),
    (ARCHIVE_URL, 404, {"content-type": "application/zip"}, False),
])
def testMatchResponse(originalUrl, status, headers, expected):
    assert matchResponse(originalUrl, status, headers) is expected


def buildSiteHandler(*, delay: float = 0, status: int = 206, contentType: str = "application/octet-stream",
                     requests: list | None = None):
    async def handler(request: web.Request) -> web.Response:
        if requests is not None:
            requests.append(dict(request.headers))
        await asyncio.sleep(delay)
        headers = {"Content-Type": contentType}
        if status == 206:
            headers["Content-Range"] = "bytes 0-0/100"
        return web.Response(status=status, body=b"x", headers=headers)
    return handler


async def testFirstMatchedWins(server):
    slow = await server(buildSiteHandler(delay=2))
    fake = await server(buildSiteHandler(status=200, contentType="text/plain"))
    good = await server(buildSiteHandler(delay=0.2))

    winner, fallbackUrls = await probeUrls([slow, fake, good], ASSET_URL, {})

    assert winner == good
    assert fallbackUrls == [slow]


async def testAllUnmatchedRaises(server):
    fake = await server(buildSiteHandler(status=200, contentType="text/html"))
    denied = await server(buildSiteHandler(status=403))

    with pytest.raises(Exception):
        await probeUrls([fake, denied], ASSET_URL, {})


async def testProxySiteGetsNoCredentials(server):
    directRequests, proxyRequests = [], []
    direct = await server(buildSiteHandler(delay=0.2, requests=directRequests))
    proxy = await server(buildSiteHandler(delay=0.2, requests=proxyRequests))
    headers = {"Authorization": "token t", "Cookie": "c=1", "X-Other": "1"}

    await probeUrls([proxy, direct], direct, headers)

    assert directRequests[0]["Authorization"] == "token t"
    assert "Authorization" not in proxyRequests[0]
    assert "Cookie" not in proxyRequests[0]
    assert proxyRequests[0]["X-Other"] == "1"
