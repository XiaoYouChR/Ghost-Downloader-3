from __future__ import annotations

import pytest
from aiohttp import web

from app.models.pack import PackServices
from app.models.task import (
    MergeTaskOptions,
    ResourceTaskOptions,
    TaskError,
    TaskOptions,
    TaskStatus,
)
from ffmpeg_pack.config import ffmpegRuntime
from ffmpeg_pack.pack import FFmpegPack
from ffmpeg_pack.task import FFmpegTask
from http_pack.pack import HttpPack
from http_pack.task import HttpTask
from tests.ffmpeg_pack.test_container import buildProgressiveMp4
from tests.helpers import buildRangeHandler, waitUntil


@pytest.fixture(params=["desktop", "android"])
def engine(startEngine, request):
    return startEngine(request.param)


@pytest.fixture
def features(engine):
    services = PackServices(coroutineRunner=engine.coroutineRunner, speedMeter=engine.speedMeter)
    for pack in (HttpPack(services), FFmpegPack(services)):
        engine.featureService.register(pack)
    return engine.featureService


def buildVideoHandler(content: bytes, contentType: str = "video/mp4", name: str = "v.mp4"):
    rangeHandler = buildRangeHandler(content)

    async def handler(request: web.Request) -> web.Response:
        response = await rangeHandler(request)
        response.content_type = contentType
        if name:
            response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    return handler


async def runToCompletion(task) -> None:
    await waitUntil(lambda: task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}, timeout=20)
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.parametrize(
    "mp4",
    [
        pytest.param(buildProgressiveMp4(faststart=True), id="head-moov"),
        pytest.param(buildProgressiveMp4(faststart=False, paddingSize=80_000), id="tail-moov"),
    ],
)
async def test_parse_video_reads_duration(features, startServer, mp4):
    url = await startServer(buildVideoHandler(mp4))

    task = await features.parse(TaskOptions(url=url))

    assert isinstance(task, FFmpegTask)
    assert task.name == "v.mp4"
    assert task.duration == 10
    assert task.canTrim
    assert task.fileSize == len(mp4)


async def test_parse_browser_resource_delegates_to_video_parser(features, startServer):
    mp4 = buildProgressiveMp4(faststart=True)
    url = await startServer(buildVideoHandler(mp4))

    task = await features.parse(
        ResourceTaskOptions(
            url=url,
            name="clip.mp4",
            size=len(mp4),
            canUseRangeRequests=True,
        ),
    )

    assert isinstance(task, FFmpegTask)
    assert task.name == "clip.mp4"
    assert task.duration == 10
    assert task.fileSize == len(mp4)


async def test_parse_unindexed_video_adds_plain_file(features, startServer):
    url = await startServer(buildVideoHandler(b"not a valid mp4" * 200))

    task = await features.parse(TaskOptions(url=url))

    assert isinstance(task, HttpTask)
    assert task.name == "v.mp4"


async def test_set_time_range_updates_name_and_size(features, startServer):
    mp4 = buildProgressiveMp4(faststart=True)
    url = await startServer(buildVideoHandler(mp4))
    task = await features.parse(TaskOptions(url=url))
    assert isinstance(task, FFmpegTask)

    task.setTimeRange(3, 6)
    assert task.isTrimmed
    assert task.name == "v [00m03s-00m06s].mp4"
    assert 0 < task.fileSize < len(mp4)

    task.setName("lecture.mp4")
    assert task.name == "lecture [00m03s-00m06s].mp4"

    task.setTimeRange(0, 0)
    assert not task.isTrimmed
    assert task.name == "lecture.mp4"
    assert task.fileSize == len(mp4)


async def test_run_untrimmed_video_downloads_directly_without_ffmpeg(
    engine, features, startServer, downloadFolder, monkeypatch,
):
    monkeypatch.setattr(ffmpegRuntime, "path", lambda: "")
    mp4 = buildProgressiveMp4(faststart=True)
    url = await startServer(buildVideoHandler(mp4))
    task = await features.parse(TaskOptions(url=url))

    engine.taskService.add(task)
    await runToCompletion(task)

    assert (downloadFolder / "v.mp4").read_bytes() == mp4
    assert not (downloadFolder / "v.mp4.ghd").exists()
    assert task.currentSnapshot()[0] == 100


async def test_run_trimmed_video_without_ffmpeg_fails_with_install_error(
    engine, features, startServer, monkeypatch,
):
    monkeypatch.setattr(ffmpegRuntime, "path", lambda: "")
    mp4 = buildProgressiveMp4(faststart=True)
    url = await startServer(buildVideoHandler(mp4))
    task = await features.parse(TaskOptions(url=url))
    assert isinstance(task, FFmpegTask)
    task.setTimeRange(2, 6)

    engine.taskService.add(task)
    await waitUntil(lambda: task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED}, timeout=20)

    assert task.status == TaskStatus.FAILED
    assert task.lastError is not None
    assert task.lastError.params.get("name") == "FFmpeg"


async def test_relink_same_video_updates_url(engine, features, startServer, downloadFolder, monkeypatch):
    monkeypatch.setattr(ffmpegRuntime, "path", lambda: "")
    mp4 = buildProgressiveMp4(faststart=True)
    url = await startServer(buildVideoHandler(mp4))
    task = await features.parse(TaskOptions(url=url))
    engine.taskService.add(task, autoStart=False)

    newUrl = await startServer(buildVideoHandler(mp4))
    newTask = await features.parse(TaskOptions(url=newUrl))
    engine.taskService.edit(task, {}, newTask)
    engine.taskService.start(task)
    await runToCompletion(task)

    assert task.url == newUrl
    assert (downloadFolder / "v.mp4").read_bytes() == mp4


async def test_relink_other_video_rejects(engine, features, startServer):
    mp4 = buildProgressiveMp4(faststart=True)
    otherMp4 = buildProgressiveMp4(faststart=True, paddingSize=1024)
    task = await features.parse(TaskOptions(url=await startServer(buildVideoHandler(mp4))))
    otherTask = await features.parse(TaskOptions(url=await startServer(buildVideoHandler(otherMp4))))

    with pytest.raises(TaskError):
        engine.taskService.edit(task, {}, otherTask)


async def test_parse_merge_task_probes_duration_and_updates_trim_size(features, startServer):
    mp4 = buildProgressiveMp4(faststart=True)
    videoUrl = await startServer(buildVideoHandler(mp4, name="video.mp4"))
    audioUrl = await startServer(buildVideoHandler(mp4, name="audio.m4a"))

    task = await features.parse(
        MergeTaskOptions(
            url=videoUrl,
            video=ResourceTaskOptions(url=videoUrl, name="movie", size=len(mp4), canUseRangeRequests=True),
            audio=ResourceTaskOptions(url=audioUrl, name="movie", size=len(mp4), canUseRangeRequests=True),
        ),
    )

    assert isinstance(task, FFmpegTask)
    assert task.hasAudio
    assert task.duration == 10
    assert task.fileSize == len(mp4) * 2

    task.setTimeRange(2, 6)
    assert task.name == "movie [00m02s-00m06s].mp4"
    assert 0 < task.fileSize < len(mp4) * 2
