from __future__ import annotations

import pytest
from aiohttp import web

from app.models.pack import PackServices
from app.models.task import TaskOptions
from ffmpeg_pack.pack import FFmpegPack
from http_pack.pack import HttpPack
from http_pack.task import HttpTask
from m3u8_pack.pack import M3U8Pack
from m3u8_pack.task import M3U8Task
from tests.helpers import buildRangeHandler

PLAYLIST = b"#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXTINF:10,\nseg0.ts\n#EXT-X-ENDLIST\n"


@pytest.fixture(params=["desktop", "android"])
def engine(startEngine, request):
    return startEngine(request.param)


@pytest.fixture
def features(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    for pack in (HttpPack(services), FFmpegPack(services), M3U8Pack(services)):
        engine.featureService.register(pack)
    return engine.featureService


def buildTypedHandler(content: bytes, contentType: str):
    rangeHandler = buildRangeHandler(content)

    async def handler(request: web.Request) -> web.Response:
        response = await rangeHandler(request)
        response.content_type = contentType
        return response
    return handler


async def test_parse_playlist_without_suffix_adds_stream(features, startServer):
    url = await startServer(buildTypedHandler(PLAYLIST, "application/vnd.apple.mpegurl"))

    task = await features.parse(TaskOptions(url=f"{url}?id=1"))

    assert isinstance(task, M3U8Task)
    assert not task.isLive


async def test_parse_broken_playlist_without_suffix_adds_plain_file(features, startServer):
    url = await startServer(buildTypedHandler(b"<html>expired</html>", "application/vnd.apple.mpegurl"))

    task = await features.parse(TaskOptions(url=url))

    assert isinstance(task, HttpTask)
