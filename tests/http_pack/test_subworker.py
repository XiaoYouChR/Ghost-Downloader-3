from __future__ import annotations

import asyncio
from pathlib import Path
from struct import pack

import pytest
from aiohttp import web

from app.models.task import Task, TaskError, TaskStatus
from features.http_pack.task import HttpTask, HttpTaskStep
from tests.helpers import buildFileContent, buildRangeHandler, runStep


def buildStep(url: str, tmp_path: Path, *, fileSize: int, subworkerCount: int = 2,
             canUseRangeRequests: bool = True, userAgent: str = "") -> tuple[HttpTask, HttpTaskStep]:
    step = HttpTaskStep(stepIndex=0, url=url, fileSize=fileSize, subworkerCount=subworkerCount,
                        canUseRangeRequests=canUseRangeRequests, userAgent=userAgent, clientProfile="raw")
    task = HttpTask(name="test.bin", url=url, outputFolder=tmp_path, fileSize=fileSize, steps=[step])
    task.setStatus(TaskStatus.RUNNING)
    return task, step


def buildRangeRecorder(handler, ranges: list[str]):
    async def recording(request: web.Request) -> web.StreamResponse:
        if request.headers.get("Range") != PROBE_RANGE:
            ranges.append(request.headers.get("Range", ""))
        return await handler(request)
    return recording


PROBE_RANGE = "bytes=0-0"


def createRecord(path: Path, *subworkers: tuple[int, int, int]) -> None:
    Path(f"{path}.ghd").write_bytes(b"".join(pack("<QQQ", *subworker) for subworker in subworkers))


def buildFullBodyHandler(content: bytes):
    async def handler(request: web.Request) -> web.Response:
        return web.Response(body=content, headers={"Content-Length": str(len(content))})
    return handler


@pytest.mark.parametrize("subworkerCount", [1, 2, 10])
async def test_run_writes_served_file(startServer, tmp_path, subworkerCount):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=subworkerCount)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_fails_on_403(startServer, tmp_path):
    async def forbidden(request):
        return web.Response(status=403, text="Forbidden")

    url = await startServer(forbidden)
    task, step = buildStep(url, tmp_path, fileSize=100, subworkerCount=1)

    with pytest.raises(TaskError, match="403"):
        await runStep(step)


async def test_run_without_range_support_fetches_whole_file(startServer, tmp_path):
    content = buildFileContent(500)
    url = await startServer(buildFullBodyHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=500, subworkerCount=1, canUseRangeRequests=False)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_falls_back_when_range_is_ignored(startServer, tmp_path):
    content = buildFileContent(500)
    url = await startServer(buildFullBodyHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=500, subworkerCount=2)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content


async def test_run_sends_user_agent_on_every_request(startServer, tmp_path):
    userAgents = []
    content = buildFileContent(100)
    handler = buildRangeHandler(content)

    async def recording(request):
        userAgents.append(request.headers.get("User-Agent"))
        return await handler(request)

    url = await startServer(recording)
    task, step = buildStep(url, tmp_path, fileSize=100, subworkerCount=2, userAgent="GhostTest/1.0")

    await runStep(step)

    assert userAgents.count("GhostTest/1.0") == len(userAgents) >= 2


async def test_run_reports_speed_adding_up_to_file_size(startServer, tmp_path):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=2)

    assert sum(await runStep(step)) == 1000


async def test_run_splits_slow_range_when_another_finishes(startServer, tmp_path):
    size = 2_000_000
    content = buildFileContent(size)
    ranges = []

    async def slowSecondHalf(request: web.Request) -> web.StreamResponse:
        if request.headers["Range"] != PROBE_RANGE:
            ranges.append(request.headers["Range"])
        if request.headers["Range"] != f"bytes={size // 2}-{size - 1}":
            return await buildRangeHandler(content)(request)
        response = web.StreamResponse(status=206, headers={
            "Content-Range": f"bytes {size // 2}-{size - 1}/{size}", "Content-Length": str(size // 2)})
        await response.prepare(request)
        for offset in range(size // 2, size, 65536):
            await response.write(content[offset:min(offset + 65536, size)])
            await asyncio.sleep(0.05)
        return response

    url = await startServer(slowSecondHalf)
    task, step = buildStep(url, tmp_path, fileSize=size, subworkerCount=2)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content
    assert len(ranges) > 2


async def test_resume_requests_only_missing_bytes(startServer, tmp_path):
    content = buildFileContent(1000)
    ranges = []
    url = await startServer(buildRangeRecorder(buildRangeHandler(content), ranges))
    path = tmp_path / "test.bin"
    path.write_bytes(content[:700] + bytes(300))
    createRecord(path, (0, 500, 499), (500, 700, 999))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=2)

    await runStep(step)

    assert path.read_bytes() == content
    assert ranges == ["bytes=700-999"]
    assert not Path(f"{path}.ghd").exists()


@pytest.mark.parametrize("subworkerCount", [1, 4])
async def test_resume_with_new_thread_count_keeps_finished_bytes(startServer, tmp_path, subworkerCount):
    content = buildFileContent(1000)
    ranges = []
    url = await startServer(buildRangeRecorder(buildRangeHandler(content), ranges))
    path = tmp_path / "test.bin"
    path.write_bytes(content[:500] + bytes(500))
    createRecord(path, (0, 500, 499), (500, 500, 999))
    task, step = buildStep(url, tmp_path, fileSize=1000, subworkerCount=subworkerCount)

    await runStep(step)

    assert path.read_bytes() == content
    assert all(int(r.removeprefix("bytes=").split("-")[0]) >= 500 for r in ranges)


@pytest.mark.parametrize("record, fileSize", [
    (b"\xff" * 7, 1000),
    (pack("<QQQ", 0, 450, 494) + pack("<QQQ", 495, 495, 989), 990),
])
async def test_resume_from_unusable_record_starts_over(startServer, tmp_path, record, fileSize):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    path = tmp_path / "test.bin"
    path.write_bytes(bytes(1000))
    Path(f"{path}.ghd").write_bytes(record)
    task, step = buildStep(url, tmp_path, fileSize=fileSize, subworkerCount=2)

    await runStep(step)

    assert path.read_bytes() == content


async def test_run_corrects_size_from_browser(startServer, tmp_path):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    task, step = buildStep(url, tmp_path, fileSize=990, subworkerCount=4)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content
    assert task.fileSize == 1000


async def test_run_segment_keeps_its_size(startServer, tmp_path):
    content = buildFileContent(1000)
    url = await startServer(buildRangeHandler(content))
    step = HttpTaskStep(stepIndex=0, url=url, fileSize=300, httpByteOffset=200,
                        subworkerCount=2, canUseRangeRequests=True, clientProfile="raw")
    task = Task(name="test.bin", url=url, packId="ffmpeg", outputFolder=tmp_path, fileSize=300, steps=[step])
    task.setStatus(TaskStatus.RUNNING)

    await runStep(step)

    assert (tmp_path / "test.bin").read_bytes() == content[200:500]
    assert step.fileSize == 300
