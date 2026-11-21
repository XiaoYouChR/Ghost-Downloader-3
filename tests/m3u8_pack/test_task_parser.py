from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from app.models.pack import PackServices
from app.models.task import ResourceTaskOptions, TaskOptions
from ffmpeg_pack.pack import FFmpegPack
from http_pack.pack import HttpPack
from http_pack.task import HttpTask
from m3u8_pack.config import m3u8Config
from m3u8_pack.pack import M3U8Pack
from m3u8_pack.task import M3U8Task, subtitleChoices
from tests.helpers import buildRangeHandler

VIMEO_SAMPLE = Path(__file__).parents[1] / "samples" / "vimeo_playlist.json"
X_MASTER_SAMPLE = Path(__file__).parents[1] / "samples" / "x_master.m3u8"
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


# Trimmed from Bilibili live: vendor attributes on Content Steering and variants.
VENDOR_MASTER = (
    b'#EXTM3U\n'
    b'#EXT-X-CONTENT-STEERING:SERVER-URI="reserved",PATHWAY-ID="https://cdn.example",'
    b'BILI-PATHWAY-PRIORITY="https://cdn.example",BILI-CTR-MODE=1,BILI-TTL=150\n'
    b'#EXT-X-STREAM-INF:BANDWIDTH=1996000,RESOLUTION=1920x1080,CODECS="hvc1.1.6.L150,mp4a.40.2",BILI-QN=10000\n'
    b'index.m3u8?qn=10000\n'
    b'#EXT-X-STREAM-INF:BANDWIDTH=871556,RESOLUTION=1280x720,CODECS="hvc1.1.6.L120,mp4a.40.2",BILI-QN=250\n'
    b'index.m3u8?qn=250\n'
)


async def test_parse_master_with_vendor_attributes_adds_stream(features, startServer):
    url = await startServer(buildTypedHandler(VENDOR_MASTER, "application/vnd.apple.mpegurl"))

    task = await features.parse(TaskOptions(url=url))

    assert isinstance(task, M3U8Task)
    assert [(stream["width"], stream["height"]) for stream in task.streams] == [(1920, 1080), (1280, 720)]


async def test_parse_broken_playlist_without_suffix_adds_plain_file(features, startServer):
    url = await startServer(buildTypedHandler(b"<html>expired</html>", "application/vnd.apple.mpegurl"))

    task = await features.parse(TaskOptions(url=url))

    assert isinstance(task, HttpTask)


def buildDisguisedHandler(content: bytes):
    typedHandler = buildTypedHandler(content, "application/x-mpegurl")

    async def handler(request: web.Request) -> web.Response:
        response = await typedHandler(request)
        response.headers["Content-Disposition"] = "attachment; filename=my.9stream.us"
        return response
    return handler


async def test_parse_playlist_with_disguised_filename_adds_stream(features, startServer):
    url = await startServer(buildDisguisedHandler(PLAYLIST))

    task = await features.parse(TaskOptions(url=url))

    assert isinstance(task, M3U8Task)


async def test_parse_resource_playlist_takes_resource_name(features, startServer):
    url = await startServer(buildDisguisedHandler(PLAYLIST))

    task = await features.parse(ResourceTaskOptions(url=url, name="Nocturne.m3u8"))

    assert task.name == f"Nocturne.{m3u8Config.outputFormat.value}"


async def test_parse_vimeo_playlist_adds_stream(features, startServer):
    url = await startServer(buildTypedHandler(VIMEO_SAMPLE.read_bytes(), "application/json"))
    playlistUrl = url.removesuffix("/file") + "/exp=1~acl=x/clip/psid=1/v2/playlist/av/primary/prot/x/playlist.json"

    task = await features.parse(TaskOptions(url=playlistUrl))

    assert isinstance(task, M3U8Task)
    assert not task.isLive
    assert sorted(stream["height"] for stream in task.streams) == [240, 360, 540, 720, 1080, 1440, 2160]


async def startXMaster(startServer) -> str:
    master = buildTypedHandler(X_MASTER_SAMPLE.read_bytes(), "application/vnd.apple.mpegurl")
    variant = buildTypedHandler(PLAYLIST, "application/vnd.apple.mpegurl")

    async def handle(request: web.Request) -> web.Response:
        return await (master if request.path == "/master.m3u8" else variant)(request)

    return (await startServer(handle)).removesuffix("/file") + "/master.m3u8"


def namesIn(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


async def test_parse_master_offers_subtitles_unselected(features, startServer):
    task = await features.parse(TaskOptions(url=await startXMaster(startServer)))

    assert subtitleChoices(task) == [("zh", "zh (auto-generated)")]
    assert task.subtitleLanguages == []


async def test_add_with_subtitle_holds_side_file(engine, features, startServer, downloadFolder):
    task = await features.parse(TaskOptions(url=await startXMaster(startServer)))
    task.setOptions({"subtitleLanguages": ["zh"]})

    engine.taskService.add(task, autoStart=False)

    assert namesIn(downloadFolder) == ["master.mp4", "master.zh.srt"]
