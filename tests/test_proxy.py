from __future__ import annotations

from aiohttp import web

from app.client import buildClient


async def test_fetch_with_proxy_off_ignores_environment_proxy(config, startServer, monkeypatch):
    proxiedPaths: list[str] = []

    async def proxyHandler(request: web.Request) -> web.Response:
        proxiedPaths.append(request.path)
        return web.Response(status=502)

    async def targetHandler(request: web.Request) -> web.Response:
        return web.Response(text="direct")

    proxyUrl = (await startServer(proxyHandler)).removesuffix("/file")
    targetUrl = await startServer(targetHandler)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, proxyUrl)
    for name in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)

    client = buildClient()
    try:
        response = await client.get(targetUrl)
        assert await response.text() == "direct"
    finally:
        client.close()
    assert proxiedPaths == []
