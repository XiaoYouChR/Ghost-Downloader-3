from __future__ import annotations

from aiohttp import web

from app.models.task import ResourceTaskOptions
from features.http_pack.pack import HttpParser


async def test_resource_negative_range_hint_is_verified(server, tmp_path):
    content = b"ghost-downloader-range-probe"

    async def handler(request: web.Request) -> web.Response:
        if request.headers.get("Range") == "bytes=1-1":
            return web.Response(
                status=206,
                body=content[1:2],
                headers={"Content-Range": f"bytes 1-1/{len(content)}"},
            )
        return web.Response(body=content)

    url = await server(handler)
    task = await HttpParser().parse(ResourceTaskOptions(
        url=url,
        outputFolder=tmp_path,
        name="redirected.bin",
        size=len(content),
        canUseRangeRequests=False,
        subworkerCount=16,
    ))

    step = task.steps[0]
    assert task.name == "redirected.bin"
    assert task.fileSize == len(content)
    assert step.canUseRangeRequests is True
    assert step.subworkerCount == 16


async def test_failed_range_probe_preserves_supplied_size(server, tmp_path):
    async def handler(request: web.Request) -> web.Response:
        return web.Response(status=200)

    url = await server(handler)
    task = await HttpParser().parse(ResourceTaskOptions(
        url=url,
        outputFolder=tmp_path,
        name="known.bin",
        size=1234,
        canUseRangeRequests=False,
    ))

    step = task.steps[0]
    assert task.fileSize == 1234
    assert step.fileSize == 1234
    assert step.canUseRangeRequests is False
